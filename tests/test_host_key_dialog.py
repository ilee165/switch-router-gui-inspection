"""tests/test_host_key_dialog.py — Adversarial tests for host_key_dialog.py.

Tests cover:
  - FirstConnectDialog button outcomes and X-button (closeEvent) behaviour
  - ChangedKeyDialog button outcomes and X-button behaviour
  - HostKeyVerifier.verify_host_key() logic paths:
      * silent reconnect (known matching key)
      * timeout → reject
      * "always_trust" result → db.store_host_key called with keyword-only args

A QApplication instance is required for any Qt widget test.  We obtain one
without creating duplicates using QApplication.instance().

Run:
    python tests/test_host_key_dialog.py
All 8 tests print PASS on success; any failure raises AssertionError and the
script exits non-zero.
"""

from __future__ import annotations

import sys
import os
import threading
import types
import unittest.mock as mock

# ── Ensure project root is on sys.path so host_key_dialog is importable ───────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── QApplication must exist before any Qt widget is instantiated ──────────────
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

# ── Import the module under test ──────────────────────────────────────────────
import host_key_dialog as hkd
from host_key_dialog import FirstConnectDialog, ChangedKeyDialog, HostKeyVerifier


# ── Shared dummy data ─────────────────────────────────────────────────────────

_HOST      = "10.0.0.1"
_PORT      = 22
_KEY_TYPE  = "ssh-ed25519"
_FP        = "SHA256:abcdef1234567890"
_OLD_FP    = "SHA256:oldoldoldoldold"
_BLOB      = "dGVzdA=="          # base64("test")
_DEV_ID    = 1


# ── Helper ────────────────────────────────────────────────────────────────────

def _first_connect(**kwargs) -> FirstConnectDialog:
    defaults = dict(hostname=_HOST, port=_PORT, key_type=_KEY_TYPE, fingerprint=_FP)
    defaults.update(kwargs)
    return FirstConnectDialog(**defaults)


def _changed_key(**kwargs) -> ChangedKeyDialog:
    defaults = dict(hostname=_HOST, port=_PORT, key_type=_KEY_TYPE,
                    old_fingerprint=_OLD_FP, new_fingerprint=_FP)
    defaults.update(kwargs)
    return ChangedKeyDialog(**defaults)


# ── Test 1: FirstConnectDialog X button → result_action = "reject" ────────────

def test_first_connect_x_button_rejects():
    """Closing with the window X (before any button click) must produce "reject"."""
    dialog = _first_connect()
    # _button_clicked is False at construction — simulate X by calling closeEvent.
    dialog.closeEvent(None)
    assert dialog.result_action == "reject", (
        f"Expected 'reject', got '{dialog.result_action}'"
    )
    assert dialog._button_clicked is False, "_button_clicked should still be False"
    print("Test 1 PASS — FirstConnectDialog X button → reject")


# ── Test 2: FirstConnectDialog "Accept Once" → result_action = "always_trust" ──
# D-01: both Accept Once and Always Trust store the key; both return "always_trust".

def test_first_connect_accept_once():
    """'Accept Once' button must set result_action = 'always_trust' (D-01)."""
    dialog = _first_connect()
    dialog._on_accept_once()
    assert dialog.result_action == "always_trust", (
        f"Expected 'always_trust', got '{dialog.result_action}'"
    )
    assert dialog._button_clicked is True, "_button_clicked must be True after click"
    print("Test 2 PASS — FirstConnectDialog Accept Once → always_trust")


# ── Test 3: ChangedKeyDialog X button → result_action = "reject" ──────────────

def test_changed_key_x_button_rejects():
    """X button on ChangedKeyDialog must produce 'reject' per D-04 logic."""
    dialog = _changed_key()
    dialog.closeEvent(None)
    assert dialog.result_action == "reject", (
        f"Expected 'reject', got '{dialog.result_action}'"
    )
    print("Test 3 PASS — ChangedKeyDialog X button → reject")


# ── Test 4: ChangedKeyDialog "Connect Anyway" → result_action = "accept_once" ──

def test_changed_key_connect_anyway():
    """'Connect Anyway' must set result_action = 'accept_once' (key NOT updated)."""
    dialog = _changed_key()
    dialog._on_connect_anyway()
    assert dialog.result_action == "accept_once", (
        f"Expected 'accept_once', got '{dialog.result_action}'"
    )
    print("Test 4 PASS — ChangedKeyDialog Connect Anyway → accept_once")


# ── Test 5: ChangedKeyDialog "Update Key" → result_action = "update_key" ──────

def test_changed_key_update_key():
    """'Update Key' must set result_action = 'update_key'."""
    dialog = _changed_key()
    dialog._on_update_key()
    assert dialog.result_action == "update_key", (
        f"Expected 'update_key', got '{dialog.result_action}'"
    )
    print("Test 5 PASS — ChangedKeyDialog Update Key → update_key")


# ── Test 6: verify_host_key — silent reconnect for matching key ────────────────

def test_verify_silent_reconnect():
    """Known matching key_blob must return 'accept_once' without emitting signal."""
    verifier = HostKeyVerifier()
    verifier.device_id = _DEV_ID

    stored_row = {
        "device_id": _DEV_ID, "hostname": _HOST, "port": _PORT,
        "key_type": _KEY_TYPE, "fingerprint": _FP, "key_blob": _BLOB,
        "added_at": "2026-01-01 00:00:00",
    }

    # Track whether signal was emitted
    signal_emitted = []
    verifier.host_key_check_requested.connect(
        lambda *args: signal_emitted.append(args)
    )

    with mock.patch.object(hkd.db, "get_host_key", return_value=stored_row):
        result = verifier.verify_host_key(
            hostname=_HOST, port=_PORT, key_type=_KEY_TYPE,
            fingerprint=_FP, key_blob=_BLOB,
        )

    assert result == "accept_once", f"Expected 'accept_once', got '{result}'"
    assert signal_emitted == [], f"Signal must NOT be emitted for a matching key"
    print("Test 6 PASS — verify_host_key silent reconnect → accept_once, no signal")


# ── Test 7: verify_host_key — timeout → "reject" ──────────────────────────────

def test_verify_timeout_rejects():
    """If threading.Event.wait() times out (returns False), must return 'reject'
    and clear self._pending."""
    verifier = HostKeyVerifier()
    verifier.device_id = _DEV_ID

    # get_host_key returns None → situation = "new" → signal emitted → we wait
    with mock.patch.object(hkd.db, "get_host_key", return_value=None):
        # Intercept the signal emission so the worker does not actually block
        # for 30 seconds — patch threading.Event.wait to return False immediately.
        original_wait = threading.Event.wait

        def instant_timeout(self_event, timeout=None):
            return False   # simulate timeout

        threading.Event.wait = instant_timeout
        try:
            result = verifier.verify_host_key(
                hostname=_HOST, port=_PORT, key_type=_KEY_TYPE,
                fingerprint=_FP, key_blob=_BLOB,
            )
        finally:
            threading.Event.wait = original_wait   # always restore

    assert result == "reject", f"Expected 'reject' on timeout, got '{result}'"
    assert verifier._pending is None, "_pending must be cleared after verify_host_key"
    print("Test 7 PASS — verify_host_key timeout → reject, _pending cleared")


# ── Test 8: verify_host_key — "always_trust" calls db.store_host_key ──────────

def test_verify_always_trust_calls_store():
    """When _pending result is 'always_trust', db.store_host_key must be called
    with correct keyword-only arguments."""
    verifier = HostKeyVerifier()
    verifier.device_id = _DEV_ID

    # Simulate the main thread setting the result immediately via threading.Event.
    # We do this by patching Event.wait to:
    #   1. Set _pending["result"] = "always_trust"
    #   2. Return True (as if the event fired)
    original_wait = threading.Event.wait

    def instant_accept(self_event, timeout=None):
        # At this point verifier._pending is already set by verify_host_key.
        verifier._pending["result"] = "always_trust"
        return True

    with mock.patch.object(hkd.db, "get_host_key", return_value=None), \
         mock.patch.object(hkd.db, "store_host_key") as mock_store:

        threading.Event.wait = instant_accept
        try:
            result = verifier.verify_host_key(
                hostname=_HOST, port=_PORT, key_type=_KEY_TYPE,
                fingerprint=_FP, key_blob=_BLOB,
            )
        finally:
            threading.Event.wait = original_wait

    assert result == "always_trust", f"Expected 'always_trust', got '{result}'"
    mock_store.assert_called_once_with(
        device_id=_DEV_ID,
        hostname=_HOST,
        port=_PORT,
        key_type=_KEY_TYPE,
        fingerprint=_FP,
        key_blob=_BLOB,
    )
    print("Test 8 PASS — verify_host_key 'always_trust' → db.store_host_key called with correct kwargs")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_first_connect_x_button_rejects,
        test_first_connect_accept_once,
        test_changed_key_x_button_rejects,
        test_changed_key_connect_anyway,
        test_changed_key_update_key,
        test_verify_silent_reconnect,
        test_verify_timeout_rejects,
        test_verify_always_trust_calls_store,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            print(f"FAIL — {test_fn.__name__}: {exc}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
