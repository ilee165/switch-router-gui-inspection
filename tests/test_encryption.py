"""
Unit tests for the credential-encryption helpers in db.py.

Covers CRED-01 through CRED-04:

  CRED-01 — Device passwords are AES-256 (Fernet) encrypted at rest.
  CRED-02 — The encryption key is derived from the login password via PBKDF2;
             it is never stored on disk.
  CRED-03 — Existing plaintext passwords are migrated in-place on first login.
  CRED-04 — db.get_device() returns ciphertext; decryption only happens in
             memory (e.g. in connector.py) for the duration of a connection.

All tests use the `isolated_db` fixture from conftest.py, which redirects
db.DB_PATH to a pytest tmp_path so the production DB is never touched.

Constants
---------
TEST_SALT        — fixed 16-byte salt (real usage: 16 random bytes from os.urandom)
TEST_LOGIN_PASS  — fake login password used to derive a deterministic session key
TEST_DEVICE_PASS — plaintext device password used as the "before-encryption" value

These are not real credentials; they exist only to give the tests a predictable
key so assertions can be deterministic across runs.
"""

import sqlite3

import pytest

import db

# ── Test constants ─────────────────────────────────────────────────────────────

TEST_SALT = b"testsalttestsalt"          # 16 bytes — fixed for determinism
TEST_LOGIN_PASS = "test_login_pass"
TEST_DEVICE_PASS = "cisco123"


@pytest.fixture()
def session_key(isolated_db):
    """Return a deterministic Fernet key derived from TEST_LOGIN_PASS + TEST_SALT.

    Depends on `isolated_db` so the temp DB is set up before any helper runs.
    """
    return db.derive_session_key(TEST_LOGIN_PASS, TEST_SALT)


# ── Test 1: CRED-01 — passwords are stored as ciphertext ─────────────────────

def test_save_device_stores_ciphertext(isolated_db, session_key):
    """add_device() must store the password as a Fernet token, not plaintext.

    We call add_device with a known plaintext password, then open the DB with a
    raw sqlite3 connection to read the row directly — bypassing any decryption
    logic that might live in db.get_device().  The stored value must start with
    'gAAAA' and must NOT equal the original plaintext.
    """
    db.add_device(
        "router-01", "192.168.1.1", "192.168.1.1",
        "ios", 22, "admin", TEST_DEVICE_PASS,
        enable_pass="", notes="",
        session_key=session_key,
    )

    conn = sqlite3.connect(isolated_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT password FROM devices WHERE name = ?", ("router-01",)).fetchone()
    conn.close()

    stored_pw = row["password"]
    assert stored_pw.startswith("gAAAA"), (
        f"Expected ciphertext starting with 'gAAAA', got: {stored_pw!r}"
    )
    assert stored_pw != TEST_DEVICE_PASS, "Plaintext password must not be stored in DB"


# ── Test 2: CRED-02 — key derivation is deterministic ────────────────────────

def test_key_derivation_deterministic(isolated_db):
    """derive_session_key() must return identical bytes for the same inputs.

    The same login password + salt must always produce the same Fernet key so
    that a user's login re-derives the key on every session without storing it.
    """
    key_a = db.derive_session_key(TEST_LOGIN_PASS, TEST_SALT)
    key_b = db.derive_session_key(TEST_LOGIN_PASS, TEST_SALT)
    assert key_a == key_b, "derive_session_key must be deterministic for the same inputs"


# ── Test 3: CRED-02 — session_key bytes never written to the DB file ─────────

def test_key_never_written_to_disk(isolated_db, session_key):
    """The raw session_key bytes must not appear anywhere in the SQLite file.

    We add a device (which writes ciphertext to the DB), then open the DB file
    in binary mode and scan every byte.  If the key material is present, it was
    accidentally written (e.g. logged, stored as a column, or embedded in the
    Fernet token verbatim — which should never happen because Fernet uses the key
    to *produce* the token, not include it).
    """
    db.add_device(
        "router-key-check", "10.0.0.1", "10.0.0.1",
        "ios", 22, "netops", TEST_DEVICE_PASS,
        session_key=session_key,
    )

    file_bytes = isolated_db.read_bytes()
    assert session_key not in file_bytes, (
        "session_key bytes were found verbatim in the DB file — key material must never be stored"
    )


# ── Test 4: CRED-03 — migrate_plaintext_passwords encrypts existing rows ─────

def test_migrate_plaintext_passwords(isolated_db, session_key):
    """migrate_plaintext_passwords() must encrypt rows inserted as plaintext.

    We insert a device directly via raw SQL (bypassing add_device) to simulate
    the pre-upgrade state where the DB contains unencrypted passwords.  After
    calling migrate_plaintext_passwords(), the stored password must be a Fernet
    token, and decrypting it must yield the original plaintext.
    """
    plaintext = "pre_upgrade_pass"
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        """INSERT INTO devices (name, hostname, ip_address, platform, port, username, password, enable_pass, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("legacy-switch", "172.16.0.1", "172.16.0.1", "ios", 22, "admin", plaintext, "", ""),
    )
    conn.commit()
    conn.close()

    count = db.migrate_plaintext_passwords(session_key)
    assert count == 1, f"Expected 1 migrated row, got {count}"

    # Read back via raw SQL to confirm the stored value is now a Fernet token
    conn = sqlite3.connect(isolated_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT password FROM devices WHERE name = ?", ("legacy-switch",)).fetchone()
    conn.close()

    stored_pw = row["password"]
    assert stored_pw.startswith("gAAAA"), (
        f"After migration, password should be ciphertext starting with 'gAAAA', got: {stored_pw!r}"
    )
    assert db.decrypt_field(session_key, stored_pw) == plaintext, (
        "Decrypting the migrated ciphertext should return the original plaintext"
    )


# ── Test 5: CRED-03 — migrate is idempotent (no double-encryption) ────────────

def test_no_double_encryption(isolated_db, session_key):
    """Calling migrate_plaintext_passwords twice must be idempotent.

    The second call should return 0 (nothing to migrate) because _is_fernet_token()
    detects that the row is already encrypted.  Decrypting after the second call
    must still yield the original plaintext — not double-encrypted garbage.
    """
    plaintext = "idempotent_pass"
    conn = sqlite3.connect(isolated_db)
    conn.execute(
        """INSERT INTO devices (name, hostname, ip_address, platform, port, username, password, enable_pass, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("idempotent-device", "10.1.1.1", "10.1.1.1", "ios", 22, "ops", plaintext, "", ""),
    )
    conn.commit()
    conn.close()

    first_count = db.migrate_plaintext_passwords(session_key)
    assert first_count == 1, f"First migration should encrypt 1 row, got {first_count}"

    second_count = db.migrate_plaintext_passwords(session_key)
    assert second_count == 0, (
        f"Second migration should return 0 (already encrypted), got {second_count}"
    )

    # Verify the value is still correctly decryptable (no double-encryption)
    conn = sqlite3.connect(isolated_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT password FROM devices WHERE name = ?", ("idempotent-device",)).fetchone()
    conn.close()

    assert db.decrypt_field(session_key, row["password"]) == plaintext, (
        "After two migrate calls, decryption must still return original plaintext"
    )


# ── Test 6: CRED-04 — get_device() returns ciphertext, not plaintext ─────────

def test_get_device_returns_ciphertext(isolated_db, session_key):
    """db.get_device() must return the stored ciphertext, never the plaintext.

    CRED-04 states that decryption happens in memory only for the duration of a
    connection (in connector.py).  db.get_device() is the raw persistence layer
    and must not decrypt on the way out.  Any decryption in the persistence layer
    would leave plaintext exposed in memory longer than necessary and would mean
    code outside connector.py has a direct path to plaintext credentials.
    """
    db.add_device(
        "switch-ciphertext-check", "192.168.10.5", "192.168.10.5",
        "nxos", 22, "netadmin", TEST_DEVICE_PASS,
        session_key=session_key,
    )

    row = db.get_device(1)  # first (and only) device in the isolated DB

    assert row is not None, "get_device returned None — device was not inserted"
    stored_pw = row["password"]

    assert stored_pw.startswith("gAAAA"), (
        f"get_device() should return ciphertext (starts with 'gAAAA'), got: {stored_pw!r}"
    )
    assert stored_pw != TEST_DEVICE_PASS, (
        "get_device() must NOT return the plaintext password"
    )


# ── Test 7: CRED-04 — empty enable_pass handled safely ───────────────────────

def test_empty_enable_pass_safe(isolated_db, session_key):
    """add_device with enable_pass='' must store '' and decrypt_field must return ''.

    Many devices have no enable password.  encrypt_field('') returns '' (not a
    Fernet token) as a guard against Fernet operating on empty bytes.
    db.get_device() should return '' for the enable_pass field.
    db.decrypt_field(session_key, '') must return '' without raising any exception.
    """
    db.add_device(
        "switch-no-enable", "10.20.30.40", "10.20.30.40",
        "eos", 22, "readonly", "readonly_pass",
        enable_pass="",   # no enable password
        session_key=session_key,
    )

    row = db.get_device(1)
    assert row is not None

    assert row["enable_pass"] == "", (
        f"Empty enable_pass should be stored as '', got: {row['enable_pass']!r}"
    )

    # decrypt_field on '' must return '' without raising
    result = db.decrypt_field(session_key, "")
    assert result == "", (
        f"decrypt_field(session_key, '') must return '', got: {result!r}"
    )
