---
phase: 04-ssh-host-key-verification
reviewed: 2026-05-30T14:09:39Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - connector.py
  - db.py
  - host_key_dialog.py
  - main.py
  - tests/test_host_keys_integrity.py
  - tests/test_verifier_concurrency.py
  - tests/test_wiring.py
findings:
  critical: 2
  warning: 5
  info: 2
  total: 9
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-05-30T14:09:39Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

This review covers Phase 4 plans 04-07 and 04-08: the thread-safety rewrite of `HostKeyVerifier`, the fail-closed connector guard, per-device closure binding in `main.py`, SQLite FK enforcement, identity-preserving upsert, and the Paramiko 2.x fingerprint fallback. The core concurrency redesign (per-thread `_pending` dict keyed by `threading.get_ident()`, `_pending_lock`, keyword-only `device_id`) is structurally sound. The fail-closed `RuntimeError` guard in `_connect_with_policy` is correctly placed.

Two critical defects were found: the Genie SSH path has no host key verification at all, and the `update_host_key` DB error handler silently remaps `result` to `"always_trust"` even when the DB write failed, reporting a successful trust establishment that did not happen. Five warnings cover a tid-reuse race window, a misleading migration error message, test coverage gaps, and a conftest isolation asymmetry. Two info items cover the `print()` debug logging and a minor documentation gap.

---

## Critical Issues

### CR-01: Genie connection path completely bypasses host key verification

**File:** `connector.py:257-260` (and parallel calls in `get_routing_table`, `get_bgp_neighbors`, `get_ospf_neighbors`, `get_arp_table`, `get_mac_table`)

**Issue:** Every public connector function attempts the Genie path first (`if GENIE_AVAILABLE: result = _genie_fetch(...)`). `_genie_fetch` uses pyATS's own SSH stack — it never installs `RemoteInHostKeyPolicy` and never calls `verifier_fn`. A MITM attacker on a Linux/Mac host where Genie is available can present a forged host key and the connection proceeds silently without showing the user a dialog or consulting the stored key DB. The comment at line 255 acknowledges this ("Host key verification applies to the Netmiko path only") but frames it as a documentation note rather than a security limitation. On any deployment where `GENIE_AVAILABLE=True`, SSH-01, SSH-02, and SSH-03 provide zero protection.

This is not new code introduced in Phase 4, but Phase 4 introduced `RemoteInHostKeyPolicy` as the host key security mechanism and explicitly documents it as the verification layer — the Genie bypass now contradicts that security guarantee in a way that is worse than before Phase 4 existed.

**Fix:** Either (a) disable the Genie path when a `verifier_fn` is provided (Netmiko path is then used, which runs `RemoteInHostKeyPolicy`), or (b) add a Genie-specific known-hosts check before calling `_genie_fetch`. Option (a) is lower risk:

```python
def get_interfaces(device: dict, session_key: bytes, verifier_fn=None) -> dict:
    # Genie path bypasses RemoteInHostKeyPolicy — skip it when a verifier is
    # in use so that host key verification is always enforced.
    if GENIE_AVAILABLE and verifier_fn is None:
        result = _genie_fetch(device, "show interfaces", session_key)
        if result is not None:
            return {"source": "genie", "data": result}
    kwargs = _netmiko_device(device, session_key)
    with _connect_with_policy(kwargs, verifier_fn) as conn:
        ...
```

Note: this also means the Genie path is still reachable from code that passes `verifier_fn=None` — but `_connect_with_policy` already rejects `None`, so any caller with a real session must supply a verifier. If the intent is to eliminate unverified connections entirely, the condition should be simply `if GENIE_AVAILABLE:` → removed, forcing all connections through Netmiko+policy.

---

### CR-02: `update_host_key` silently remaps result to "always_trust" even when DB write failed

**File:** `host_key_dialog.py:199-213`

**Issue:** When the user clicks "Update Key" in `ChangedKeyDialog`, `result` is `"update_key"`. The code at lines 199-213 attempts `db.update_host_key(...)` and then unconditionally remaps `result = "always_trust"` at line 213 — even when the `except sqlite3.IntegrityError` branch caught an exception at line 209. The sequence is:

```python
elif result == "update_key":
    try:
        db.update_host_key(...)
    except sqlite3.IntegrityError as exc:
        print(f"[HostKeyVerifier] update_host_key failed: {exc}")  # DB write FAILED
    # Remap to "always_trust" — always executes, even after DB failure
    result = "always_trust"
```

After a DB failure the key is NOT updated in the DB, but `verify_host_key` returns `"always_trust"` to `RemoteInHostKeyPolicy`, which allows the connection. More critically, the user clicked "Update Key" expecting the new key to be stored — it was not, but the system silently acts as if trust was established. On the next connection, the stored key still mismatches and the `ChangedKeyDialog` will appear again, which may confuse the user. There is no user-visible error.

This is distinct from the `store_host_key` failure path (lines 194-197) which correctly prints a log message and falls through to returning `"reject"`-or-`"always_trust"` based on the result variable already set. The `update_key` path uniquely conflates "attempted update" with "connection allowed" without surfacing the failure.

**Fix:** Move the remap outside the `try/except` and only remap on success, or remap unconditionally but add a signal/status emit so the user knows the DB write failed:

```python
elif result == "update_key":
    db_updated = False
    try:
        db.update_host_key(
            device_id=device_id,
            hostname=hostname,
            port=port,
            key_type=key_type,
            fingerprint=fingerprint,
            key_blob=key_blob,
        )
        db_updated = True
    except sqlite3.IntegrityError as exc:
        print(f"[HostKeyVerifier] update_host_key failed: {exc}")
    # Always allow the connection — but emit a status note if DB write failed
    result = "always_trust"
    if not db_updated:
        self.connection_status_note.emit(
            "Connected but host key could not be saved (DB error — check logs)"
        )
```

---

## Warnings

### WR-01: Thread ID reuse creates a low-probability stale-signal window

**File:** `host_key_dialog.py:129-151`

**Issue:** `threading.get_ident()` returns an OS-assigned integer that can be reused after a thread terminates. The signal `host_key_check_requested` is delivered via `QueuedConnection` — it is queued in the main event loop and delivered asynchronously. The window: (1) Worker thread A emits the signal and then raises an unhandled exception that terminates the thread; (2) the OS reuses A's tid for new thread B before the main event loop delivers the queued signal; (3) thread B calls `verify_host_key`, adds its own `_pending[tid]` entry; (4) the main thread delivers the signal for A's situation, finds B's `_pending[tid]` record, shows A's dialog, and sets B's event.

Result: thread B receives A's dialog result (wrong situation, possibly wrong device). In practice this requires extremely tight timing and is unlikely in a GUI app with human interaction delays. However, it is a correctness gap that the current implementation does not guard against.

**Fix:** Include a unique nonce in the pending record (e.g., `uuid.uuid4()`) and pass it through the signal so `_show_host_key_dialog` can cross-check that the record it finds matches the signal it received. Alternatively, replace the tid key with a monotonically incrementing counter generated under the lock.

```python
import uuid

# In verify_host_key:
nonce = str(uuid.uuid4())
with self._pending_lock:
    self._pending[tid] = {"event": event, "result": None, "nonce": nonce, ...}
self.host_key_check_requested.emit(tid, nonce, hostname, ...)

# In _show_host_key_dialog (add nonce param to signal):
with self._pending_lock:
    record = self._pending.get(tid)
if record is None or record.get("nonce") != nonce:
    return  # stale signal — different thread reused this tid
```

---

### WR-02: Migration error message always reports "some" passwords even when count is known

**File:** `main.py:79-87`

**Issue:** The error handler for `migrate_plaintext_passwords` uses `locals().get("count", "some")` to report how many passwords failed:

```python
try:
    count = db.migrate_plaintext_passwords(session_key)
except Exception as exc:
    _migrated = locals().get("count", "some")
    QMessageBox.warning(self, "Migration Warning",
        f"Could not encrypt {_migrated} device password(s). ...")
```

`migrate_plaintext_passwords` raises during execution, so the `count =` assignment never completes. `locals().get("count", "some")` will always return `"some"`. The message will always read "Could not encrypt some device password(s)" regardless of how many devices were in the DB. While this is not a data-loss risk (login still proceeds and the user sees the warning), the message is always inaccurate and provides no actionable information about scope.

**Fix:** Remove the `locals()` lookup and use the fixed fallback directly, or restructure to catch after a partial count is available:

```python
try:
    db.migrate_plaintext_passwords(session_key)
except Exception as exc:
    QMessageBox.warning(
        self,
        "Migration Warning",
        f"Could not migrate one or more device passwords to encrypted storage. "
        f"Affected devices may fail to connect.\n\nDetail: {exc}"
    )
```

---

### WR-03: `test_verifier_fn_none_does_not_crash` tests a stub, not the real risk

**File:** `tests/test_wiring.py:118-134`

**Issue:** Test 3 verifies that `_StubPanel._run_fetch()` with `verifier_fn=None` does not crash. `_StubPanel._run_fetch` is:

```python
def _run_fetch(self):
    self._captured_args = (self._device, self._session_key, self._verifier_fn)
```

It never calls `_connect_with_policy`. The test passes trivially because the stub never exercises the fail-closed guard. The real failure mode — a real panel calling `connector.get_interfaces(device, session_key, None)` which then hits `_connect_with_policy(kwargs, None)` → `RuntimeError` — is untested. There is no test that starts a real fetch worker on a real panel with `verifier_fn=None` and asserts `RuntimeError` is propagated as a status bar error.

**Fix:** Add a test using `InterfacesPanel` (not `_StubPanel`) with `verifier_fn=None`, patching the connector to verify `RuntimeError` is raised and reaches `FetchWorker.error` signal:

```python
def test_none_verifier_fn_reaches_error_signal():
    panel = InterfacesPanel()
    panel.set_device(_DEVICE, session_key=_SESSION_KEY, verifier_fn=None)
    errors = []
    panel.status_message.connect(lambda m: errors.append(m))

    with mock.patch("connector.get_interfaces",
                    side_effect=RuntimeError("Host key verification is required: ...")):
        # _start_worker will call connector.get_interfaces(device, key, None)
        # FetchWorker catches RuntimeError and emits error signal
        panel._run_fetch()
        # pump event loop...
    assert any("RuntimeError" in e or "verification" in e.lower() for e in errors)
```

---

### WR-04: `_pending_lock` not held when writing `record["result"]` and calling `record["event"].set()`

**File:** `host_key_dialog.py:261-270`

**Issue:** In `_show_host_key_dialog`, the lock is acquired to retrieve `record`, then released before entering the `try` block. `record["result"] = dialog.result_action` (line 261) and `record["event"].set()` (line 270) execute without the lock held. This is safe *only* because the worker thread reads `record.get("result")` exclusively after `event.wait()` returns, and `event.set()` provides a happens-before memory barrier via CPython's threading.Event implementation.

However, this is a subtle concurrency contract with no in-code documentation of why it is safe. A future maintainer could easily introduce a second read of `record["result"]` before `event.wait()` returns (e.g., in a timeout-handling branch) and create a real race. The lock should either be re-acquired when writing the result, or a clear comment should explain why the lock is intentionally not held.

**Fix (documentation):** Add a comment at the point of lock release:

```python
with self._pending_lock:
    record = self._pending.get(tid)
# Lock released intentionally before dialog.exec() — holding it during a
# blocking modal dialog would deadlock the worker (worker blocks on event.wait;
# event.set is called here; if we held the lock, the worker's lock acquisition
# after event.wait would deadlock).
# SAFETY: record["result"] is written only by this slot (main thread) and
# read only by the worker after event.wait() returns. threading.Event.set()
# provides the required memory visibility barrier between the write and the read.
```

---

### WR-05: `conftest.py` `isolated_db` fixture does not reset `_DUMMY_HASH`

**File:** `tests/conftest.py` / `db.py:253`

**Issue:** `_DUMMY_HASH` is computed at module import time with `bcrypt.hashpw(b"dummy", bcrypt.gensalt())`. This is a module-level constant — it is computed once and reused across all `verify_user` calls. This is correct by design (it is the timing-equalization hash). However, `conftest.py`'s `isolated_db` fixture monkeypatches `db.DB_PATH` but does not reset other module-level state in `db.py`. If any test modifies `db._DUMMY_HASH` (intentionally or by accident), all subsequent tests in the session are affected.

More concretely: no current test modifies `_DUMMY_HASH`, so this is a latent risk rather than an active bug. But the fixture's docstring claims it isolates "the entire test session for that test function" — that claim is only accurate for DB state, not for module-level Python state.

**Fix:** This is low priority given no current test touches `_DUMMY_HASH`. Document the limitation in the conftest docstring:

```python
# NOTE: isolated_db redirects DB_PATH and reinitializes the schema.
# It does NOT reset other db.py module-level state (e.g., _DUMMY_HASH).
# Tests that modify db module attributes must restore them manually.
```

---

## Info

### IN-01: `print()` used for error logging in HostKeyVerifier

**File:** `host_key_dialog.py:197, 210, 265`

**Issue:** Three error paths use `print(f"[HostKeyVerifier] ...")` to report DB write failures and dialog construction errors. In production, this output goes to stdout, which is not visible to the end user and is not collected by any logging infrastructure. If the user runs the app from a desktop shortcut (no terminal), these messages are silently lost. The failure at line 210 (`update_host_key failed`) is the most consequential because it is paired with CR-02.

**Fix:** Replace with `import logging; logger = logging.getLogger(__name__)` and use `logger.error(...)`. This is a one-line change per call site and integrates with Python's standard logging pipeline so the messages can be captured by future log handlers.

---

### IN-02: `_genie_testbed` does not thread `verifier_fn` — no connector docstring note

**File:** `connector.py:147-179`

**Issue:** `_genie_testbed` builds the pyATS testbed dict. There is a docstring note on `get_interfaces` (line 254-255) about the Genie bypass, but `_genie_testbed` itself has no comment explaining that it provides no host key callback mechanism. This is a documentation gap that will make future maintainers unaware of why adding host key support to the Genie path would require a different approach (pyATS uses its own transport layer, not Paramiko's policy hook).

**Fix:** Add a one-line comment to `_genie_testbed`:

```python
def _genie_testbed(device: dict, session_key: bytes) -> dict:
    """Build minimal pyATS testbed dict for a single device, decrypting credentials.

    NOTE: pyATS uses its own SSH transport — RemoteInHostKeyPolicy cannot be
    injected here. Host key verification is skipped on the Genie path. See
    get_interfaces() docstring for the security implication.
    """
```

---

_Reviewed: 2026-05-30T14:09:39Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
