---
phase: 04-ssh-host-key-verification
plan: "07"
subsystem: host_key_dialog / connector / main
tags: [security, concurrency, ssh, host-key, thread-safety, fail-closed]
dependency_graph:
  requires: [04-06]
  provides: [thread-safe HostKeyVerifier, fail-closed connector, device_id call-scoped]
  affects: [host_key_dialog.py, connector.py, main.py, tests/test_wiring.py, tests/test_verifier_concurrency.py]
tech_stack:
  patterns: [per-thread dict keyed by threading.get_ident(), threading.Lock, per-device closure, fail-closed security guard]
key_files:
  modified:
    - host_key_dialog.py
    - connector.py
    - main.py
    - tests/test_wiring.py
  created:
    - tests/test_verifier_concurrency.py
decisions:
  - "Use threading.get_ident() as pending-dict key rather than a per-thread local — allows the main-thread slot to look up the record by tid from the signal argument"
  - "Pop the pending entry under lock after event.wait() returns — timeout in one thread cannot clear another thread's record"
  - "Per-device lambda closure in _on_device_selected rather than an explicit class wrapping verify_host_key — minimal code change, no new types"
  - "RuntimeError (not a custom exception) for fail-closed guard — matches existing error-handling in FetchWorker which stringifies all exceptions to the status bar"
metrics:
  duration_seconds: 380
  completed_date: "2026-05-30"
  tasks_completed: 3
  files_changed: 5
---

# Phase 4 Plan 07: Thread-Safe HostKeyVerifier and Fail-Closed Connector Summary

Three HIGH-severity concurrency and fail-open defects from the cross-AI review (04-REVIEWS.md) are now closed: thread-keyed pending dict replaces the shared single-slot, device_id is supplied at the call site via a closure, and `_connect_with_policy` raises `RuntimeError` instead of opening an unverified connection.

## What Was Changed and Why

### 1. `host_key_dialog.py` — Thread-keyed pending state, device_id call-scoped

**Before (broken):** `self._pending` was a single `dict | None` shared across all threads. A second worker calling `verify_host_key` concurrently would overwrite the first's `event` and `result`, cross-contaminating dialog results. `self.device_id` was a shared mutable attribute — set by `main.py` at device-selection time — so a concurrent device switch mid-fetch could make the verifier look up or persist the host key against the wrong device row.

**After (fixed):**

- `self._pending` is now `dict[int, dict]`, keyed by `threading.get_ident()`. Each worker thread writes and reads only its own entry. A timeout or stale signal never touches another thread's record.
- `self._pending_lock = threading.Lock()` guards all reads and writes to the dict.
- `self.device_id` attribute is removed entirely. `verify_host_key` now accepts `device_id` as a **keyword-only** first parameter.
- `host_key_check_requested` signal now carries `tid` (int) as its first argument: `pyqtSignal(int, str, int, str, str, str, str)`.
- `_show_host_key_dialog` accepts `tid` as first param, looks up `self._pending.get(tid)` under lock, and returns early (stale signal guard) if the record is absent.
- `verify_host_key` pops its own entry via `self._pending.pop(tid, None)` under lock after `event.wait()` returns — the local `record` variable is used for result extraction, never `self._pending` after the pop.

### 2. `main.py` — Per-device closure, no shared verifier.device_id

**Before (broken):** `_on_device_selected` called `self._verifier.device_id = device["id"]` before distributing `self._verifier.verify_host_key` to panels. A concurrent fetch from a second panel after a device switch would see a different device_id than the one it was initialized with.

**After (fixed):**

```python
verifier_fn = lambda **kwargs: self._verifier.verify_host_key(
    device_id=device["id"], **kwargs
)
```

Each device selection produces a fresh closure capturing `device["id"]` immutably. All five panels receive the same `verifier_fn` for that selection. No shared mutable state.

### 3. `connector.py` — Fail closed on `verifier_fn=None`

**Before (broken):** `_connect_with_policy` returned a plain `ConnectHandler(**netmiko_kwargs)` when `verifier_fn` was `None`. This silently bypassed `RemoteInHostKeyPolicy` — a MITM-enabling security bypass in any code path that failed to supply a verifier.

**After (fixed):**

```python
if verifier_fn is None:
    raise RuntimeError(
        "Host key verification is required: no verifier_fn supplied to "
        "_connect_with_policy. ..."
    )
```

Tests that intentionally bypass host key verification must pass an explicit stub (e.g. `lambda **kw: "accept_once"`), not `None`. Both docstrings (`_netmiko_device` and `_connect_with_policy`) updated to reflect the fail-closed contract.

### 4. `tests/test_wiring.py` — Updated Test 4 for new API

Test 4 previously set `verifier.device_id = 1` (attribute now removed) and called `verify_host_key` without `device_id`. Updated to:
- Pass `device_id=1` as keyword argument to `verify_host_key`
- Fake dialog slot now accepts `tid` as first argument and uses `verifier._pending_lock` to look up the record by tid

### 5. `tests/test_verifier_concurrency.py` — New adversarial test file

Three tests covering the closed defects:

- **Test 1 — concurrent calls do not cross-write:** Two threads with `device_id=1` and `device_id=2` run simultaneously. Fake slot resolves by tid. `db.store_host_key` is patched to record which device_id each thread stored. Asserts `stored_by_thread[tid1] == 1` and `stored_by_thread[tid2] == 2`.
- **Test 2 — fail-closed connector:** Asserts `_connect_with_policy({"host": "x", "port": 22}, None)` raises `RuntimeError`.
- **Test 3 — keyword-only device_id:** Uses `inspect.signature` to assert `device_id` is `KEYWORD_ONLY`.

## Verification Results

```
=== tests/test_verifier_concurrency.py ===
PASS test_concurrent_calls_do_not_cross_write
PASS test_fail_closed_connector
PASS test_device_id_is_keyword_only
All 3 concurrency / fail-closed tests PASS.

=== tests/test_wiring.py ===
PASS test_set_device_stores_verifier_fn
PASS test_interfaces_run_fetch_passes_verifier_fn
PASS test_verifier_fn_none_does_not_crash
PASS test_connection_status_note_emitted_on_connect_anyway
All 4 wiring tests PASS.
```

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 | ff49cb8 | fix(04-07): thread-keyed HostKeyVerifier pending state and device_id call-scoped |
| 2 | 6a2b193 | fix(04-07): bind device_id at call site, fail closed on None verifier_fn |
| 3 | 75d05bc | test(04-07): adversarial concurrency and fail-closed tests |

## Deviations from Plan

None. Plan executed exactly as written. All changes were targeted edits (CLAUDE.md rule 1 — no whole-file rewrites). No new files added beyond the one specified (`tests/test_verifier_concurrency.py`).

## Known Stubs

None.

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. All changes are within the existing host key verification subsystem. The threat register entries T-04-01, T-04-02, T-04-03, and T-04-04 are now mitigated.

## Self-Check: PASSED

- `host_key_dialog.py` — modified, `threading.get_ident` and `_pending_lock` confirmed present
- `connector.py` — modified, `RuntimeError` and `verifier_fn is None` guard confirmed present
- `main.py` — modified, `device_id=device` closure confirmed present, `self._verifier.device_id` assignment confirmed absent
- `tests/test_wiring.py` — modified, Test 4 uses `device_id=1` keyword arg and tid-aware slot
- `tests/test_verifier_concurrency.py` — created, 201 lines, 3 PASS tests
- Commits ff49cb8, 6a2b193, 75d05bc verified in `git log`
