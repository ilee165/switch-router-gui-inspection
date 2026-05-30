---
phase: "04"
plan: "05"
subsystem: device-manager-ui
tags: [ssh-keys, qtabwidget, device-manager, ui, ssh-04]
dependency_graph:
  requires: [host_keys-table, get_device_host_keys, delete_host_key]
  provides: [SSH-04-tab, DeviceManagerDialog-ssh-tab]
  affects: [device_manager.py]
tech_stack:
  added: []
  patterns: [QTabWidget, QTableWidget, UserRole-keyed-delete, isHidden-visibility-check]
key_files:
  created: [tests/test_ssh_keys_tab.py]
  modified: [device_manager.py]
decisions:
  - QTabWidget wraps only the right-hand panel (form + SSH Keys) — left list stays outside
  - key_blob NOT displayed in table — only key_type, fingerprint, added_at (security by design)
  - Key ID stored in column 0 via UserRole — avoids second DB query on delete without exposing raw id in UI
  - isHidden() used in tests instead of isVisible() — dialog not .show()ed in tests so isVisible() checks full parent chain
metrics:
  duration_minutes: 45
  completed_date: "2026-05-30"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
---

# Phase 4 Plan 05: SSH Keys Tab in DeviceManagerDialog (SSH-04) Summary

## One-liner

`DeviceManagerDialog` right panel wrapped in `QTabWidget` (Details + SSH Keys tabs); `_load_ssh_keys`, `_delete_host_key`, and `_refresh_list` wired to the host_keys DB; 6 adversarial pytest tests all pass.

## What Was Built

### Task 1 — Wrap right panel in QTabWidget (`device_manager.py`)

The existing right-hand form (name, IP, platform, etc.) was wrapped in a `QTabWidget` under a new "Details" tab. A second "SSH Keys" tab was added alongside it. The outer `right_layout` now contains only the `QTabWidget`; all form widgets moved into the Details tab's interior layout. No functional change to device add/edit/delete — only the container changed.

New SSH Keys tab layout:
- `_ssh_empty_label` — `QLabel("No stored host keys for this device.")` shown when table is empty
- `_ssh_table` — `QTableWidget` with columns: `Key Type`, `Fingerprint`, `Added`
- `_btn_delete_ssh_key` — styled delete button beneath the table

### Task 2 — Populate SSH Keys tab + Delete (`device_manager.py`)

Three methods added:

| Method | Behaviour |
|---|---|
| `_load_ssh_keys(device_id)` | Clears table, fetches `db.get_device_host_keys(device_id=...)`, shows rows or empty-state label. Stores key ID via `UserRole` in column 0 for delete. |
| `_delete_host_key()` | Reads `UserRole` ID from selected row, shows confirmation dialog with fingerprint, calls `db.delete_host_key(key_id=...)`, reloads table. |
| `_refresh_list()` | Extended: resets `_current_device_id = None`, clears table to 0 rows, hides label. |

`_on_device_selected` now calls `_load_ssh_keys(device_id)` when a device is selected in the list.

Error contract: if `db.get_device_host_keys` raises, `QMessageBox.warning` is shown and empty-state label is displayed — no crash.

### Task 3 — Adversarial pytest tests (`tests/test_ssh_keys_tab.py`)

6 tests using `isolated_db` fixture and a per-test `DeviceManagerDialog` instance (not shown — methods called directly):

1. `test_empty_device_shows_placeholder` — `_ssh_empty_label` not hidden, table hidden, rowCount=0 with no keys
2. `test_device_with_keys_populates_table` — 2 keys → table not hidden, label hidden, correct key_type/fingerprint in columns
3. `test_delete_removes_row_from_table_and_db` — delete removes row from table and from `db.get_device_host_keys`
4. `test_delete_with_no_selection_does_not_crash` — no selection → no exception (QMessageBox.information shown)
5. `test_refresh_list_clears_ssh_tab` — `_refresh_list()` resets table to 0 rows and `_current_device_id` to `None`
6. `test_key_id_stored_in_userrole` — column 0 `UserRole` holds the correct integer key ID

All 6 tests pass.

## Deviations from Plan

### Test assertions: isHidden() instead of isVisible()

The plan specified `isVisible()` assertions. `isVisible()` in Qt returns `True` only when the widget and its entire parent chain are visible. Since the test fixture creates a `DeviceManagerDialog` without `.show()`, all widgets report `isVisible() == False` regardless of their own state. Assertions updated to use `not widget.isHidden()` / `widget.isHidden()` — these check only the widget's own visibility flag, which is what `setVisible()` actually sets.

## Commits

| Task | Commit | Message |
|---|---|---|
| 1 | `3eacbf3` | feat(04-05): wrap DeviceManagerDialog right panel in QTabWidget |
| 2 | `58470aa` | feat(04-05): populate SSH Keys tab and implement Delete |
| 3 | `fb9a4ad` | test(04-05): adversarial tests for SSH Keys tab — 6 tests, all pass |

## Security Checklist

- [x] `key_blob` not shown in table — only `key_type`, `fingerprint`, `added_at` exposed in UI
- [x] Delete uses `key_id` from `UserRole` data — not constructed from user-visible text
- [x] `db.delete_host_key(key_id=...)` called with keyword-only argument
- [x] Confirmation dialog shown before delete — user cannot accidentally delete

## Self-Check: PASSED

- [x] `device_manager.py` modified — `_load_ssh_keys`, `_delete_host_key`, `_refresh_list` present
- [x] `tests/test_ssh_keys_tab.py` created — 6 tests all pass (`python -m pytest tests/test_ssh_keys_tab.py -v`)
- [x] Commits `3eacbf3`, `58470aa`, `fb9a4ad` exist in `git log --oneline`
