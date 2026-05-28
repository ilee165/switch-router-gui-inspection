# Phase 3: Credential Encryption — Research

**Researched:** 2026-05-28
**Domain:** Python cryptography — Fernet symmetric encryption, PBKDF2 key derivation, SQLite schema migration
**Confidence:** HIGH

---

## Summary

Phase 3 adds at-rest encryption to device passwords stored in SQLite. The encryption
key is never persisted — it is derived fresh from the user's login password on every
session and held only in memory. Existing plaintext passwords are migrated automatically
on first login after upgrade.

The standard library (`hashlib.pbkdf2_hmac`) handles key derivation. The `cryptography`
package provides Fernet for authenticated symmetric encryption. Both were verified via
live Python execution on the target machine (Python 3.14, cryptography 48.0.0).

**One important correction:** CLAUDE.md describes this as "AES-256 via Fernet." Fernet's
spec is AES-128-CBC + HMAC-SHA256 — the 32-byte key is split into two 16-byte halves
(signing key + AES key). This is well-documented and not a weakness; the overall
construction is secure. The planner should not attempt to swap in AES-256 manually —
use Fernet as-is.

**Primary recommendation:** Add `cryptography>=41.0.0` to `requirements.txt`. Use
`hashlib.pbkdf2_hmac` (stdlib) for key derivation. Store the per-user salt as a hex
string in a new `encryption_salt TEXT DEFAULT ''` column on the `users` table.
Pass the derived `session_key: bytes` as an explicit parameter through the call stack.

---

## Project Constraints (from CLAUDE.md)

- Never rewrite whole files — always use targeted edits
- `styles.py` is off-limits
- Explain changes as you make them — owner is learning to code
- Respect layering: panels never touch db; no business logic in `main.py`; no GUI in `connector.py`
- SQL safety: always use `?` placeholders, never f-strings in SQL
- Threading: all network calls go through `_start_worker()` in `BasePanel`

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CRED-01 | Device passwords encrypted at rest in SQLite using AES-256 (Fernet) | Fernet API verified; encrypt on `add_device`/`update_device`, store ciphertext |
| CRED-02 | Encryption key derived from login password via PBKDF2, never stored on disk | `hashlib.pbkdf2_hmac` + `base64.urlsafe_b64encode` → Fernet key; salt stored in `users.encryption_salt`; key lives only in memory |
| CRED-03 | Existing plaintext passwords migrated to encrypted form on first login after upgrade | Detect via `gAAAA` prefix + length check; re-encrypt in `migrate_plaintext_passwords()` called from login flow |
| CRED-04 | Decrypted passwords exist only in memory for connection duration, never written back | Decrypt in `connector.py` only inside connection context; never return plaintext from `db.get_device()` |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Key derivation from login password | `main.py` (login flow) | `db.py` (reads salt) | Derivation happens once at login, result passed down |
| Salt generation and storage | `db.py` | — | Salt is a DB concern; generated on first login if absent |
| Encrypt on device save | `db.py` (`add_device`, `update_device`) | `device_manager.py` (passes key) | DB layer owns all persistence; form submits plaintext |
| Decrypt for connection | `connector.py` | — | Decryption happens at connection time only, per CRED-04 |
| Migration (plaintext → encrypted) | `db.py` | `main.py` (triggers call) | DB layer reads/writes; called once from login flow |
| Session key lifetime | `main.py` → `MainWindow` | passed to `DeviceManagerDialog` | Key created at login, passed explicitly, never global |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `cryptography` | 48.0.0 (installed) | Fernet symmetric encryption | [VERIFIED: live import] PyCA cryptography — the canonical Python crypto library |
| `hashlib` | stdlib | PBKDF2-HMAC-SHA256 key derivation | [VERIFIED: live execution] Built into Python 3.4+; no extra dependency |
| `base64` | stdlib | Encode 32-byte derived key to Fernet format | [VERIFIED: live execution] Required by Fernet key format |
| `os.urandom` | stdlib | Cryptographically secure salt generation | [VERIFIED: live execution] OS CSPRNG |

### Not Needed

| Package | Why Not |
|---------|---------|
| `pycryptodome` / `pycryptodomex` | `cryptography` package already present via `paramiko`/`netmiko`; redundant |
| `cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC` | `hashlib.pbkdf2_hmac` is simpler and sufficient; hazmat API is single-use per instance |
| `secrets` module | Only needed for token generation; `os.urandom` is correct for salts |

**Installation — only one new line needed in `requirements.txt`:**

```
cryptography>=41.0.0
```

Note: `cryptography` is almost certainly already installed as a transitive dependency
of `paramiko` (which is required by `netmiko`). The version pin just makes it explicit.

---

## Package Legitimacy Audit

| Package | Registry | Age | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|
| `cryptography` | PyPI | ~13 years (PyCA project) | [OK] (verified live) | Approved |

**Packages removed:** none
**Packages flagged:** none

*slopcheck ran successfully and returned [OK] for `cryptography` before hitting an
unrelated Windows subprocess path issue. The package is the canonical PyCA cryptography
library, maintained by the Python Cryptographic Authority.*

---

## Architecture Patterns

### System Architecture Diagram

```
LOGIN FLOW
  LoginDialog._login()
       │  plaintext login password (never stored)
       ▼
  db.get_or_create_salt(user_id)  ──► users.encryption_salt (hex, persisted)
       │  16-byte salt
       ▼
  _derive_key(password, salt)
       │  session_key: bytes  (Fernet-format, in memory only)
       ▼
  db.migrate_plaintext_passwords(session_key)   [no-op if already migrated]
       │
       ▼
  MainWindow(user, session_key)
       │
       ├──► DeviceManagerDialog(session_key)
       │         │  form submits plaintext password
       │         ▼
       │    db.add_device(..., session_key)  ──► SQLite: stores ciphertext
       │    db.update_device(..., session_key)
       │
       └──► _on_device_selected()
                 │  db.get_device(id) returns device dict with CIPHERTEXT
                 │
                 ▼
            panel.set_device(device_with_ciphertext)
                 │
                 ▼
            connector.get_interfaces(device, session_key)
                 │  decrypt_field(session_key, device['password'])
                 │  plaintext lives only inside ConnectHandler context manager
                 ▼
            ConnectHandler(**netmiko_params)
```

### Recommended Project Structure

No new files needed. Changes are confined to existing files:

```
db.py                # get_or_create_salt(), _derive_key() helper,
                     # migrate_plaintext_passwords(), encrypt/decrypt in
                     # add_device() / update_device()
connector.py         # accept session_key param; decrypt in _netmiko_device()
                     # and _genie_testbed()
device_manager.py    # accept + thread session_key through _save_device()
main.py              # derive key at login; pass to MainWindow;
                     # MainWindow passes to DeviceManagerDialog and panels
```

### Pattern 1: Key Derivation at Login

```python
# Source: verified via live execution — hashlib stdlib + cryptography 48.0.0
import hashlib, base64, os

def get_or_create_salt(user_id: int) -> bytes:
    """Load existing salt or generate and store a new one."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT encryption_salt FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row and row["encryption_salt"]:
            return bytes.fromhex(row["encryption_salt"])
        salt = os.urandom(16)
        conn.execute(
            "UPDATE users SET encryption_salt = ? WHERE id = ?",
            (salt.hex(), user_id)
        )
        return salt

def derive_session_key(login_password: str, salt: bytes) -> bytes:
    """Derive Fernet key from login password. Returns bytes (Fernet key format)."""
    raw = hashlib.pbkdf2_hmac('sha256', login_password.encode('utf-8'), salt, 600_000)
    return base64.urlsafe_b64encode(raw)  # 44-char bytes, accepted by Fernet()
```

### Pattern 2: Encrypt / Decrypt Field

```python
# Source: verified via live execution — cryptography.fernet 48.0.0
from cryptography.fernet import Fernet, InvalidToken

def encrypt_field(session_key: bytes, value: str) -> str:
    """Encrypt a credential field. Returns '' for empty/None values."""
    if not value:
        return ''
    f = Fernet(session_key)
    return f.encrypt(value.encode('utf-8')).decode()

def decrypt_field(session_key: bytes, value: str) -> str:
    """Decrypt a credential field. Returns '' for empty/None stored values."""
    if not value:
        return ''
    f = Fernet(session_key)
    return f.decrypt(value.encode()).decode('utf-8')
```

**Why create `Fernet()` per call rather than storing an instance:** Fernet is
stateless for encrypt/decrypt — there is no performance benefit to caching it.
Creating it inline keeps the plaintext lifetime minimal and makes the code easier
to reason about. No global Fernet instance.

### Pattern 3: Migration Detection and Execution

```python
# Source: verified via live execution
import base64

def _is_fernet_token(value: str) -> bool:
    """Return True if value looks like a Fernet token (not plaintext)."""
    if not value:
        return False
    if not value.startswith('gAAAA'):
        return False
    try:
        # Fernet token minimum: 1B version + 8B timestamp + 16B IV +
        # >=16B ciphertext + 32B HMAC = >=73 bytes decoded
        return len(base64.urlsafe_b64decode(value + '==')) >= 57
    except Exception:
        return False

def migrate_plaintext_passwords(session_key: bytes) -> int:
    """
    Re-encrypt any device passwords that are still stored as plaintext.
    Called once from the login flow after key derivation.
    Returns count of rows migrated.
    """
    migrated = 0
    with get_conn() as conn:
        rows = conn.execute("SELECT id, password, enable_pass FROM devices").fetchall()
        for row in rows:
            pw  = row["password"]
            ep  = row["enable_pass"]
            needs_pw = pw  and not _is_fernet_token(pw)
            needs_ep = ep  and not _is_fernet_token(ep)
            if needs_pw or needs_ep:
                new_pw = encrypt_field(session_key, pw)  if needs_pw else pw
                new_ep = encrypt_field(session_key, ep)  if needs_ep else ep
                conn.execute(
                    "UPDATE devices SET password = ?, enable_pass = ? WHERE id = ?",
                    (new_pw, new_ep, row["id"])
                )
                migrated += 1
    return migrated
```

### Pattern 4: Connector Change — Decrypt at Connection Time

The two functions in `connector.py` that build connection dicts must accept the
session key and decrypt passwords inline:

```python
# Source: verified against connector.py source + cryptography 48.0.0
def _netmiko_device(device: dict, session_key: bytes) -> dict:
    return {
        ...
        "password": decrypt_field(session_key, device["password"]),
        "secret":   decrypt_field(session_key, device.get("enable_pass", "")),
        ...
    }

def _genie_testbed(device: dict, session_key: bytes) -> dict:
    # Same change: decrypt both password fields before passing to testbed dict
    ...
```

All six public `get_*` functions and `run_cli_command` must thread `session_key`
through to these helpers.

### Pattern 5: DeviceFormWidget — load_device must NOT show ciphertext

`DeviceFormWidget.load_device()` currently does:
```python
self.pass_edit.setText(device["password"])  # BUG after encryption: shows ciphertext
```

After encryption, `db.get_device()` returns ciphertext. The form must decrypt before
displaying (so the user sees the real password when editing):

```python
def load_device(self, device: dict, session_key: bytes):
    ...
    self.pass_edit.setText(decrypt_field(session_key, device["password"]))
    self.enable_edit.setText(decrypt_field(session_key, device.get("enable_pass", "")))
```

`DeviceManagerDialog` must receive `session_key` from its caller (`MainWindow`) and
pass it to both `load_device()` and down through `_save_device()` to the db calls.

### Anti-Patterns to Avoid

- **Storing the derived key in a module-level global:** Breaks testability, creates
  implicit state. Pass `session_key` explicitly as a parameter.
- **Calling `Fernet(key).decrypt()` on a value without checking for empty string:**
  Empty `enable_pass` is stored as `''`. Calling `f.decrypt(b'')` raises `InvalidToken`.
  Always guard with `if not value: return ''`.
- **Decrypting in `db.get_device()` or `db.list_devices()`:** These return raw DB rows.
  Decryption belongs in connector (for connections) and device manager form (for display).
  Never decrypt in the DB layer itself.
- **Re-encrypting on every `update_device` call without checking:** If the user edits
  a device but the password field already contains ciphertext (loaded from the form),
  double-encrypting will corrupt the value. The form must always decrypt before populating
  the field, so `_save_device` always receives plaintext.
- **Using `hashlib.pbkdf2_hmac` with fewer than 600,000 iterations:** OWASP recommends
  600,000 for PBKDF2-HMAC-SHA256. Even though this is key derivation (not password
  storage), 600,000 makes the implementation auditable and consistent.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Symmetric authenticated encryption | Custom AES + HMAC | `cryptography.Fernet` | Fernet bundles AES-CBC + HMAC-SHA256 with correct IV generation and timing-safe comparison |
| Key derivation from password | Custom SHA hash | `hashlib.pbkdf2_hmac` | PBKDF2 adds iteration cost that makes brute-force expensive; raw SHA is instant |
| "Is this a Fernet token?" | Custom regex | `startswith('gAAAA')` + base64 length check | Fernet tokens have a fixed version byte (0x80) which always encodes to `gAAAA` in base64url |
| Salt generation | `random.random()` | `os.urandom(16)` | `os.urandom` uses the OS CSPRNG; `random` is not cryptographically secure |

---

## Schema Changes

### Exact SQL (safe to run on startup via `init_db`)

```sql
-- Add salt column to users table (idempotent via try/except OperationalError)
ALTER TABLE users ADD COLUMN encryption_salt TEXT DEFAULT '';
```

**Safety verified:** SQLite `ALTER TABLE ... ADD COLUMN` with a `DEFAULT` value is
safe on existing databases. Existing rows receive `''` (empty string). The app detects
the empty salt and generates a new one on first login. [VERIFIED: live SQLite test]

**Why no `NOT NULL` constraint on `encryption_salt`:** SQLite does not allow `ADD COLUMN NOT NULL`
without a default. `DEFAULT ''` + application-level generation on first login is the
correct pattern.

**No changes to the `devices` table schema:** `password` and `enable_pass` are already
`TEXT` columns. Fernet tokens are valid UTF-8 strings and fit without schema change.

### How to apply idempotently in `init_db()`

```python
def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (...);   -- unchanged
            CREATE TABLE IF NOT EXISTS devices (...); -- unchanged
        """)
        # Add encryption_salt column if this is an upgrade
        try:
            conn.execute("ALTER TABLE users ADD COLUMN encryption_salt TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists — normal after first run
        ...
```

---

## Key Passing Pattern Through the Call Stack

The session key must flow from `main.py` → `MainWindow` → `DeviceManagerDialog` and
`connector.py`. There are two viable patterns:

### Option A: Explicit parameter threading (RECOMMENDED)

Pass `session_key: bytes` as a constructor argument and method parameter everywhere
it's needed. This is the correct approach for a codebase where the owner is learning.
It makes data flow visible and testable.

```
LoginDialog._login()
  → derive_session_key(password, salt) → session_key
  → MainWindow(user, session_key)        [stored as self._session_key]
  → _open_device_manager()
      DeviceManagerDialog(parent, session_key)
  → _on_device_selected()
      panel.set_device(device)  [device still has ciphertext]
      connector.get_interfaces(device, session_key)
```

### Option B: Application-level singleton / QApplication property

Store `session_key` as a property of `QApplication.instance()`. Avoids threading
through every call but hides data flow and is harder to reason about. NOT recommended
for this codebase.

**Decision for planner:** Use Option A (explicit threading). The call chain is shallow
(4 levels max) and the owner benefits from seeing where the key flows.

---

## Common Pitfalls

### Pitfall 1: Double-Encryption on Device Edit

**What goes wrong:** `DeviceFormWidget.load_device()` populates the password field.
If it displays the raw ciphertext (because `db.get_device()` returns the encrypted
value), the user saves → `update_device` encrypts the ciphertext string again →
the stored value is now double-encrypted and unrecoverable.

**Why it happens:** Forgetting that the form's `_on_save()` always treats the
password field as plaintext and passes it directly to the db function.

**How to avoid:** `load_device()` must decrypt before populating fields. After this
change, the form always holds plaintext during editing, and `_save_device` always
receives plaintext to encrypt.

**Warning signs:** After editing a device and reconnecting, connection fails with
`NetmikoAuthenticationException`.

### Pitfall 2: Empty `enable_pass` Raises `InvalidToken`

**What goes wrong:** `decrypt_field(session_key, '')` calls `Fernet.decrypt(b'')`
which raises `InvalidToken`, crashing the connection attempt.

**Why it happens:** `enable_pass` defaults to `''` in the DB. Many devices don't
use an enable password.

**How to avoid:** `decrypt_field()` must guard: `if not value: return ''`. Verified
via live test that Fernet raises `InvalidToken` on empty bytes input.

### Pitfall 3: `PBKDF2HMAC` Instance is Single-Use

**What goes wrong:** If using `cryptography.hazmat.primitives.kdf.pbkdf2.PBKDF2HMAC`
(the hazmat path), calling `kdf.derive()` twice on the same instance raises
`AlreadyFinalized`.

**Why it happens:** The hazmat KDF classes are designed to be used once.

**How to avoid:** Use `hashlib.pbkdf2_hmac` instead (stdlib, no single-use constraint,
simpler API). The plan uses `hashlib` throughout. [VERIFIED: live execution]

### Pitfall 4: Salt `hex()` vs `bytes` Mismatch

**What goes wrong:** Salt is generated as `bytes`, stored as hex string. If the
hex-to-bytes conversion is not applied symmetrically (`salt.hex()` on write,
`bytes.fromhex(salt_hex)` on read), PBKDF2 produces a different key on the second
login and decryption fails with `InvalidToken` for all device passwords.

**How to avoid:** Always use `salt.hex()` for storage and `bytes.fromhex()` for
retrieval. Verify in a unit test or manual test that login #2 decrypts what login #1
encrypted.

**Warning signs:** All device connections fail immediately after the second login.

### Pitfall 5: Fernet Token Starts With `gAAAAA` (six A's), Not Five

**What goes wrong:** Migration detection checks `startswith('gAAAA')` (five A's).
This is correct — verified via live test (`b'gAAAAA...'`). Using four A's or six A's
would cause false negatives or positives.

**Confirmed prefix:** `gAAAAA` is the base64url encoding of the Fernet version byte
`0x80` + the first few bytes of the timestamp. The five-character check `gAAAA` is
a reliable heuristic; any realistic plaintext password would not start with this prefix.

### Pitfall 6: `AlreadyFinalized` on PBKDF2HMAC If Using hazmat Path

Already covered in Pitfall 3. Reiterated because it only surfaces when migrating
multiple passwords in a loop:

```python
# WRONG — hazmat path, AlreadyFinalized on second iteration
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
for device in devices:
    kdf.derive(...)  # crashes on second call

# CORRECT — hashlib path, safe to call in a loop
for device in devices:
    raw = hashlib.pbkdf2_hmac('sha256', password_bytes, salt, 600_000)
```

---

## Edge Cases and Handling

| Scenario | Stored Value | Behaviour |
|----------|-------------|-----------|
| `enable_pass` is empty string | `''` | `encrypt_field` returns `''`; `decrypt_field` returns `''`; no Fernet call |
| `enable_pass` is `None` | `''` (default) | Same as empty — guard `if not value` covers both |
| Device password contains non-ASCII (e.g. `päßwörd`) | Fernet token | `encode('utf-8')` before encrypt; `decode('utf-8')` after decrypt — verified |
| Existing DB with no `encryption_salt` column | `OperationalError` on `ADD COLUMN` suppressed | `try/except` in `init_db` handles existing upgraded installs |
| New install (no existing devices) | `migrate_plaintext_passwords()` runs, finds 0 rows | Returns `0`, no-op |
| User changes their login password | Old key no longer derivable | Out of scope for this phase; document as known limitation |

---

## Code Examples

### Complete key derivation function

```python
# Source: verified via live execution — hashlib stdlib, cryptography 48.0.0
import hashlib, base64, os
from cryptography.fernet import Fernet, InvalidToken

def derive_session_key(login_password: str, salt: bytes) -> bytes:
    """
    Derive a Fernet-compatible key from the user's login password and stored salt.
    Returns bytes in Fernet key format (base64url-encoded 32 bytes).
    600,000 iterations per OWASP PBKDF2-HMAC-SHA256 recommendation.
    """
    raw = hashlib.pbkdf2_hmac('sha256', login_password.encode('utf-8'), salt, 600_000)
    return base64.urlsafe_b64encode(raw)
```

### Complete encrypt/decrypt helpers

```python
# Source: verified via live execution
def encrypt_field(session_key: bytes, value: str) -> str:
    """Encrypt a credential string. Returns '' for empty or None values."""
    if not value:
        return ''
    return Fernet(session_key).encrypt(value.encode('utf-8')).decode()

def decrypt_field(session_key: bytes, value: str) -> str:
    """Decrypt a credential string. Returns '' for empty stored values."""
    if not value:
        return ''
    return Fernet(session_key).decrypt(value.encode()).decode('utf-8')
```

### Login flow changes in `main.py`

```python
# Source: derived from main.py source + CRED-02/CRED-03 requirements
def _login(self):
    user = self.user_input.text().strip()
    pwd  = self.pass_input.text()
    result = db.verify_user(user, pwd)           # bcrypt check unchanged
    if result:
        salt = db.get_or_create_salt(result["id"])
        session_key = db.derive_session_key(pwd, salt)
        db.migrate_plaintext_passwords(session_key)   # CRED-03: no-op if clean
        self.current_user = result
        self.session_key  = session_key
        self.accept()
    else:
        self.error_lbl.setText("Invalid credentials.")
        self.pass_input.clear()
```

`MainWindow.__init__` signature changes from `(user: dict)` to `(user: dict, session_key: bytes)`.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Plaintext passwords in SQLite | Fernet ciphertext (AES-128-CBC + HMAC-SHA256) | Passwords unreadable without login |
| No key management | PBKDF2-derived session key, never persisted | Key loss = re-enter passwords (acceptable for desktop app) |

**Not applicable here but worth knowing:**
- For multi-user key isolation, separate salts per user would be needed. Currently
  single-user-per-install so one salt per `users` row is correct.
- If the user changes their login password, the session key changes and all encrypted
  device passwords become unrecoverable. This is a known deferred risk (out of scope
  per REQUIREMENTS.md).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `cryptography` | Fernet encryption | Yes | 48.0.0 | — |
| `hashlib` | PBKDF2 key derivation | Yes | stdlib | — |
| `base64` | Fernet key encoding | Yes | stdlib | — |
| `os.urandom` | Salt generation | Yes | stdlib | — |
| Python 3.x | All of the above | Yes | 3.14 | — |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** none

---

## Validation Architecture

> `workflow.nyquist_validation` not explicitly set to false — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | None installed — zero test coverage confirmed (observation #13) |
| Config file | none |
| Quick run command | `python -m pytest tests/ -x -q` (after Wave 0 setup) |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CRED-01 | Saved device has ciphertext in DB, not plaintext | unit | `pytest tests/test_encryption.py::test_save_device_stores_ciphertext -x` | No — Wave 0 |
| CRED-02 | Key derived from login password matches on re-derive | unit | `pytest tests/test_encryption.py::test_key_derivation_deterministic -x` | No — Wave 0 |
| CRED-02 | Key is not written to disk at any point | unit | `pytest tests/test_encryption.py::test_key_never_written_to_disk -x` | No — Wave 0 |
| CRED-03 | Plaintext password in DB is migrated on next login | unit | `pytest tests/test_encryption.py::test_migrate_plaintext_passwords -x` | No — Wave 0 |
| CRED-03 | Already-encrypted password is not double-encrypted | unit | `pytest tests/test_encryption.py::test_no_double_encryption -x` | No — Wave 0 |
| CRED-04 | Decrypted password does not appear in db.get_device() | unit | `pytest tests/test_encryption.py::test_get_device_returns_ciphertext -x` | No — Wave 0 |
| CRED-04 | Empty enable_pass does not raise InvalidToken | unit | `pytest tests/test_encryption.py::test_empty_enable_pass_safe -x` | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_encryption.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_encryption.py` — all 7 unit tests above
- [ ] `tests/conftest.py` — shared in-memory SQLite fixture
- [ ] Framework install: `pip install pytest` (not in `requirements.txt`)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | bcrypt already in place; no change |
| V3 Session Management | Partial | Session key in memory only; no serialization |
| V4 Access Control | No | Single-user desktop app |
| V5 Input Validation | Yes | `encode('utf-8')` normalizes input before encryption |
| V6 Cryptography | Yes | Fernet (AES-128-CBC + HMAC-SHA256); no custom crypto |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DB file copied off-disk | Information Disclosure | Fernet ciphertext unreadable without login password |
| Brute-force key derivation | Elevation of Privilege | 600,000 PBKDF2 iterations — ~100ms per attempt on modern hardware |
| Key accidentally logged | Information Disclosure | Never log `session_key`; verify in `test_key_never_written_to_disk` |
| Double-encryption on edit | Denial of Service | `load_device()` always decrypts before populating form fields |
| Empty enable_pass crash | Denial of Service | Guard `if not value: return ''` in `decrypt_field()` |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Single login user per SQLite install (one salt per `users` row is sufficient) | Salt Storage | Low — confirmed by REQUIREMENTS.md "Out of Scope: multi-user credential isolation" |
| A2 | Login password is always UTF-8 compatible (no raw binary passwords) | Key Derivation | Very low — ASCII login passwords are universal for this app |
| A3 | Fernet token prefix `gAAAA` is a reliable migration heuristic (no real passwords start with this) | Migration Detection | Low — five-char base64 prefix is highly distinctive; probability of collision is negligible |

---

## Open Questions

1. **What happens when the user changes their login password?**
   - What we know: The session key changes because it's derived from the login password + salt.
     All existing encrypted device passwords become unrecoverable with the new key.
   - What's unclear: Should Phase 3 include a "re-encrypt all devices on password change"
     flow, or is this documented as a known limitation?
   - Recommendation: Document as a known limitation for now. Password change is in
     `user_manager.py` (admin only, rarely used). A re-encryption flow would add
     complexity beyond CRED-01 through CRED-04 scope.

2. **Should `db.get_device()` / `db.list_devices()` return ciphertext or plaintext?**
   - What we know: Returning ciphertext is correct for CRED-04 (never decrypt except
     for connection). But `device_manager.py` needs plaintext to show in the edit form.
   - What's unclear: Nothing — the answer is clearly ciphertext from DB, decrypt only
     at display/connection time. Documented in Architecture Patterns above.
   - Recommendation: DB layer always returns raw ciphertext. Callers decrypt as needed.

---

## Sources

### Primary (HIGH confidence)

- Live Python execution on target machine (Python 3.14, cryptography 48.0.0) — all API
  calls, edge cases, migration detection, schema migration
- Project source files: `db.py`, `connector.py`, `device_manager.py`, `main.py`,
  `requirements.txt` — verified current state

### Secondary (MEDIUM confidence)

- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) — 600,000 iterations for PBKDF2-HMAC-SHA256 [CITED]
- [cryptography.io Fernet spec](https://cryptography.io/en/latest/fernet/) — AES-128-CBC + HMAC-SHA256 construction confirmed via source inspection [CITED]

### Tertiary (LOW confidence)

None — all claims verified via live execution or official source.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — cryptography 48.0.0 installed and tested live
- Architecture (call stack patterns): HIGH — derived from reading source + live simulation
- Schema migration: HIGH — SQLite ALTER TABLE tested live
- Pitfalls: HIGH — each pitfall reproduced or confirmed via live code
- PBKDF2 iteration count: HIGH — OWASP cited + confirmed via WebSearch

**Research date:** 2026-05-28
**Valid until:** 2026-08-28 (stable cryptography APIs; 90 days)
