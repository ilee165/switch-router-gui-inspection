---
phase: 03-credential-encryption
fixed_at: 2026-05-29T01:30:00Z
review_path: .planning/phases/03-credential-encryption/03-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-05-29T01:30:00Z
**Source review:** .planning/phases/03-credential-encryption/03-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (3 Critical + 4 Warning)
- Fixed: 6 (CR-01 also resolved WR-02 in the same edit)
- Skipped: 0

All 7/7 tests passed after fixes. All import checks clean.

---

## Fixed Issues

### CR-01: SSH host-key verification is permanently disabled

**Files modified:** `connector.py`
**Commit:** `1e25997`
**Applied fix:** Removed `ssh_strict: False` and `system_host_keys: False` (which auto-accepted every host key). Changed to `system_host_keys: True` so only already-trusted hosts in the system known_hosts file can connect. Added comment directing future developer to SSH-01 implementation. WR-02 (`disabled_algorithms` SHA-1 downgrade) was also removed in this same edit since both were adjacent in `_netmiko_device()`.

---

### CR-02: Silent exception swallow in migration leaves devices silently unreachable

**Files modified:** `main.py`
**Commit:** `d556f39`
**Applied fix:** Replaced `except Exception: pass` with `except Exception as exc:` that shows a `QMessageBox.warning` dialog explaining which devices may fail to connect and surfacing the exception detail. Used `locals().get("count", "some")` to safely handle the case where the exception fires before the `count` assignment.

---

### CR-03: `session_key=None` default creates live double-encryption path

**Files modified:** `device_manager.py`
**Commit:** `0967636`
**Applied fix:** Changed `load_device(self, device: dict, session_key: bytes = None)` to `load_device(self, device: dict, *, session_key: bytes)` — removing the `None` default and making `session_key` a required keyword-only argument. Removed the `if session_key else device["password"]` conditional branches so `decrypt_field` is always called. The call site in `_on_item_clicked` (line 181) already passes `session_key=self._session_key` and continues to work unchanged.

---

### WR-01: Salt returned before DB commit — crash window leaves key unreproducible

**Files modified:** `db.py`
**Commit:** `72b250f`
**Applied fix:** Restructured `get_or_create_salt()` to perform the `UPDATE` inside the first `with` block (which commits on `__exit__`), then opens a second connection to re-read the saved value before returning it. If the read-back finds an empty value (commit failed), raises `RuntimeError` rather than returning salt bytes that cannot be reproduced on next login.

---

### WR-02: `disabled_algorithms` downgrades SSH to legacy RSA (SHA-1)

**Files modified:** `connector.py`
**Commit:** `1e25997` (same commit as CR-01)
**Applied fix:** The entire `disabled_algorithms` block was removed as part of the CR-01 fix to `_netmiko_device()`. Paramiko now negotiates `rsa-sha2-256`/`rsa-sha2-512` first and falls back as needed by the remote device.

---

### WR-03: Timing oracle on username enumeration in `verify_user`

**Files modified:** `db.py`
**Commit:** `72b250f`
**Applied fix:** Added module-level `_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()` computed at import time. Restructured `verify_user` to call `bcrypt.checkpw(password.encode(), _DUMMY_HASH.encode())` in the `else` branch when the username does not exist, ensuring constant response time regardless of whether the username is valid.

---

### WR-04: `_is_fernet_token` padding correction is incorrect

**Files modified:** `db.py`
**Commit:** `72b250f`
**Applied fix:** Added `raw[0] == 0x80` check after the base64 decode in `_is_fernet_token`. The Fernet version byte (0x80) is the definitive discriminator — any string starting with `gAAAA` that does not decode to a first byte of `0x80` is not a Fernet token. This eliminates false positives from plaintext device passwords that happen to start with `gAAAA`, which would previously have been silently skipped by the migration.

---

## Skipped Issues

None — all in-scope findings were fixed.

---

## Verification Results

```
tests/test_encryption.py::test_save_device_stores_ciphertext   PASSED
tests/test_encryption.py::test_key_derivation_deterministic    PASSED
tests/test_encryption.py::test_key_never_written_to_disk       PASSED
tests/test_encryption.py::test_migrate_plaintext_passwords     PASSED
tests/test_encryption.py::test_no_double_encryption            PASSED
tests/test_encryption.py::test_get_device_returns_ciphertext   PASSED
tests/test_encryption.py::test_empty_enable_pass_safe          PASSED

7 passed in 4.28s

import connector  -- OK
import db         -- OK
import device_manager -- OK
import main       -- OK
```

---

_Fixed: 2026-05-29T01:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
