---
phase: 04-ssh-host-key-verification
fixed_at: 2026-05-31T04:35:00Z
review_path: .planning/phases/04-ssh-host-key-verification/04-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-05-31T04:35:00Z
**Source review:** `.planning/phases/04-ssh-host-key-verification/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (3 Critical + 6 Warning)
- Fixed: 9
- Skipped: 0

---

## Fixed Issues

### CR-01: test_host_key_dialog.py tests 6/7/8 broken against current API

**Files modified:** `tests/test_host_key_dialog.py`
**Commit:** `771d169`
**Applied fix:**
- Test 6: removed `verifier.device_id = _DEV_ID` (no longer an instance attribute), added `device_id=_DEV_ID` keyword arg to `verify_host_key()` call.
- Test 7: same device_id fix; replaced `assert verifier._pending is None` with `assert verifier._pending == {}` to match the current `dict[int, dict]` type that is never `None`.
- Test 8: same device_id fix; replaced `verifier._pending["result"] = "always_trust"` (wrong dict level) with a tid-keyed lookup via `threading.get_ident()` and `verifier._pending_lock` to write into the correct nested record.

---

### CR-02: test_host_key_policy.py Test 6 asserts fail-open bug as correct

**Files modified:** `tests/test_host_key_policy.py`
**Commit:** `2bffb65`
**Applied fix:** Renamed `test_no_verifier_skips_policy` to `test_no_verifier_raises_runtime_error` and rewrote its body to assert `pytest.raises(RuntimeError, match="Host key verification is required")`. The old test encoded the security bypass as expected behavior; the new test documents and enforces the correct fail-closed contract. All mock setup for the old `ConnectHandler` path removed.

---

### CR-03: Genie path bypasses host key verification

**Files modified:** `connector.py`
**Commit:** `1723b48`
**Applied fix:** Changed all six public connector functions (`get_interfaces`, `get_routing_table`, `get_bgp_neighbors`, `get_ospf_neighbors`, `get_arp_table`, `get_mac_table`) from `if GENIE_AVAILABLE:` to `if GENIE_AVAILABLE and verifier_fn is None:`. When `verifier_fn` is provided, the Genie path is skipped and the Netmiko path (with `RemoteInHostKeyPolicy`) is used, closing the MITM window on Linux/Mac deployments with pyATS installed. Added explanatory comment in `get_interfaces` docstring; cross-reference comment in the other five functions.

---

### WR-01: update_host_key returns silently on 0-row match

**Files modified:** `db.py`, `host_key_dialog.py`
**Commit:** `9434b99`
**Applied fix:**
- `db.update_host_key`: changed return type from `None` to `int`; captures cursor from `conn.execute()` and returns `cur.rowcount` (0 or 1). Updated docstring to document the return value contract.
- `host_key_dialog.py`: captures `rows_updated = db.update_host_key(...)` and when `rows_updated == 0`, falls back to `db.store_host_key(...)` to insert a fresh row rather than silently trusting an unupdated key. The `result = "always_trust"` remap now fires after the fallback store, not just after the original update.

---

### WR-02: conn.key_policy relies on undocumented Netmiko internals

**Files modified:** `connector.py`
**Commit:** `3511948`
**Applied fix:** Added a comment block immediately before `conn.key_policy = policy` in `_connect_with_policy` explaining why `conn.key_policy` and `conn._open()` are used (no public Netmiko API for custom `MissingHostKeyPolicy` injection). Added `assert conn.key_policy is policy` with a descriptive error message so that a Netmiko version change that breaks the assignment fails loudly at connection time (fail-closed) rather than silently bypassing verification.

---

### WR-03: BasePanel._start_worker overwrites thread without guarding double-start

**Files modified:** `panels/base.py`
**Commit:** `8b7ffee`
**Applied fix:** Added guard at the top of `_start_worker`:
```python
if self._thread is not None and self._thread.isRunning():
    return
```
A duplicate Fetch click while a fetch is in progress is now silently dropped. Added explanatory comment describing the two failure modes this prevents (interleaved table data, premature button re-enable).

---

### WR-04: test_host_keys_db.py Test 3 comment contradicts db.py

**Files modified:** `tests/test_host_keys_db.py`
**Commit:** `d6731ca`
**Applied fix:** Replaced the stale docstring in `test_cascade_delete_removes_host_keys` that falsely stated `PRAGMA foreign_keys is NOT enabled`. New docstring accurately states that `db.py` enables `PRAGMA foreign_keys = ON` in `get_conn()`, explains the belt-and-suspenders explicit `DELETE` pattern and the `IntegrityError` contract it creates, and describes what regression the test catches.

---

### WR-05: _show_host_key_dialog does not validate event before calling set()

**Files modified:** `host_key_dialog.py`
**Commit:** `20ab939`
**Applied fix:** Wrapped `record["event"].set()` in an `if record is not None:` guard and added a comment explaining that `threading.Event.set()` is idempotent — safe to call even if the worker already timed out and the event is in the signaled state. Also clarified why the guard is defensive-only (the early-return at line 243 already ensures `record is not None` when the `finally` block executes).

---

### WR-06: _genie_fetch swallows credential decryption failures

**Files modified:** `connector.py`
**Commit:** `c5bad3e`
**Applied fix:** Added `import logging` and `_log = logging.getLogger(__name__)` at the module level. Changed `except Exception:` in `_genie_fetch` to `except Exception as exc:` and added `_log.debug(...)` before `return None`, logging the device hostname, command, and exception. This makes credential decryption failures and Genie-specific errors visible in application logs at DEBUG level rather than being silently discarded and confusingly re-surfaced as Netmiko auth errors.

---

## Skipped Issues

None — all 9 in-scope findings were successfully fixed.

---

_Fixed: 2026-05-31T04:35:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
