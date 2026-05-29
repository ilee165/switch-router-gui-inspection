---
phase: 03-credential-encryption
reviewed: 2026-05-29T01:10:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - CLAUDE.md
  - connector.py
  - db.py
  - device_manager.py
  - main.py
  - panels/arp_mac.py
  - panels/base.py
  - panels/bgp_ospf.py
  - panels/cli.py
  - panels/interfaces.py
  - panels/routing.py
  - requirements.txt
  - tests/conftest.py
  - tests/test_encryption.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-29T01:10:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

This phase added Fernet/PBKDF2 credential encryption to device passwords stored
in SQLite, threaded a `session_key: bytes` parameter through the full call chain
(LoginDialog → MainWindow → panels → connector → db), and wrote a seven-test
suite covering CRED-01 through CRED-04.

The cryptographic primitives are correctly chosen and implemented: PBKDF2-HMAC-
SHA256 at 600,000 iterations, `os.urandom(16)` salt, Fernet for authenticated
encryption, and `_is_fernet_token()` for idempotent migration. The session key
is never stored on disk and the test suite confirms this.

Three blockers were found. The most serious is pre-existing but directly relevant
to this milestone: `connector.py` unconditionally sets `ssh_strict: False`,
silently accepting every host key and making every connection vulnerable to MITM.
The second blocker is a silent exception swallow in the migration path that can
leave some devices unreachable with no user-visible error. The third is a
`session_key=None` default in `DeviceFormWidget.load_device()` that creates a
live double-encryption path.

---

## Critical Issues

### CR-01: SSH host-key verification is permanently disabled

**File:** `connector.py:41-42`
**Issue:** `_netmiko_device()` hard-codes `ssh_strict: False` and
`system_host_keys: False`. `ssh_strict: False` instructs Paramiko to auto-accept
any host key presented during the handshake — including one substituted by an
attacker on the same network segment. The milestone explicitly schedules SSH-01
through SSH-04 (host-key fingerprint dialogs, stored known-hosts), but those
features cannot retrofit trust once plaintext auto-acceptance is the default.
The current code actively undermines the encryption work in this phase: the
session key protects passwords at rest, but an MITM attacker receives the
decrypted password in the SSH handshake before any command is sent.

**Fix:** Remove the auto-accept flags and raise an explicit error directing the
caller to implement the SSH-01 verification dialog before enabling connections.
As an interim safe default while SSH-01 is pending:

```python
# connector.py — _netmiko_device()
return {
    "device_type":      PLATFORM_MAP.get(device["platform"], "cisco_ios"),
    "host":             device["hostname"],
    "port":             device.get("port", 22),
    "username":         device["username"],
    "password":         _pw,
    "secret":           _ep or "",
    "timeout":          15,
    # SSH-01 is not yet implemented — connections are blocked until
    # host-key verification is added (see roadmap SSH-01 through SSH-04).
    # Do NOT set ssh_strict=False here; that disables MITM protection.
}
```

If the milestone schedule requires connections to work before SSH-01 ships,
the safe interim is to load the system known_hosts file (`system_host_keys: True`)
so only already-trusted hosts connect, rather than trusting everything.

---

### CR-02: Silent exception swallow in migration leaves devices silently unreachable

**File:** `main.py:78-80`
**Issue:** The migration call is wrapped in a bare `except Exception: pass`:

```python
try:
    db.migrate_plaintext_passwords(session_key)
except Exception:
    pass  # Non-fatal: unencrypted rows remain readable; login proceeds
```

The comment's reasoning is incorrect. If `migrate_plaintext_passwords` raises
partway through (DB write error, disk full, corrupt row), some device rows will
have been encrypted and some will still hold plaintext. When `connector.py` later
calls `decrypt_field(session_key, plaintext_value)`, Fernet raises `InvalidToken`
on a non-token input, `decrypt_field` catches it and returns `None`, and
`_netmiko_device` raises `ValueError("Credential decryption failed")`. The user
sees a connection error with no explanation of why some devices work and others
do not. The unencrypted rows are NOT silently readable as the comment claims —
they fail at connection time.

Additionally, swallowing the exception hides any real DB errors (permissions,
corruption) that the user should be told about.

**Fix:** Show a non-blocking warning dialog on failure instead of silently
continuing. Log at minimum so the error is diagnosable:

```python
try:
    count = db.migrate_plaintext_passwords(session_key)
    if count:
        # Optional: status bar message "Migrated N device passwords"
        pass
except Exception as exc:
    QMessageBox.warning(
        self,
        "Migration Warning",
        f"Could not encrypt {count if 'count' in dir() else 'some'} device "
        f"password(s). Affected devices may fail to connect.\n\nDetail: {exc}"
    )
```

---

### CR-03: `session_key=None` default creates live double-encryption path

**File:** `device_manager.py:67`
**Issue:** `DeviceFormWidget.load_device()` accepts `session_key: bytes = None`
as a keyword argument with a `None` default. When `session_key` is `None`, the
fallback at line 77 populates the password field with the raw ciphertext from
the DB:

```python
_pw = decrypt_field(session_key, device["password"]) if session_key else device["password"]
```

If any caller invokes `load_device(device)` without a key — or if the key is
accidentally passed as `None` — the form holds ciphertext. When the user clicks
Save, `_on_save()` emits that ciphertext as `payload["password"]`, and
`_save_device()` calls `db.update_device(..., session_key=self._session_key)`,
which calls `encrypt_field(session_key, ciphertext_value)` — Fernet-encrypting
an already-encrypted value. The resulting double-encrypted value is stored back
to the DB silently. On the next connection attempt, `decrypt_field` produces the
inner ciphertext token (not the original password), and the SSH login fails.

The docstring on `update_device` claims "always receives plaintext and always
encrypts — no double-encryption risk", but that guarantee is broken by this
default.

**Fix:** Remove the `None` default. Make `session_key` a required keyword-only
argument so callers cannot accidentally omit it:

```python
def load_device(self, device: dict, *, session_key: bytes):
    self._device_id = device["id"]
    # ... (remove the 'if session_key else' branches — key is always present)
    _pw = decrypt_field(session_key, device["password"])
    self.pass_edit.setText(_pw if _pw is not None else "")
    _ep = decrypt_field(session_key, device.get("enable_pass", ""))
    self.enable_edit.setText(_ep if _ep is not None else "")
```

Also update the call site in `_on_item_clicked` (line 181), which already passes
`session_key=self._session_key` correctly and will continue to work unchanged.

---

## Warnings

### WR-01: Salt returned before DB commit — crash window leaves key unreproducible

**File:** `db.py:163-174`
**Issue:** `get_or_create_salt()` generates a new salt with `os.urandom(16)`,
writes it via `conn.execute(UPDATE ...)`, and then returns the salt bytes at
line 174 — all inside the `with get_conn() as conn` block. The `with` block
commits on `__exit__`. If the commit fails (disk full, permission error, locked
DB), the salt bytes are already in memory and returned to the caller. The
session key is then derived from this salt and used to encrypt device passwords.
On next login, `get_or_create_salt()` finds `encryption_salt = ''` in the DB
(the write failed), generates a different random salt, derives a different key,
and all previously encrypted passwords become permanently undecryptable.

**Fix:** Check that the salt actually persisted after the `with` block exits, or
structure it to re-read the saved value:

```python
def get_or_create_salt(user_id: int) -> bytes:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT encryption_salt FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row and row["encryption_salt"]:
            return bytes.fromhex(row["encryption_salt"])
        salt = os.urandom(16)
        conn.execute(
            "UPDATE users SET encryption_salt = ? WHERE id = ?",
            (salt.hex(), user_id),
        )
    # Re-read to confirm the write succeeded before returning
    with get_conn() as conn:
        row = conn.execute(
            "SELECT encryption_salt FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not (row and row["encryption_salt"]):
            raise RuntimeError("Failed to persist encryption salt — cannot derive session key")
        return bytes.fromhex(row["encryption_salt"])
```

---

### WR-02: `disabled_algorithms` downgrades SSH to legacy RSA (SHA-1)

**File:** `connector.py:45-47`
**Issue:** The `disabled_algorithms` block explicitly removes `rsa-sha2-256` and
`rsa-sha2-512` from Paramiko's public-key algorithm list:

```python
"disabled_algorithms": {
    "pubkeys": ["rsa-sha2-256", "rsa-sha2-512"],  # fall back to legacy RSA
},
```

This forces the SSH negotiation to use `ssh-rsa` (SHA-1-based RSA), which has
been deprecated since OpenSSH 8.8 (released September 2021) due to SHA-1
collision vulnerabilities. Many modern network devices and jump hosts already
refuse `ssh-rsa` by default. The comment acknowledges the downgrade ("fall back
to legacy") but does not justify why SHA-2 variants are being rejected. If the
intent was to fix connection issues with older Cisco IOS devices that don't
advertise SHA-2 RSA, the correct approach is to let Paramiko negotiate SHA-2
first and only fall back gracefully — not to pre-emptively disable SHA-2.

**Fix:** Remove the `disabled_algorithms` block entirely and let Paramiko
negotiate the strongest mutually supported algorithm. If a specific device
genuinely requires legacy RSA, expose it as a per-device option rather than a
global downgrade:

```python
# Remove the disabled_algorithms key entirely from the return dict.
# Paramiko will negotiate rsa-sha2-256/512 first and fall back as needed.
```

---

### WR-03: Timing oracle on username enumeration in `verify_user`

**File:** `db.py:216-224`
**Issue:** When the username does not exist in the DB, `verify_user` returns
`None` immediately — without calling `bcrypt.checkpw`. When the username exists
but the password is wrong, `bcrypt.checkpw` runs its full work factor (bcrypt
rounds), taking ~100–300ms. This creates a measurable timing difference: an
attacker can enumerate valid usernames by observing response latency. For a
local desktop app this is low-severity, but since the login dialog is the sole
gate to all stored device credentials, it is worth closing.

**Fix:** Always run `bcrypt.checkpw` against a dummy hash when the user is not
found, ensuring constant time regardless of whether the username exists:

```python
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()

def verify_user(username: str, password: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row:
        if bcrypt.checkpw(password.encode(), row["password"].encode()):
            return dict(row)
    else:
        # Run bcrypt anyway to prevent username enumeration via timing
        bcrypt.checkpw(password.encode(), _DUMMY_HASH.encode())
    return None
```

---

### WR-04: `_is_fernet_token` padding correction is incorrect

**File:** `db.py:80`
**Issue:** The function appends `'=='` unconditionally before decoding:

```python
return len(base64.urlsafe_b64decode(value + '==')) >= 57
```

A valid Fernet token is already correctly padded base64url (its length is always
a multiple of 4). Appending `==` to a correctly-padded string produces a string
whose length mod 4 is 2, which is malformed base64. Python's `urlsafe_b64decode`
silently accepts over-padded input in most cases, but this is relying on
undocumented lenient behavior. The correct approach is to use `validate=False`
and strip before re-padding, or simply rely on the `startswith('gAAAA')` check
(which is already a very strong discriminator) without the length cross-check,
since any string starting with `gAAAA` that successfully base64-decodes to 57+
bytes is almost certainly a Fernet token.

A more critical edge case: a genuine plaintext device password that starts with
`gAAAA` (unlikely but possible) and is long enough to pass the length check
would be silently skipped by `migrate_plaintext_passwords`, leaving it
unencrypted in the DB forever.

**Fix:** Use stricter padding handling and add an explicit Fernet decode attempt
as the definitive test:

```python
def _is_fernet_token(value: str) -> bool:
    if not value or not value.startswith('gAAAA'):
        return False
    # Use Fernet's own validation rather than manual base64 decode
    try:
        # extract_timestamp raises ValueError on malformed tokens
        from cryptography.fernet import Fernet as _F
        # We can't call decrypt without a key, but we can check the structure:
        raw = base64.urlsafe_b64decode(value + '==')
        return len(raw) >= 57 and raw[0] == 0x80
    except Exception:
        return False
```

The key addition is checking `raw[0] == 0x80` — the Fernet version byte —
which eliminates false positives from non-token strings that happen to
start with `gAAAA`.

---

## Info

### IN-01: `encrypt_field` docstring incorrectly describes AES key size

**File:** `db.py:86`
**Issue:** The docstring says "AES-128-CBC + HMAC-SHA256". Fernet internally
splits its 32-byte input key into two 16-byte halves: one for AES-128-CBC
encryption and one as the HMAC-SHA256 signing key. The PBKDF2 output is 32 bytes
of high-entropy key material, but AES encryption is only 128-bit, not 256-bit.
This is correct Fernet behavior, but the comment could mislead a future reader
into believing the encryption strength is AES-256. This is a documentation
accuracy issue, not a code bug.

**Fix:** Update the docstring to be precise:

```python
"""Encrypt a credential string using Fernet (AES-128-CBC + HMAC-SHA256).

Note: Fernet uses a 32-byte key split into two 16-byte halves — one for
AES-128-CBC and one for HMAC-SHA256 signing. The PBKDF2 output is 256-bit
key material, but the effective encryption cipher is AES-128, not AES-256.
This is the standard Fernet construction.
"""
```

---

### IN-02: Test 6 assumes device `id=1` — fragile if schema changes

**File:** `tests/test_encryption.py:206`
**Issue:** `db.get_device(1)` hard-codes the expected primary key of the first
inserted device. This works in the current isolated DB (fresh schema, no seeded
devices), but will silently return `None` and produce a confusing assertion
failure if `init_db()` ever seeds a device row or if the AUTOINCREMENT sequence
starts at a different value.

**Fix:** Query by name instead of by hardcoded ID:

```python
# Instead of db.get_device(1), retrieve by name:
import sqlite3
conn = sqlite3.connect(isolated_db)
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT id FROM devices WHERE name = ?", ("switch-ciphertext-check",)
).fetchone()
conn.close()
device_id = row["id"]
result = db.get_device(device_id)
```

---

_Reviewed: 2026-05-29T01:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
