# ROADMAP.md — RemoteIn Security (v1.1)

## Phases

| # | Name | Status | Requirements | Completed |
|---|------|--------|--------------|-----------|
| 1 | connector.py Cleanup | Complete | MAINT-01, BUG-02, DEAD-01 | 2026-05-27 |
| 2 | Panels Cleanup | Complete | MAINT-02, MAINT-03, BUG-01, DEAD-02 | 2026-05-27 |
| 3 | Credential Encryption | Complete | CRED-01, CRED-02, CRED-03, CRED-04 | 2026-05-29 |
| 4 | SSH Host Key Verification | 4/6 | In Progress|  |

---

## Phase 3: Credential Encryption

**Goal:** Device passwords are encrypted at rest. The encryption key derives
from the user's login password and is never persisted. Existing plaintext
passwords are migrated automatically on first login.

**Files in scope:** `db.py`, `connector.py`, `device_manager.py`, `main.py`, `requirements.txt`

**Plans:** 6 plans across 4 waves
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Crypto helpers + schema migration + encrypt on save (db.py, requirements.txt)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-02-PLAN.md — Unit test scaffold: 7 tests covering CRED-01 through CRED-04
- [x] 03-03-PLAN.md — connector.py + panels/base.py: decrypt at connection time, session_key threading
- [x] 03-04-PLAN.md — device_manager.py: decrypt on form load, encrypt on save (anti double-encrypt)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-05-PLAN.md — main.py: login-time key derivation, migration trigger, full wiring

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03-06-PLAN.md — Functional verification checkpoint

**Success Criteria:**

1. SQLite `devices` table stores ciphertext for `password` and `enable_pass`, not plaintext
2. Saving a device encrypts both password fields; loading decrypts on-demand for connection only
3. First login after upgrade detects plaintext passwords and re-encrypts them transparently
4. Decrypted value is never written back to disk; memory reference is short-lived
5. Key derivation uses PBKDF2-HMAC-SHA256 with a stored salt; key is derived fresh each login session

---

## Phase 4: SSH Host Key Verification

**Goal:** Every SSH connection verifies the server's host key. First connect
shows a fingerprint dialog. Changed keys block the connection with a warning.
Accepted keys are stored in SQLite and manageable from device settings.

**Files in scope:** `db.py`, `connector.py`, `device_manager.py` (or new `host_key_dialog.py`)

**Success Criteria:**

1. Connecting to an unknown host raises a dialog showing the key fingerprint (SHA256)
2. Selecting "Accept" or "Always Trust" stores the key in the `host_keys` table
3. Selecting "Reject" aborts the connection without storing anything
4. Reconnecting to a known host with a matching key connects silently
5. Reconnecting with a changed key shows a warning dialog — user must explicitly accept to proceed
6. Device settings dialog includes a tab or section to view and delete stored host keys
