---
phase: "04"
plan: "03"
subsystem: host-key-dialog
tags: [ssh-01, ssh-03, host-key, threading, qobject, dialogs, security]
dependency_graph:
  requires: [host_keys-table, store_host_key, get_host_key, update_host_key, RemoteInHostKeyPolicy]
  provides: [HostKeyVerifier, FirstConnectDialog, ChangedKeyDialog, host_key_dialog.py]
  affects: [connector.py, panels/base.py, main.py]
tech_stack:
  added: [threading.Event cross-thread sync]
  patterns: [QObject-signal-slot, worker-thread-blocks-main-thread-unblocks, keyword-only-db-calls]
key_files:
  created: [host_key_dialog.py, tests/test_host_key_dialog.py]
  modified: []
decisions:
  - HostKeyVerifier is a QObject (not a QDialog) — it owns the threading.Event and emits a signal; the slot runs on the main thread and shows the dialog
  - verify_host_key() blocks the worker thread via threading.Event.wait(timeout=30); timeout returns "reject" to keep connections safe
  - "always_trust" and "accept_once" (Accept Once) both return "always_trust" to RemoteInHostKeyPolicy — D-01 decision, both paths store the key
  - update_key result remapped to "always_trust" before returning — RemoteInHostKeyPolicy only understands accept_once/always_trust/reject
  - closeEvent guards event is not None — PyQt6 rejects None QCloseEvent; test-only path calls closeEvent(None) to simulate X button
  - DB write (store_host_key / update_host_key) runs on the worker thread after event.set() — SQLite serialized mode is thread-safe
metrics:
  duration_minutes: 60
  completed_date: "2026-05-30"
  tasks_completed: 4
  tasks_total: 4
  files_changed: 2
---

# Phase 4 Plan 03: HostKeyVerifier + SSH-01 First-Connect Dialog + SSH-03 Changed-Key Dialog Summary

## One-liner

`host_key_dialog.py` implements `HostKeyVerifier` (QObject with threading.Event cross-thread sync), `FirstConnectDialog` (SSH-01), and `ChangedKeyDialog` (SSH-03); 8 adversarial tests all pass.

## What Was Built

### Task 1 — `HostKeyVerifier` QObject

`HostKeyVerifier` subclasses `QObject` and owns the cross-thread mechanism:

- `host_key_check_requested` signal (str × 5) — emitted from the worker thread; connected to `_show_host_key_dialog` slot via `Qt.ConnectionType.QueuedConnection` so the slot runs on the main thread
- `verify_host_key(*, hostname, port, key_type, fingerprint, key_blob)` — called from the SSH worker thread:
  1. Calls `db.get_host_key(...)` — silent accept for matching blob (returns `"accept_once"`, no dialog)
  2. For new or changed keys: sets `self._pending = {"event": threading.Event(), "result": None}`, emits signal, blocks via `event.wait(timeout=30)`
  3. Timeout → `"reject"` (safe default)
  4. On result: writes to DB (`store_host_key` / `update_host_key`) then returns result to caller
- `_show_host_key_dialog` slot — runs on main thread; shows appropriate dialog; stores user's choice in `_pending["result"]`; always calls `event.set()` (even on error) to unblock the worker

### Task 2 — `FirstConnectDialog` (SSH-01)

Three-button dialog for first-connection to an unknown host:

| Button | `result_action` | Returned as |
|---|---|---|
| Accept Once | `"always_trust"` | `"always_trust"` (D-01: both paths store key) |
| Always Trust | `"always_trust"` | `"always_trust"` |
| Reject | `"reject"` | `"reject"` |
| X (close) | `"reject"` | `"reject"` |

Displays: hostname, port, key type, SHA256 fingerprint. Layout matches PLAN.md specification.

### Task 3 — `ChangedKeyDialog` (SSH-03)

Warning dialog for a host key mismatch (possible MITM):

| Button | `result_action` | Returned as |
|---|---|---|
| Connect Anyway | `"accept_once"` | `"accept_once"` |
| Update Key | `"update_key"` → remapped | `"always_trust"` |
| Reject | `"reject"` | `"reject"` |
| X (close) | `"reject"` | `"reject"` |

Shows old fingerprint vs new fingerprint clearly. Warning text emphasises MITM risk.

### Task 4 — Adversarial tests (`tests/test_host_key_dialog.py`)

8 standalone tests (no pytest — standalone `if __name__ == "__main__"` runner):

1. `test_first_connect_x_button_rejects` — `closeEvent(None)` → `"reject"`
2. `test_first_connect_accept_once` — `_on_accept_once()` → `"always_trust"`, `_button_clicked=True`
3. `test_changed_key_x_button_rejects` — `closeEvent(None)` → `"reject"`
4. `test_changed_key_connect_anyway` — `_on_connect_anyway()` → `"accept_once"`
5. `test_changed_key_update_key` — `_on_update_key()` → `"update_key"`
6. `test_verify_silent_reconnect` — matching blob → `"accept_once"`, signal NOT emitted
7. `test_verify_timeout_rejects` — `threading.Event.wait` patched to return `False` → `"reject"`, `_pending` cleared
8. `test_verify_always_trust_calls_store` — `"always_trust"` result → `db.store_host_key` called with correct keyword args

All 8 pass.

## Deviations from Plan

### closeEvent(None) guard added

The plan specified `closeEvent(None)` as the test call for simulating the X button. PyQt6 on Windows raises a `TypeError` when `super().closeEvent(None)` is called because `QCloseEvent` cannot be `None`. Added `if event is not None:` guard before the `super()` call in both dialogs. Behaviour is identical in production (Qt always passes a real `QCloseEvent`).

### Test runner: standalone script (not pytest)

The plan specified a standalone script because "no pytest infrastructure yet." However, the test was written to be compatible with the standalone runner as specified. The `isolated_db` fixture is not needed here since no DB writes occur in the dialog/verifier unit tests (DB calls are mocked).

## Commits

| Task | Commit | Message |
|---|---|---|
| 1–4 | `7981932` | feat(04-03): HostKeyVerifier + FirstConnectDialog + ChangedKeyDialog |

## Security Checklist

- [x] `verify_host_key` timeout returns `"reject"` — fail-safe, never silently accepts
- [x] `_show_host_key_dialog` always calls `event.set()` in `finally` — worker never hangs
- [x] `_pending` cleared before any DB write — no stale state for concurrent connections
- [x] `key_blob` not displayed in dialogs — only fingerprint shown to user
- [x] DB writes use keyword-only args — `store_host_key(device_id=..., hostname=..., ...)`
- [x] `update_key` remapped to `"always_trust"` before returning — RemoteInHostKeyPolicy cannot receive internal values

## Self-Check: PASSED

- [x] `host_key_dialog.py` created — `HostKeyVerifier`, `FirstConnectDialog`, `ChangedKeyDialog` all present
- [x] `tests/test_host_key_dialog.py` created — 8 tests all PASS (`PYTHONIOENCODING=utf-8 python tests/test_host_key_dialog.py`)
- [x] Commit `7981932` exists in `git log --oneline`
