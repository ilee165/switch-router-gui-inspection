"""tests/test_wiring.py — Adversarial end-to-end wiring tests for Plan 04-04.

Verifies that verifier_fn travels from set_device() through _run_fetch() and
_start_worker() to the connector function, and that connection_status_note is
emitted after a "Connect Anyway" decision on a changed key.

No real devices or network connections are used.

Run:
    python tests/test_wiring.py
All 4 tests print PASS on success.
"""

from __future__ import annotations

import sys
import os
import threading
import types
import unittest.mock as mock

# ── Ensure project root is importable ─────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── QApplication must exist before any Qt widget is instantiated ──────────────
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

# ── Imports under test ────────────────────────────────────────────────────────
from panels.base import BasePanel
from panels.interfaces import InterfacesPanel
from host_key_dialog import HostKeyVerifier


# ── Shared dummy data ─────────────────────────────────────────────────────────

_DEVICE   = {"id": 1, "name": "test-sw", "hostname": "10.0.0.1",
              "platform": "ios", "port": 22, "username": "admin",
              "password": "enc:placeholder", "enable_pass": "", "notes": ""}
_SESSION_KEY = b"\x00" * 32
_VERIFIER_FN = lambda **kw: "reject"


# ── Minimal concrete BasePanel subclass for testing ───────────────────────────

class _StubPanel(BasePanel):
    """Minimal concrete BasePanel that records the connector call args."""

    def __init__(self):
        super().__init__("STUB")
        self._captured_args = None

    def _build_content(self, layout):
        pass   # no widgets needed in tests

    def _run_fetch(self):
        # Records args passed to a mock connector fn — does not start a real thread.
        self._captured_args = (self._device, self._session_key, self._verifier_fn)

    def _on_result(self, data):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — BasePanel.set_device stores verifier_fn
# ─────────────────────────────────────────────────────────────────────────────

def test_set_device_stores_verifier_fn():
    """set_device() must store verifier_fn in self._verifier_fn."""
    panel = _StubPanel()
    assert panel._verifier_fn is None, "Expected None before set_device"

    sentinel = lambda **kw: "reject"
    panel.set_device(_DEVICE, session_key=_SESSION_KEY, verifier_fn=sentinel)

    assert panel._verifier_fn is sentinel, (
        f"Expected verifier_fn to be the sentinel lambda; got {panel._verifier_fn!r}"
    )
    print("PASS test_set_device_stores_verifier_fn")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — InterfacesPanel._run_fetch passes verifier_fn to connector
# ─────────────────────────────────────────────────────────────────────────────

def test_interfaces_run_fetch_passes_verifier_fn():
    """_run_fetch() on InterfacesPanel must include self._verifier_fn in the
    args tuple passed to _start_worker (and thus to the connector function)."""
    panel = InterfacesPanel()
    sentinel = lambda **kw: "reject"
    panel.set_device(_DEVICE, session_key=_SESSION_KEY, verifier_fn=sentinel)

    captured = {}

    def _fake_start_worker(fn, *args):
        captured["fn"] = fn
        captured["args"] = args

    # Patch _start_worker so no real thread is spawned.
    panel._start_worker = _fake_start_worker
    panel._run_fetch()

    assert "args" in captured, "_start_worker was not called"
    # connector.get_interfaces(device, session_key, verifier_fn) — verifier_fn is 3rd positional arg
    assert len(captured["args"]) == 3, (
        f"Expected 3 positional args (device, session_key, verifier_fn); got {captured['args']}"
    )
    assert captured["args"][2] is sentinel, (
        f"Expected verifier_fn sentinel as 3rd arg; got {captured['args'][2]!r}"
    )
    print("PASS test_interfaces_run_fetch_passes_verifier_fn")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — verifier_fn=None does not crash any panel
# ─────────────────────────────────────────────────────────────────────────────

def test_verifier_fn_none_does_not_crash():
    """Panels must not raise AttributeError when verifier_fn is None (the
    default before main.py wiring is complete)."""
    panel = _StubPanel()
    panel.set_device(_DEVICE, session_key=_SESSION_KEY)   # no verifier_fn arg
    assert panel._verifier_fn is None

    # Call _run_fetch — StubPanel just records args, no crash expected.
    try:
        panel._run_fetch()
    except Exception as exc:
        raise AssertionError(f"_run_fetch raised with verifier_fn=None: {exc}") from exc

    assert panel._captured_args[2] is None, (
        f"Expected None as verifier_fn in captured args; got {panel._captured_args[2]!r}"
    )
    print("PASS test_verifier_fn_none_does_not_crash")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4 — connection_status_note emits after "Connect Anyway" on changed key
# ─────────────────────────────────────────────────────────────────────────────

def test_connection_status_note_emitted_on_connect_anyway():
    """connection_status_note must emit 'Connected (host key mismatch not resolved)'
    when verify_host_key returns 'accept_once' for a CHANGED key situation."""

    received_notes: list[str] = []

    verifier = HostKeyVerifier()
    verifier.connection_status_note.connect(lambda msg: received_notes.append(msg))
    verifier.device_id = 1

    stored_key = {
        "key_blob": "DIFFERENT_BLOB",          # does not match live blob → changed
        "fingerprint": "SHA256:oldoldold",
    }

    # Patch db.get_host_key to return a stored (but different) key → situation="changed"
    with mock.patch("db.get_host_key", return_value=stored_key), \
         mock.patch("db.store_host_key"), \
         mock.patch("db.update_host_key"):

        # Simulate the dialog returning "accept_once" (Connect Anyway button).
        # Connect as a real Qt slot so QueuedConnection delivers it on processEvents().
        def _fake_show_dialog(hostname, port, key_type, fingerprint, key_blob, situation):
            # Verify we are in the "changed" situation.
            assert situation == "changed", f"Expected 'changed', got '{situation}'"
            if verifier._pending:
                verifier._pending["result"] = "accept_once"
                verifier._pending["event"].set()

        verifier.host_key_check_requested.connect(_fake_show_dialog)

        # Call verify_host_key from a worker thread (as Netmiko would do) so
        # threading.Event blocks correctly.
        result_holder: list[str] = []

        def _worker():
            r = verifier.verify_host_key(
                hostname="10.0.0.1",
                port=22,
                key_type="ssh-ed25519",
                fingerprint="SHA256:newkey",
                key_blob="LIVE_BLOB",
            )
            result_holder.append(r)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        # Pump the Qt event loop while the worker blocks on threading.Event.
        # The queued signal delivering _fake_show_dialog runs here, sets the
        # event, and unblocks the worker.
        import time
        deadline = time.monotonic() + 5.0
        while t.is_alive() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        t.join(timeout=0.5)

    assert not t.is_alive(), "Worker thread did not finish — possible deadlock"
    assert result_holder == ["accept_once"], (
        f"Expected verify_host_key to return 'accept_once'; got {result_holder}"
    )

    # Process Qt events so queued signal delivers to main thread.
    app.processEvents()

    assert received_notes == ["Connected (host key mismatch not resolved)"], (
        f"Expected connection_status_note signal with D-07 message; got {received_notes}"
    )
    print("PASS test_connection_status_note_emitted_on_connect_anyway")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_set_device_stores_verifier_fn()
    test_interfaces_run_fetch_passes_verifier_fn()
    test_verifier_fn_none_does_not_crash()
    test_connection_status_note_emitted_on_connect_anyway()
    print("\nAll 4 wiring tests PASS.")
