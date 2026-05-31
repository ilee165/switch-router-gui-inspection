import sqlite3
import bcrypt
import os
import hashlib
import base64
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

DB_PATH = Path.home() / ".switch_router_gui" / "data.db"

def get_conn ():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite disables FK enforcement by default and resets it per-connection.
    # This PRAGMA must be set here — on every new connection — to enforce the
    # REFERENCES devices(id) declaration on host_keys and make the IntegrityError
    # contract in store_host_key accurate.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db ():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role     TEXT DEFAULT 'admin'
            );
                           
            CREATE TABLE IF NOT EXISTS devices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                hostname    TEXT NOT NULL,
                ip_address  TEXT DEFAULT '',
                platform    TEXT DEFAULT 'ios',
                port        INTEGER DEFAULT 22,
                username    TEXT NOT NULL,
                password    TEXT NOT NULL,
                enable_pass TEXT DEFAULT '',
                notes       TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS host_keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   INTEGER NOT NULL REFERENCES devices(id),
                hostname    TEXT    NOT NULL,
                port        INTEGER NOT NULL,
                key_type    TEXT    NOT NULL,
                fingerprint TEXT    NOT NULL,
                key_blob    TEXT    NOT NULL,
                added_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_id, hostname, port, key_type)
            );
        """)

        # Add encryption_salt column if this is an upgrade from a pre-encryption install.
        # sqlite3.OperationalError means the column already exists — that is normal
        # after the first run and is silently ignored.
        try:
            conn.execute("ALTER TABLE users ADD COLUMN encryption_salt TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists on upgraded installs

        cur = conn.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            hashed = bcrypt.hashpw("admin".encode(), bcrypt.gensalt()).decode()
            conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("admin", hashed, "admin"),
            )
        else:
            # Repair passwords stored as BLOB (bytes) by the old seed — decode to str
            for row in conn.execute("SELECT id, password FROM users").fetchall():
                if isinstance(row["password"], bytes):
                    conn.execute(
                        "UPDATE users SET password = ? WHERE id = ?",
                        (row["password"].decode(), row["id"]),
                    )

# ── Crypto helpers ─────────────────────────────────────────────────────────────

def _is_fernet_token(value: str) -> bool:
    """Return True if value looks like a Fernet ciphertext token (not plaintext).

    Fernet tokens always start with 'gAAAA' because the version byte (0x80)
    base64url-encodes to that prefix. We also check the decoded length is at
    least 57 bytes (1 version + 8 timestamp + 16 IV + >=16 ciphertext + 32 HMAC)
    to avoid false positives from short strings that happen to start with gAAAA.
    """
    if not value:
        return False
    if not value.startswith('gAAAA'):
        return False
    try:
        raw = base64.urlsafe_b64decode(value + '==')
        # Check both minimum length and the Fernet version byte (0x80).
        # This eliminates false positives from non-token strings that happen
        # to start with 'gAAAA' — a genuine plaintext password starting with
        # 'gAAAA' would not have 0x80 as its first decoded byte.
        return len(raw) >= 57 and raw[0] == 0x80
    except Exception:
        return False


def encrypt_field(session_key: bytes, value: str) -> str:
    """Encrypt a credential string using Fernet (AES-128-CBC + HMAC-SHA256).

    Returns an empty string for empty or None values without calling Fernet.
    This guard is critical: empty enable_pass is stored as '' in the DB and
    Fernet.encrypt(b'') would raise InvalidToken on the decrypt side.

    Args:
        session_key: A Fernet-format key (44-byte base64url bytes) derived
                     at login via derive_session_key().
        value:       The plaintext credential to encrypt.

    Returns:
        Fernet ciphertext as a str, or '' if value is empty/None.
    """
    if not value:
        return ''
    return Fernet(session_key).encrypt(value.encode('utf-8')).decode()


def decrypt_field(session_key: bytes, value: str) -> str | None:
    """Decrypt a Fernet-encrypted credential string.

    Returns '' for empty or None stored values (devices with no enable_pass).
    Returns None if decryption fails — this signals a corrupt DB value or a
    wrong session key. Callers must handle None (e.g. connector.py falls back
    gracefully; device_manager.py shows an empty field rather than crashing).

    Args:
        session_key: The same Fernet key that was used during encrypt_field().
        value:       The ciphertext string from the DB (or '' / None).

    Returns:
        Decrypted plaintext str, '' for empty input, or None on failure.
    """
    if not value:
        return ''
    try:
        return Fernet(session_key).decrypt(value.encode()).decode('utf-8')
    except Exception:
        return None


def derive_session_key(login_password: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from the user's login password and salt.

    Uses PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP 2025 recommendation).
    The same password + salt always produces the same key — this is intentional
    so the user's login recreates the key on every session without storing it.

    Note: We use hashlib.pbkdf2_hmac (stdlib) NOT cryptography.hazmat.PBKDF2HMAC.
    The hazmat class is single-use per instance and raises AlreadyFinalized if
    .derive() is called twice — which would break the migration loop.

    Args:
        login_password: The user's plaintext login password (UTF-8 string).
        salt:           16 random bytes stored as users.encryption_salt (hex).

    Returns:
        A 44-byte Fernet key (base64url-encoded 32-byte PBKDF2 output).
    """
    raw = hashlib.pbkdf2_hmac('sha256', login_password.encode('utf-8'), salt, 600_000)
    return base64.urlsafe_b64encode(raw)


def get_or_create_salt(user_id: int) -> bytes:
    """Load the per-user salt from the DB, or generate and store a new one.

    The salt is stored as a hex string in users.encryption_salt. On first login
    (or fresh install), the column will be '' and a new 16-byte random salt is
    generated via os.urandom (the OS CSPRNG — not random.random()).

    Args:
        user_id: The integer primary key of the logged-in user row.

    Returns:
        16 raw bytes to be passed to derive_session_key().
    """
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
    # Re-read to confirm the write committed before returning.
    # If the commit failed (disk full, locked DB), the salt bytes were never
    # persisted — returning them would derive a key that can never be
    # reproduced on next login, making all encrypted passwords undecryptable.
    with get_conn() as conn:
        row = conn.execute(
            "SELECT encryption_salt FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not (row and row["encryption_salt"]):
            raise RuntimeError(
                "Failed to persist encryption salt — cannot derive session key"
            )
        return bytes.fromhex(row["encryption_salt"])


def migrate_plaintext_passwords(session_key: bytes) -> int:
    """Re-encrypt any device passwords still stored as plaintext.

    Called once from the login flow after key derivation. On a fresh install
    there are no devices to migrate and this is a no-op. On an upgraded install
    that previously had plaintext passwords, each password is encrypted in place.

    Uses _is_fernet_token() to detect whether a value is already encrypted —
    any value starting with 'gAAAA' with sufficient decoded length is assumed
    to be a Fernet token and is left untouched. Plaintext values are encrypted
    and written back with ? placeholders (never f-strings).

    Args:
        session_key: The Fernet key derived from the user's login password.

    Returns:
        Count of device rows that were migrated (0 if nothing to do).
    """
    migrated = 0
    with get_conn() as conn:
        rows = conn.execute("SELECT id, password, enable_pass FROM devices").fetchall()
        for row in rows:
            pw = row["password"]
            ep = row["enable_pass"]
            needs_pw = pw and not _is_fernet_token(pw)
            needs_ep = ep and not _is_fernet_token(ep)
            if needs_pw or needs_ep:
                new_pw = encrypt_field(session_key, pw) if needs_pw else pw
                new_ep = encrypt_field(session_key, ep) if needs_ep else ep
                conn.execute(
                    "UPDATE devices SET password = ?, enable_pass = ? WHERE id = ?",
                    (new_pw, new_ep, row["id"]),
                )
                migrated += 1
    return migrated


# ── User functions ─────────────────────────────────────────────────────────────

# Pre-computed dummy hash for timing-safe username enumeration defense.
# When the username does not exist, bcrypt.checkpw runs against this hash
# so the response time is indistinguishable from a wrong-password attempt.
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()


def verify_user(username: str, password: str):
    """Return user row if credentials valid, else None.

    Always runs bcrypt.checkpw — even for unknown usernames — to prevent
    timing-based username enumeration attacks.
    """
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

def create_user(username: str, password: str, role: str = "operator"):
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed, role),
        )
 
def list_users():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT id, username, role FROM users")]

def delete_user(user_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


# ── Device functions ───────────────────────────────────────────────────────────
 
def list_devices():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM devices ORDER BY name")]
 
 
def get_device(device_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return dict(row) if row else None
 
 
def add_device(name, hostname, ip_address, platform, port, username, password,
               enable_pass="", notes="", *, session_key: bytes):
    """Insert a new device row. Passwords are Fernet-encrypted before storage.

    The *, session_key syntax makes session_key keyword-only — callers must write
    session_key=... explicitly, which makes the encryption requirement visible at
    the call site (device_manager.py, tests).
    """
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO devices (name, hostname, ip_address, platform, port, username, password, enable_pass, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, hostname, ip_address, platform, port, username,
             encrypt_field(session_key, password),
             encrypt_field(session_key, enable_pass),
             notes),
        )
 
 
def update_device(device_id, name, hostname, ip_address, platform, port, username, password,
                  enable_pass="", notes="", *, session_key: bytes):
    """Update an existing device row. Passwords are Fernet-encrypted before storage.

    The form in device_manager.py always holds plaintext during editing (because
    load_device() decrypts before populating fields). So this function always
    receives plaintext and always encrypts — no double-encryption risk.
    """
    with get_conn() as conn:
        conn.execute(
            """UPDATE devices SET name=?, hostname=?, ip_address=?, platform=?, port=?, username=?, password=?,
               enable_pass=?, notes=? WHERE id=?""",
            (name, hostname, ip_address, platform, port, username,
             encrypt_field(session_key, password),
             encrypt_field(session_key, enable_pass),
             notes, device_id),
        )
 
 
def delete_device(device_id: int):
    with get_conn() as conn:
        # Explicitly delete associated host keys before the device row.
        # PRAGMA foreign_keys = ON is now active in get_conn(), so the REFERENCES
        # declaration on host_keys would block deletion of a device that still has
        # host key rows — this explicit DELETE is belt-and-suspenders defense in
        # depth, and also clears the host_keys rows before the device row is removed.
        # Both DELETEs run inside the same connection context manager and commit
        # atomically: if either fails the whole transaction rolls back.
        conn.execute("DELETE FROM host_keys WHERE device_id = ?", (device_id,))
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))


# ── Host key functions ────────────────────────────────────────────────────────


def store_host_key(*, device_id: int, hostname: str, port: int,
                   key_type: str, fingerprint: str, key_blob: str) -> None:
    """Upsert a host key row for the given (device, host, port, key_type) tuple.

    Uses INSERT ... ON CONFLICT(device_id, hostname, port, key_type) DO UPDATE
    so that calling this function twice with the same UNIQUE tuple updates the
    existing row in place — the row's primary key and original added_at are
    preserved. The identity-preserving upsert avoids the PK churn that a
    delete-and-reinsert strategy would cause. This keeps the SSH-04 audit trail
    stable across reconnects and key updates.

    The ON CONFLICT target columns exactly match the UNIQUE(device_id, hostname,
    port, key_type) constraint in the host_keys DDL.

    All parameters are keyword-only (the * separator) so security-relevant
    identifiers can never be passed positionally and swapped silently.

    Args:
        device_id:   Foreign key into devices.id.
        hostname:    The hostname or IP address the SSH connection used.
        port:        The SSH port number (typically 22).
        key_type:    SSH key algorithm string (e.g. "ssh-ed25519", "ssh-rsa").
        fingerprint: SHA256 fingerprint string as displayed to the user.
        key_blob:    Base64-encoded server public key blob (opaque to this layer).

    Raises:
        sqlite3.IntegrityError: If device_id references a non-existent device
            (enforced by PRAGMA foreign_keys = ON in get_conn()).
            Caller (host_key_dialog.py) must catch and show QMessageBox.warning.
    """
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO host_keys
               (device_id, hostname, port, key_type, fingerprint, key_blob)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(device_id, hostname, port, key_type)
               DO UPDATE SET
                   fingerprint = excluded.fingerprint,
                   key_blob    = excluded.key_blob,
                   added_at    = CURRENT_TIMESTAMP""",
            (device_id, hostname, port, key_type, fingerprint, key_blob),
        )


def get_host_key(*, device_id: int, hostname: str, port: int,
                 key_type: str) -> dict | None:
    """Fetch a single host key row by its UNIQUE tuple.

    Returns the row as a dict, or None if no matching row exists. The None
    return is the "Reject" code path signal — no exception is raised for a
    missing row because absence is a valid and expected state (first connect).

    Args:
        device_id: Foreign key into devices.id.
        hostname:  The hostname or IP address the SSH connection used.
        port:      The SSH port number.
        key_type:  SSH key algorithm string.

    Returns:
        dict with all host_keys columns, or None if not found.
    """
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM host_keys
               WHERE device_id = ? AND hostname = ? AND port = ? AND key_type = ?""",
            (device_id, hostname, port, key_type),
        ).fetchone()
        return dict(row) if row else None


def update_host_key(*, device_id: int, hostname: str, port: int,
                    key_type: str, fingerprint: str, key_blob: str) -> int:
    """Replace fingerprint and key_blob for an existing host key row.

    This is the "Update Key" action from the changed-key warning dialog (D-05).
    The added_at column is reset to CURRENT_TIMESTAMP to record when the key
    was last verified — useful for audit and for detecting stale trust entries.

    Returns the number of rows updated (1 on success, 0 if no matching row).
    Callers must check the return value: 0 means the row was deleted between
    the dialog being shown and the user clicking "Update Key". In that case,
    use store_host_key() to insert a fresh row rather than silently trusting
    an unupdated key.

    Args:
        device_id:   Foreign key into devices.id.
        hostname:    The hostname or IP address the SSH connection used.
        port:        The SSH port number.
        key_type:    SSH key algorithm string.
        fingerprint: New SHA256 fingerprint string.
        key_blob:    New base64-encoded server public key blob.

    Returns:
        int: 1 if the row was updated, 0 if no matching row was found.
    """
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE host_keys
               SET fingerprint = ?, key_blob = ?, added_at = CURRENT_TIMESTAMP
               WHERE device_id = ? AND hostname = ? AND port = ? AND key_type = ?""",
            (fingerprint, key_blob, device_id, hostname, port, key_type),
        )
        return cur.rowcount  # 0 if no matching row; 1 if updated


def delete_host_key(*, key_id: int) -> None:
    """Remove a single host key row by its primary key.

    Used by the SSH tab Delete button (SSH-04). If the row does not exist,
    this is a no-op — no exception is raised for a missing row.

    The parameter is named key_id (not id) to avoid shadowing the Python
    built-in id() function. It is keyword-only to make call sites explicit.

    Args:
        key_id: The integer primary key of the host_keys row to delete.
    """
    with get_conn() as conn:
        conn.execute("DELETE FROM host_keys WHERE id = ?", (key_id,))


def get_device_host_keys(*, device_id: int) -> list[dict]:
    """Return all host key rows for a device, newest first.

    Used to populate the SSH tab table (SSH-04). Returns an empty list if
    no keys have been stored for this device — not an error condition.

    Args:
        device_id: Foreign key into devices.id.

    Returns:
        List of dicts (all host_keys columns), ordered by added_at DESC.
        Empty list if no rows exist.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM host_keys WHERE device_id = ? ORDER BY added_at DESC",
            (device_id,),
        ).fetchall()
        return [dict(r) for r in rows]
 