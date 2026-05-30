---
quick_id: QT-02
slug: update-host-key-silent-failure
date: 2026-05-30
status: in_progress
files_modified:
  - host_key_dialog.py
---

# Quick Task: Fix update_host_key silent failure on IntegrityError

## Problem

In `host_key_dialog.py` `verify_host_key`, the `"update_key"` branch (lines 199-213) has a logic error:

```python
elif result == "update_key":
    try:
        db.update_host_key(...)
    except sqlite3.IntegrityError as exc:
        print(f"[HostKeyVerifier] update_host_key failed: {exc}")
    result = "always_trust"   # BUG: outside try — executes even on failure
```

When `db.update_host_key` raises `sqlite3.IntegrityError`, the exception is caught and printed, but `result = "always_trust"` still executes unconditionally. The connection proceeds as trusted even though the new key was never saved. The user sees no error and will be shown the changed-key dialog again on the next connect with no explanation.

## Fix

Move `result = "always_trust"` inside the try block (success path). On exception, remap to `"accept_once"` (connect this time, but don't persist — user sees dialog again next connect) and emit `connection_status_note` to surface the failure in the status bar.

## must_haves

- `result = "always_trust"` only executes when `db.update_host_key` succeeds
- On `IntegrityError`, result becomes `"accept_once"` (not `"always_trust"`)
- `connection_status_note` is emitted on failure so the user sees a status bar message
- `result = "always_trust"` is NOT on an unindented line after the except block
