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
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
 