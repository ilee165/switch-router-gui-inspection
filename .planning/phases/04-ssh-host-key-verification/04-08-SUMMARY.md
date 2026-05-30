---
phase: 04-ssh-host-key-verification
plan: "08"
subsystem: db, connector, host_key_dialog, tests
tags: [sqlite, foreign-keys, upsert, paramiko, fingerprint, layering, integrity]
requires: ["04-07"]
provides: ["FK-enforcement", "identity-preserving-upsert", "paramiko-fingerprint-compat", "import-boundary-docs", "integrity-test-suite"]
affects: ["db.py", "connector.py", "host_key_dialog.py", "tests/test_host_keys_integrity.py"]
tech-stack:
  added: []
  patterns: ["PRAGMA foreign_keys = ON per-connection", "INSERT ON CONFLICT DO UPDATE", "hasattr-based version fallback", "standalone+pytest dual-mode test runner"]
key-files:
  created: ["tests/test_host_keys_integrity.py"]
  modified: ["db.py", "connector.py", "host_key_dialog.py"]
decisions:
  - "D-07 note timing: Option B (documented best-effort) chosen over Option A (post-_open callback); see D-07 section below"
  - "PRAGMA foreign_keys = ON applied in get_conn on every connection — SQLite resets per-connection so this is the correct location"
  - "store_host_key ON CONFLICT target exactly matches UNIQUE(device_id, hostname, port, key_type) DDL constraint"
metrics:
  duration: "9 minutes"
  completed: "2026-05-30"
  tasks: 3
  files_modified: 3
  files_created: 1
---

# Phase 04 Plan 08: DB Integrity and UX Correctness Fixes Summary

One-liner: SQLite FK enforcement + identity-preserving upsert + Paramiko 2.x fingerprint fallback + import boundary documentation.

## What Was Changed and Why

This plan remediates five defects flagged by the cross-AI review (04-REVIEWS.md) in the Phase 4 SSH host key implementation. None required redesign — all are targeted fixes.

### Task 1: FK enforcement and store_host_key upsert (db.py)

**Problem 1:** `get_conn` did not execute `PRAGMA foreign_keys = ON`. SQLite disables FK enforcement per-connection by default, so the `REFERENCES devices(id)` declaration on `host_keys` was silently unenforced. The `store_host_key` docstring claimed an `IntegrityError` would be raised for non-existent `device_id` values — that claim was inaccurate.

**Fix:** Added `conn.execute("PRAGMA foreign_keys = ON")` in `get_conn` after `row_factory` assignment, with a comment explaining the per-connection reset behavior. The IntegrityError contract is now accurate.

**Problem 2:** `store_host_key` used `INSERT OR REPLACE` which deletes the existing row and inserts a new one. This churns the primary key (new autoincrement id) and resets `added_at` on every reconnect. The SSH-04 audit trail showed a new entry id each time a device reconnected.

**Fix:** Replaced with `INSERT INTO ... ON CONFLICT(device_id, hostname, port, key_type) DO UPDATE SET fingerprint = excluded.fingerprint, key_blob = excluded.key_blob, added_at = CURRENT_TIMESTAMP`. The ON CONFLICT target columns exactly match the `UNIQUE(device_id, hostname, port, key_type)` DDL constraint. The row's primary key is now preserved across updates.

**Problem 3 (belt-and-suspenders):** `delete_device` had a comment incorrectly stating FK enforcement was NOT enabled. Updated to reflect the new reality while keeping the explicit `DELETE FROM host_keys` as defense-in-depth (the FK constraint would block device deletion while host_key rows exist, so the explicit delete runs first).

### Task 2: Paramiko fingerprint fallback and D-07 note (connector.py, host_key_dialog.py)

**Problem:** `missing_host_key` in `RemoteInHostKeyPolicy` used `key.fingerprint` directly. This property was added in Paramiko 3.x. On Paramiko 2.x the attribute does not exist and raises `AttributeError`, crashing the connection attempt silently.

**Fix:** Added a module-level `_compute_fingerprint(key) -> str` helper that:
- Returns `key.fingerprint` when the attribute exists (Paramiko 3.x)
- Falls back to manual SHA256 computation: `hashlib.sha256(key.asbytes()).digest()` encoded as `"SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")` — the `rstrip("=")` matches OpenSSH's unpadded format from `ssh-keygen -l`

`missing_host_key` now calls `_compute_fingerprint(key)` instead of `key.fingerprint`.

**DB import boundary:** Added a comment block near `from db import decrypt_field` documenting the true layering audit boundary:
- ALLOWED: `decrypt_field` (pure crypto helper, no I/O, no DB state)
- FORBIDDEN: PyQt6 / any GUI module
- FORBIDDEN: any host-key DB functions (`store_host_key`, `get_host_key`, `update_host_key`, `delete_host_key`, `get_device_host_keys`) — persistence is the verifier's job

### D-07 Note Timing: Option B (documented best-effort)

**Problem:** The `connection_status_note.emit("Connected (host key mismatch not resolved)")` fires inside `verify_host_key()`, which runs during Paramiko's `missing_host_key()` callback — meaning it fires while `conn._open()` is still executing. SSH authentication (username/password) has not yet completed at this point. The connection could still fail after the note fires.

**Option A (deferred post-_open):** Would require adding an `on_connected` callback kwarg to `_connect_with_policy`, threading it through all six public connector functions (`get_interfaces`, `get_routing_table`, etc.), and updating the main.py closures. This is a cross-cutting change to code that was just stabilised by 04-07 (concurrent pending state, thread-keyed records, fail-closed guard). The risk of introducing a new concurrency bug outweighs the benefit for this milestone.

**Option B chosen:** Kept the emit in place, added a detailed comment explaining the best-effort timing and why Option A was deferred. The note is always overwritten by FetchWorker's definitive success or error status, so the user is never permanently misled — the worst case is a brief "Connected (host key mismatch not resolved)" that is replaced by an auth error message within seconds.

### Task 3: Integrity tests (tests/test_host_keys_integrity.py)

New test file with three tests covering the Task 1 and Task 2 fixes:

- **test_fk_enforced**: calls `store_host_key` with `device_id=999999` (does not exist), asserts `sqlite3.IntegrityError` is raised
- **test_upsert_preserves_pk**: calls `store_host_key` twice with the same tuple and different fingerprints, asserts row id is unchanged and fingerprint is the new value, and `get_device_host_keys` returns exactly one row
- **test_connector_import_boundary**: reads `connector.py` source, asserts no `import PyQt6` / `from PyQt6` in non-comment lines, no host-key DB function calls, and `from db import decrypt_field` is present

The file is dual-mode: works as a pytest file (uses `isolated_db` from conftest.py) and as a standalone script (`python tests/test_host_keys_integrity.py`).

## Files Modified

| File | Change |
|------|--------|
| `db.py` | `get_conn`: added `PRAGMA foreign_keys = ON`; `store_host_key`: INSERT OR REPLACE → ON CONFLICT DO UPDATE; `delete_device`: updated comment |
| `connector.py` | Added `hashlib` import; added `_compute_fingerprint()` helper; `missing_host_key` uses `_compute_fingerprint`; added DB import boundary comment block |
| `host_key_dialog.py` | Added Option B rationale comment at D-07 emit site |
| `tests/test_host_keys_integrity.py` | New file — 3 integrity tests (FK, upsert PK, import boundary) |

## Verification Results

```
python tests/test_host_keys_integrity.py
  PASS test_fk_enforced
  PASS test_upsert_preserves_pk
  PASS test_connector_import_boundary
  Results: 3 passed, 0 failed

python -m pytest tests/test_host_keys_db.py -v
  7 passed (no regressions — ON CONFLICT is behaviorally equivalent to
  INSERT OR REPLACE for the uniqueness test; upsert test now exercises
  identity preservation)

python -m pytest tests/test_verifier_concurrency.py -v
  3 passed (no regressions from connector.py changes)

python -c "import db, connector, host_key_dialog"
  imports OK
```

## Commits

| Hash | Message |
|------|---------|
| `cbba434` | fix(04-08): enable FK enforcement and upsert store_host_key to preserve PK |
| `e7a5ad3` | fix(04-08): Paramiko fingerprint fallback and D-07 note timing |
| `ffb52b3` | test(04-08): FK enforcement, upsert PK preservation, and import boundary tests |

## Deviations from Plan

### Auto-fixed issues

None.

### Planned deviations

**1. store_host_key docstring does not use the phrase "INSERT OR REPLACE"**

The Task 1 automated verify check asserted `'INSERT OR REPLACE' not in inspect.getsource(db.store_host_key)`. The initial docstring explained the old behavior by naming it — "unlike INSERT OR REPLACE which deletes and reinserts". The phrase was rewritten to "unlike the delete-and-reinsert strategy" to satisfy the test without losing the conceptual explanation.

**2. D-07 Option B chosen**

As documented above — Option A was evaluated and rejected due to cross-cutting complexity risk. Option B is explicitly permitted by the plan ("acceptable if Option A adds complexity that risks introducing new bugs") and is documented in the SUMMARY and in an inline code comment.

**3. Test file includes sys.path insertion for standalone mode**

The plan specified a standalone runner (`python tests/test_host_keys_integrity.py`). On Windows, running from the repo root does not automatically add the project root to `sys.path`, so `import db` would fail. Added `sys.path.insert(0, str(Path(__file__).parent.parent))` guarded by a presence check — this only affects standalone execution; pytest handles paths via conftest.py.

**4. Windows file-lock workaround in standalone runner**

SQLite on Windows holds a file lock until process exit. Using a single tempfile and deleting+recreating it between tests raises `PermissionError`. Fixed by using a fresh `NamedTemporaryFile` per test — each test gets its own isolated DB file, consistent with the test isolation model.

## Known Stubs

None. All changes are functional fixes and test additions. No placeholder data or UI stubs introduced.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced beyond those in the plan's threat model.

## Self-Check

Files created:
- [x] `tests/test_host_keys_integrity.py` — FOUND

Commits:
- [x] `cbba434` — FOUND (git log confirmed)
- [x] `e7a5ad3` — FOUND (git log confirmed)
- [x] `ffb52b3` — FOUND (git log confirmed)

## Self-Check: PASSED
