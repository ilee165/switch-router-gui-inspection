"""host_key_dialog.py — Cross-thread host key verification for RemoteIn.

Architecture
============
HostKeyVerifier is a QObject that lives on the main (GUI) thread. When a
Netmiko worker thread calls verify_host_key(), the verifier:

  1. Looks up the stored key in SQLite via db.get_host_key().
  2. If the stored key matches the live key blob, returns "accept_once" silently
     (SSH-02 happy path — no dialog, no user interrupt).
  3. Otherwise, sets up a threading.Event, emits host_key_check_requested
     (QueuedConnection — delivered to the main thread's event loop), and blocks
     with event.wait(timeout=30).
  4. The main thread slot _show_host_key_dialog receives the signal, shows the
     appropriate modal dialog, stores the result in self._pending, and calls
     event.set() to unblock the worker.
  5. The worker reads the result, updates the DB if needed, and returns.

Timeout: if the user does not respond within 30 seconds, event.wait() returns
False and verify_host_key() returns "reject" — the safe default.

Dependencies
============
- db.py (get_host_key, store_host_key, update_host_key) — no connector.py import.
- PyQt6 (QObject, QDialog, pyqtSignal, Qt).
- panels/base.py (PALETTE) for consistent color usage.
"""

from __future__ import annotations

import sqlite3
import threading

import db
from panels.base import PALETTE
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)


# ── HostKeyVerifier ────────────────────────────────────────────────────────────

class HostKeyVerifier(QObject):
    """QObject that bridges the Netmiko worker thread and the GUI dialog.

    Must be constructed on the main thread. The host_key_check_requested signal
    is connected to _show_host_key_dialog with the default QueuedConnection type,
    which delivers the signal safely across threads via the main event loop.

    Usage (wiring, done in main.py / panel init):
        self.verifier = HostKeyVerifier(parent=self)
        self.verifier.host_key_check_requested.connect(
            self.verifier._show_host_key_dialog
        )

    Then pass self.verifier.verify_host_key as verifier_fn to connector functions.
    But first call:
        self.verifier.device_id = device["id"]
    so the verifier knows which device row to key against.
    """

    # Signal: hostname, port, key_type, fingerprint, key_blob, situation
    # situation is "new" (SSH-01 first connect) or "changed" (SSH-03 key mismatch)
    # port is int — PyQt6 supports int in signal signatures.
    host_key_check_requested = pyqtSignal(str, int, str, str, str, str)

    # Emitted after a "Connect Anyway" decision on a changed key (SSH-03, D-07).
    # Carries the status bar message string to display. Connected in main.py to
    # MainWindow._set_status so it is delivered on the main thread.
    connection_status_note = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending = None   # dict while a check is active; None otherwise
        self.device_id: int | None = None

    # ── Worker-thread entry point ──────────────────────────────────────────────

    def verify_host_key(self, *, hostname: str, port: int, key_type: str,
                        fingerprint: str, key_blob: str) -> str:
        """Called from the Netmiko worker thread.  Blocks until user responds.

        All parameters are keyword-only (the * separator) so they cannot be
        supplied positionally — matches the calling convention in connector.py
        RemoteInHostKeyPolicy.missing_host_key().

        Returns:
            "accept_once"  — allow connection, DB NOT updated.
            "always_trust" — allow connection, key written/updated in DB.
            "reject"       — deny connection, raise SSHException upstream.
        """
        device_id = self.device_id
        if device_id is None:
            # Safety guard: device_id must be set before calling verify_host_key.
            # Without it we cannot look up or persist the key. Reject to be safe.
            print("[HostKeyVerifier] WARNING: device_id not set; rejecting connection.")
            return "reject"

        # ── SSH-02 happy path: known matching key ──────────────────────────────
        stored = db.get_host_key(
            device_id=device_id,
            hostname=hostname,
            port=port,
            key_type=key_type,
        )
        if stored is not None and stored["key_blob"] == key_blob:
            # Silent reconnect — key matches exactly, no dialog needed.
            return "accept_once"

        # ── Determine situation ────────────────────────────────────────────────
        if stored is None:
            situation = "new"          # SSH-01: first connect
        else:
            situation = "changed"      # SSH-03: stored key does not match

        # ── Cross-thread sync setup ────────────────────────────────────────────
        event = threading.Event()
        self._pending = {
            "event": event,
            "result": None,
            # old fingerprint for ChangedKeyDialog (None for first-connect)
            "stored_fingerprint": stored["fingerprint"] if stored else None,
        }

        # Emit signal — QueuedConnection delivers this to the main thread's
        # event loop without blocking the worker.
        self.host_key_check_requested.emit(
            hostname, port, key_type, fingerprint, key_blob, situation
        )

        # Block the worker thread until the main thread sets the event.
        fired = event.wait(timeout=30)

        # Read result before clearing _pending.
        result = (self._pending.get("result") if self._pending else None) or "reject"

        # Timeout (fired=False) or result still None → reject safely.
        if not fired:
            result = "reject"

        # Clear pending state — must happen before any DB call so a subsequent
        # connection attempt on another thread does not see stale state.
        self._pending = None

        # ── D-07: emit status note for "Connect Anyway" on a changed key ──────
        # Emitted from the worker thread; Qt routes to main thread via
        # QueuedConnection because the verifier lives on the main thread.
        if result == "accept_once" and situation == "changed":
            self.connection_status_note.emit("Connected (host key mismatch not resolved)")

        # ── Persist to DB from worker thread ───────────────────────────────────
        # SQLite is thread-safe in serialized mode (Python's sqlite3 default).
        if result == "always_trust":
            try:
                db.store_host_key(
                    device_id=device_id,
                    hostname=hostname,
                    port=port,
                    key_type=key_type,
                    fingerprint=fingerprint,
                    key_blob=key_blob,
                )
            except sqlite3.IntegrityError as exc:
                # Log but do not abort — connection proceeds, user will see the
                # dialog again next time because the key was not persisted.
                print(f"[HostKeyVerifier] store_host_key failed: {exc}")

        elif result == "update_key":
            try:
                db.update_host_key(
                    device_id=device_id,
                    hostname=hostname,
                    port=port,
                    key_type=key_type,
                    fingerprint=fingerprint,
                    key_blob=key_blob,
                )
            except sqlite3.IntegrityError as exc:
                print(f"[HostKeyVerifier] update_host_key failed: {exc}")
            # Remap to "always_trust" — RemoteInHostKeyPolicy only understands
            # accept_once / always_trust / reject; "update_key" is internal only.
            result = "always_trust"

        return result

    # ── Main-thread slot ───────────────────────────────────────────────────────

    def _show_host_key_dialog(self, hostname: str, port: int, key_type: str,
                              fingerprint: str, key_blob: str, situation: str) -> None:
        """Slot connected to host_key_check_requested (runs on the main thread).

        Shows the appropriate modal dialog, stores the user's choice in
        self._pending["result"], then calls event.set() to unblock the worker.

        This method MUST always call event.set() — even if dialog construction
        fails — so the worker thread is never left hanging indefinitely.
        """
        if self._pending is None:
            # Safety: nothing is waiting (e.g. stale signal delivery). Ignore.
            return

        try:
            if situation == "new":
                dialog = FirstConnectDialog(
                    hostname=hostname,
                    port=port,
                    key_type=key_type,
                    fingerprint=fingerprint,
                )
            else:
                # situation == "changed"
                old_fp = self._pending.get("stored_fingerprint") or "(unknown)"
                dialog = ChangedKeyDialog(
                    hostname=hostname,
                    port=port,
                    key_type=key_type,
                    old_fingerprint=old_fp,
                    new_fingerprint=fingerprint,
                )

            dialog.exec()   # blocks main thread until user responds (modal)
            self._pending["result"] = dialog.result_action

        except Exception as exc:
            # Dialog construction failed — reject to keep the system safe.
            print(f"[HostKeyVerifier] dialog error: {exc}")
            self._pending["result"] = "reject"

        finally:
            # Always unblock the worker — a hanging worker is worse than a reject.
            self._pending["event"].set()


# ── FirstConnectDialog (SSH-01) ───────────────────────────────────────────────

class FirstConnectDialog(QDialog):
    """Shown when connecting to a host whose key is not in the DB (SSH-01).

    Mirrors the PuTTY host-key prompt:
    - Shows hostname, key type, and SHA256 fingerprint.
    - Three choices: Reject / Accept Once / Always Trust.
    - Closing with the window X button is treated as Reject (D-04).

    result_action is always set before the dialog closes:
      "reject"       — Reject button or window X.
      "always_trust" — Accept Once or Always Trust (D-01: both store the key).
    """

    def __init__(self, parent=None, *, hostname: str, port: int,
                 key_type: str, fingerprint: str):
        super().__init__(parent)
        self.setWindowTitle("SSH Host Key Verification")
        self.setMinimumWidth(520)

        # Safe defaults — set before any widget interaction.
        self.result_action: str = "reject"
        self._button_clicked: bool = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("Unknown Host Key")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        # Body text
        body = QLabel(
            f"The host key for this server was not recognized.\n\n"
            f"Host:         {hostname}:{port}\n"
            f"Key type:     {key_type}\n"
            f"Fingerprint:  {fingerprint}\n\n"
            f"Verify this fingerprint matches the server before accepting.\n"
            f"A mismatch may indicate a MITM attack or a new server install."
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        reject_btn = QPushButton("Reject")
        reject_btn.setObjectName("dangerBtn")
        reject_btn.clicked.connect(self._on_reject)

        accept_once_btn = QPushButton("Accept Once")
        accept_once_btn.setObjectName("primaryBtn")
        accept_once_btn.clicked.connect(self._on_accept_once)

        always_trust_btn = QPushButton("Always Trust")
        always_trust_btn.setObjectName("primaryBtn")
        always_trust_btn.clicked.connect(self._on_always_trust)

        btn_row.addWidget(reject_btn)
        btn_row.addStretch()
        btn_row.addWidget(accept_once_btn)
        btn_row.addWidget(always_trust_btn)
        layout.addLayout(btn_row)

    # ── Button handlers ────────────────────────────────────────────────────────

    def _on_reject(self):
        self._button_clicked = True
        self.result_action = "reject"
        self.reject()

    def _on_accept_once(self):
        # D-01 decision: both "Accept Once" and "Always Trust" store the key.
        # The label distinction is for user clarity (one-time vs permanent intent),
        # but the verifier maps both to db.store_host_key. We return "always_trust"
        # from Accept Once so the verifier's DB-write branch fires.
        self._button_clicked = True
        self.result_action = "always_trust"
        self.accept()

    def _on_always_trust(self):
        self._button_clicked = True
        self.result_action = "always_trust"
        self.accept()

    def closeEvent(self, event):
        # closeEvent fires when the dialog is closing via any path (button or X).
        # Only override result_action if no button was clicked — that means the
        # user pressed the window X button, which is treated as Reject (D-04).
        if not self._button_clicked:
            self.result_action = "reject"
        if event is not None:
            super().closeEvent(event)


# ── ChangedKeyDialog (SSH-03) ─────────────────────────────────────────────────

class ChangedKeyDialog(QDialog):
    """Shown when the stored host key does not match the live key (SSH-03).

    Displays old vs new fingerprints and a prominent MITM warning.
    Per D-05 (three buttons): Cancel / Connect Anyway / Update Key.
    Per D-06: title "Host Key Changed", shows both fingerprints.

    result_action:
      "reject"       — Cancel button or window X.
      "accept_once"  — Connect Anyway (key NOT updated in DB).
      "update_key"   — Update Key (verifier will call db.update_host_key).
    """

    def __init__(self, parent=None, *, hostname: str, port: int, key_type: str,
                 old_fingerprint: str, new_fingerprint: str):
        super().__init__(parent)
        self.setWindowTitle("SSH Host Key Changed")
        self.setMinimumWidth(560)

        self.result_action: str = "reject"
        self._button_clicked: bool = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title — D-06 specifies "Host Key Changed"
        title = QLabel("Host Key Changed")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)

        # Warning label — red, prominent
        warning = QLabel("WARNING")
        warning.setStyleSheet(f"color: {PALETTE['error']}; font-weight: bold; font-size: 14px;")
        layout.addWidget(warning)

        # Body text — shows both fingerprints per D-06
        body = QLabel(
            f"The host key for {hostname}:{port} has changed.\n\n"
            f"Stored key:   {key_type} {old_fingerprint}\n"
            f"New key:      {key_type} {new_fingerprint}\n\n"
            f"This may indicate a MITM attack or a legitimate key change\n"
            f"(device reimaged or rotated).\n\n"
            f"Verify the new fingerprint before proceeding."
        )
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)

        # Button row — D-05: Cancel / Connect Anyway / Update Key
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("dangerBtn")
        cancel_btn.clicked.connect(self._on_cancel)

        connect_anyway_btn = QPushButton("Connect Anyway")
        connect_anyway_btn.setObjectName("primaryBtn")
        connect_anyway_btn.clicked.connect(self._on_connect_anyway)

        update_key_btn = QPushButton("Update Key")
        update_key_btn.setObjectName("primaryBtn")
        update_key_btn.clicked.connect(self._on_update_key)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(connect_anyway_btn)
        btn_row.addWidget(update_key_btn)
        layout.addLayout(btn_row)

    # ── Button handlers ────────────────────────────────────────────────────────

    def _on_cancel(self):
        self._button_clicked = True
        self.result_action = "reject"
        self.reject()

    def _on_connect_anyway(self):
        # Connect this session only — stored key is NOT updated (D-05).
        # Next connect will show this dialog again.
        self._button_clicked = True
        self.result_action = "accept_once"
        self.accept()

    def _on_update_key(self):
        # Replace stored key AND connect — verifier calls db.update_host_key.
        self._button_clicked = True
        self.result_action = "update_key"
        self.accept()

    def closeEvent(self, event):
        # X button: treat as Cancel per D-04 logic.
        if not self._button_clicked:
            self.result_action = "reject"
        if event is not None:
            super().closeEvent(event)
