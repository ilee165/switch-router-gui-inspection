"""tests/test_verifier_concurrency.py — Adversarial concurrency and fail-closed tests.

Covers the three HIGH-severity defects fixed in plan 04-07:
  1. Concurrent verify_host_key calls for different device_ids must not cross-write
     each other's pending state or DB result (T-04-01, T-04-02).
  2. connector._connect_with_policy must raise RuntimeError when verifier_fn is None
     (T-04-03 — fail closed, no silent ConnectHandler fallback).
  3. device_id must be a KEYWORD_ONLY parameter on verify_host_key (enforces the
     call-site closure pattern in main.py and prevents positional accidental omission).

No real devices or network connections are used.

Run:
    python tests/test_verifier_concurrency.py
All 3 tests print PASS on success.
"""

from __future__ import annotations

import inspect
import sys
import os
import threading
import time
import unittest.mock as mock

# ── Ensure project root is importable ─────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── QApplication must exist before any Qt widget is instantiated ──────────────
from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

# ── Imports under test ────────────────────────────────────────────────────────
from host_key_dialog import HostKeyVerifier
import connector


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — Concurrent calls do not cross-write device_id or pending state
# ─────────────────────────────────────────────────────────────────────────────

def test_concurrent_calls_do_not_cross_write():
    """Two simultaneous verify_host_key calls with different device_ids must each
    store their own device_id in the DB — no cross-contamination between threads.

    Setup:
    - Both threads arrive as "new" (no stored key → situation="new").
    - Fake slot resolves by tid, sets result="always_trust" so the DB write fires.
    - db.store_host_key is patched to record which device_id each call stored,
      keyed by the calling thread's id.
    - After both threads finish, assert device_id 1 went to thread-1 and 2 to thread-2.
    """
    verifier = HostKeyVerifier()

    # Track which device_id was stored by which thread.
    stored_by_thread: dict[int, int] = {}
    stored_lock = threading.Lock()

    def _fake_store_host_key(*, device_id, hostname, port, key_type, fingerprint, key_blob):
        tid = threading.get_ident()
        with stored_lock:
            stored_by_thread[tid] = device_id

    # Slot: receives tid from signal, resolves _pending entry, sets result.
    # Must accept all 7 signal arguments: (tid, hostname, port, key_type, fp, blob, situation).
    def _fake_show_dialog(tid, hostname, port, key_type, fingerprint, key_blob, situation):
        with verifier._pending_lock:
            record = verifier._pending.get(tid)
        if record is not None:
            record["result"] = "always_trust"
            record["event"].set()

    verifier.host_key_check_requested.connect(_fake_show_dialog)

    # Both threads will be tracked so we can assert the correct mapping.
    thread_ids: dict[str, int] = {}
    thread_ids_lock = threading.Lock()

    result_holder: dict[str, str] = {}

    def _worker(device_id: int, label: str):
        with thread_ids_lock:
            thread_ids[label] = threading.get_ident()
        r = verifier.verify_host_key(
            device_id=device_id,
            hostname="10.0.0.1",
            port=22,
            key_type="ssh-ed25519",
            fingerprint=f"SHA256:fp{device_id}",
            key_blob=f"BLOB{device_id}",
        )
        result_holder[label] = r

    with mock.patch("db.get_host_key", return_value=None), \
         mock.patch("db.store_host_key", side_effect=_fake_store_host_key), \
         mock.patch("db.update_host_key"):

        t1 = threading.Thread(target=_worker, args=(1, "t1"), daemon=True)
        t2 = threading.Thread(target=_worker, args=(2, "t2"), daemon=True)

        t1.start()
        t2.start()

        # Pump the Qt event loop while both workers block on threading.Event.
        # The queued signals delivering _fake_show_dialog run here.
        deadline = time.monotonic() + 10.0
        while (t1.is_alive() or t2.is_alive()) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)

        t1.join(timeout=1.0)
        t2.join(timeout=1.0)

    assert not t1.is_alive(), "Thread t1 did not finish — possible deadlock"
    assert not t2.is_alive(), "Thread t2 did not finish — possible deadlock"

    assert result_holder.get("t1") == "always_trust", (
        f"t1 expected 'always_trust', got {result_holder.get('t1')!r}"
    )
    assert result_holder.get("t2") == "always_trust", (
        f"t2 expected 'always_trust', got {result_holder.get('t2')!r}"
    )

    # The critical cross-contamination check: each thread must have stored its
    # own device_id, not the other thread's.
    tid1 = thread_ids.get("t1")
    tid2 = thread_ids.get("t2")

    assert tid1 in stored_by_thread, "t1 did not call db.store_host_key at all"
    assert tid2 in stored_by_thread, "t2 did not call db.store_host_key at all"

    assert stored_by_thread[tid1] == 1, (
        f"Thread t1 (device_id=1) stored device_id={stored_by_thread[tid1]} — cross-write detected!"
    )
    assert stored_by_thread[tid2] == 2, (
        f"Thread t2 (device_id=2) stored device_id={stored_by_thread[tid2]} — cross-write detected!"
    )

    print("PASS test_concurrent_calls_do_not_cross_write")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — Fail-closed connector: verifier_fn=None raises RuntimeError
# ─────────────────────────────────────────────────────────────────────────────

def test_fail_closed_connector():
    """_connect_with_policy(kwargs, None) must raise RuntimeError.

    The old code returned a plain ConnectHandler when verifier_fn was None,
    silently bypassing host key verification. The fix raises RuntimeError so
    the security bypass is impossible in production paths.
    """
    raised = False
    try:
        connector._connect_with_policy({"host": "x", "port": 22}, None)
    except RuntimeError:
        raised = True
    except Exception as exc:
        raise AssertionError(
            f"Expected RuntimeError when verifier_fn=None, got {type(exc).__name__}: {exc}"
        ) from exc

    assert raised, "_connect_with_policy(kwargs, None) did not raise RuntimeError"
    print("PASS test_fail_closed_connector")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — device_id is KEYWORD_ONLY on verify_host_key
# ─────────────────────────────────────────────────────────────────────────────

def test_device_id_is_keyword_only():
    """verify_host_key must declare device_id as a KEYWORD_ONLY parameter.

    This enforces the call-site closure pattern — callers cannot accidentally
    supply device_id positionally or omit it without a TypeError at call time.
    """
    sig = inspect.signature(HostKeyVerifier.verify_host_key)
    params = sig.parameters

    assert "device_id" in params, (
        "device_id not found in verify_host_key signature at all"
    )

    param = params["device_id"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
        f"device_id kind is {param.kind.name!r}; expected KEYWORD_ONLY. "
        "It must not be positional — callers must supply it by name."
    )
    print("PASS test_device_id_is_keyword_only")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_concurrent_calls_do_not_cross_write()
    test_fail_closed_connector()
    test_device_id_is_keyword_only()
    print("\nAll 3 concurrency / fail-closed tests PASS.")
