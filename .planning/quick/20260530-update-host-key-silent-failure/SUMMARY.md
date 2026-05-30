---
quick_id: QT-02
slug: update-host-key-silent-failure
date: 2026-05-30
status: complete
commit: 753fcef
files_modified:
  - host_key_dialog.py
---

# QT-02: Fix update_host_key silent failure on IntegrityError

## What changed

`host_key_dialog.py` lines 199-219 — `verify_host_key` update_key branch.

**Before:** `result = "always_trust"` was outside (after) the `try/except`, so it executed unconditionally even when `db.update_host_key` raised `IntegrityError`. The connection proceeded as trusted even though the new key was never saved.

**After:** `result = "always_trust"` moved inside the `try` block — only executes when the DB write succeeds. On `IntegrityError`, result becomes `"accept_once"` (connects once, not persisted) and `connection_status_note` is emitted so the user sees "Warning: host key could not be saved — mismatch will reappear next connect" in the status bar.

## Verification

- `python -c "import host_key_dialog, connector, db, main; print('imports OK')"` → OK
- `result = "always_trust"` confirmed at indent 16 (inside try block at indent 12)
- Except path confirmed: `result = "accept_once"` + `connection_status_note.emit`
