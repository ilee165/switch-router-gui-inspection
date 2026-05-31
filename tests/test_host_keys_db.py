"""
Adversarial tests for the host_keys table CRUD functions in db.py.

Covers SSH-01 through SSH-04 at the database layer:

  SSH-01 / SSH-02 — store_host_key() and get_host_key() back the first-connect
                    fingerprint dialog: Accept stores a key, Reject must NOT.
  SSH-03          — update_host_key() backs the changed-key warning dialog.
  SSH-04          — delete_host_key() and get_device_host_keys() back the SSH tab.

All tests use the `isolated_db` fixture from conftest.py, which redirects
db.DB_PATH to a pytest tmp_path so the production DB at
~/.switch_router_gui/data.db is never opened or modified.

Test strategy
-------------
These are *adversarial* tests — they target the exact failure modes the plan
identified: UNIQUE constraint collision, absent-row reads, cascade delete
correctness, update reflection, and keyword-only parameter enforcement.

A helper fixture `device_id` inserts one device row before each test so that
store_host_key FK constraint is satisfied. The raw password is encrypted with
a fixed session key to match add_device's signature.
"""

import inspect

import pytest

import db

# ── Shared test constants ──────────────────────────────────────────────────────

_SALT = b"hostkeytest_salt"   # 16 bytes — fixed for determinism
_LOGIN_PASS = "test_login_pass"

_HOST = "10.0.0.1"
_PORT = 22
_KEY_TYPE = "ssh-ed25519"
_FP_A = "SHA256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_FP_B = "SHA256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_BLOB_A = "dGVzdGtleWJsb2JB"   # base64("testkeyblob A")
_BLOB_B = "dGVzdGtleWJsb2JC"   # base64("testkeyblob B")


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def session_key(isolated_db):
    """Return a deterministic Fernet key, same pattern as test_encryption.py."""
    return db.derive_session_key(_LOGIN_PASS, _SALT)


@pytest.fixture()
def device_id(isolated_db, session_key):
    """Insert one device row and return its integer primary key.

    host_keys has a FK to devices(id), so every host-key test needs at least
    one device row or the INSERT will raise sqlite3.IntegrityError.
    """
    db.add_device(
        "test-router", _HOST, _HOST,
        "ios", _PORT, "admin", "cisco123",
        enable_pass="", notes="",
        session_key=session_key,
    )
    # The isolated_db starts empty so this device gets id=1.
    row = db.list_devices()[0]
    return row["id"]


# ── Test 1: UNIQUE constraint — INSERT OR REPLACE replaces the existing row ───

def test_unique_constraint_upsert(isolated_db, device_id):
    """Calling store_host_key twice with the same tuple must update, not duplicate.

    The UNIQUE(device_id, hostname, port, key_type) constraint combined with
    INSERT OR REPLACE means the second call replaces the first row atomically.
    After both calls:
      - get_host_key returns the NEW fingerprint (_FP_B), not the original.
      - get_device_host_keys returns exactly one row (no phantom duplicate).
    """
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_A, key_blob=_BLOB_A,
    )
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_B, key_blob=_BLOB_B,
    )

    row = db.get_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT, key_type=_KEY_TYPE
    )
    assert row is not None, "get_host_key returned None after two store_host_key calls"
    assert row["fingerprint"] == _FP_B, (
        f"Expected updated fingerprint {_FP_B!r}, got {row['fingerprint']!r}"
    )

    all_keys = db.get_device_host_keys(device_id=device_id)
    assert len(all_keys) == 1, (
        f"Expected exactly 1 row after upsert, got {len(all_keys)}"
    )


# ── Test 2: Reject path — get_host_key returns None for an unstored tuple ─────

def test_reject_path_leaves_no_trace(isolated_db, device_id):
    """get_host_key for a tuple never passed to store_host_key must return None.

    This validates the Reject code path (dialog dismissed without storing).
    The DB must not auto-populate and get_device_host_keys must return [].
    Calling get_host_key is read-only and must never raise an exception for a
    missing row — None is the contract.
    """
    result = db.get_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT, key_type=_KEY_TYPE
    )
    assert result is None, (
        f"Expected None for an unstored key, got {result!r}"
    )

    all_keys = db.get_device_host_keys(device_id=device_id)
    assert all_keys == [], (
        f"Expected empty list for a device with no stored keys, got {all_keys!r}"
    )


# ── Test 3: Cascade delete — host_keys removed when device is deleted ─────────

def test_cascade_delete_removes_host_keys(isolated_db, device_id):
    """delete_device() must remove associated host_keys rows in the same transaction.

    db.py enables PRAGMA foreign_keys = ON in get_conn(), so SQLite enforces the
    REFERENCES devices(id) constraint on host_keys. delete_device() explicitly
    DELETEs host_keys rows first (belt-and-suspenders) before removing the device
    row, ensuring both rows are gone atomically even on older SQLite builds where
    FK cascade semantics vary by compile option.

    This test catches regressions where the explicit DELETE FROM host_keys is
    removed -- without it, the FK constraint would block the device DELETE and
    raise IntegrityError (or orphan the rows if PRAGMA foreign_keys is ever
    inadvertently disabled).
    """
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_A, key_blob=_BLOB_A,
    )

    # Confirm the key exists before deletion
    assert db.get_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT, key_type=_KEY_TYPE
    ) is not None, "Pre-condition: host key should exist before device delete"

    db.delete_device(device_id)

    remaining = db.get_device_host_keys(device_id=device_id)
    assert remaining == [], (
        f"Expected [] after delete_device, got {remaining!r} "
        "(host_keys cascade delete may be missing)"
    )


# ── Test 4: Update reflects new key_blob — simulates "Update Key" dialog ──────

def test_update_host_key_reflects_new_value(isolated_db, device_id):
    """update_host_key() must replace fingerprint and key_blob for the stored tuple.

    Simulates the D-05 "changed key" dialog: the user clicks "Update Key",
    which calls update_host_key with new material.  get_host_key must return
    the replacement values, not the originals.  The added_at column is also
    reset by UPDATE so this tests the full UPDATE path, not INSERT OR REPLACE.
    """
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_A, key_blob=_BLOB_A,
    )

    db.update_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_B, key_blob=_BLOB_B,
    )

    row = db.get_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT, key_type=_KEY_TYPE
    )
    assert row is not None, "get_host_key returned None after update_host_key"
    assert row["fingerprint"] == _FP_B, (
        f"Expected updated fingerprint {_FP_B!r}, got {row['fingerprint']!r}"
    )
    assert row["key_blob"] == _BLOB_B, (
        f"Expected updated key_blob {_BLOB_B!r}, got {row['key_blob']!r}"
    )


# ── Test 5: Keyword-only enforcement — static parameter inspection ─────────────

def test_all_crud_functions_are_keyword_only(isolated_db):
    """All five host_keys CRUD functions must have zero positional parameters.

    Uses inspect.signature to verify the * separator is present in every
    function signature.  A positional parameter would allow callers to pass
    device_id and key_type in the wrong order silently — the keyword-only
    contract makes that a TypeError at the call site instead.

    This is a static check: no DB interaction is needed.
    """
    target_functions = [
        "store_host_key",
        "get_host_key",
        "update_host_key",
        "delete_host_key",
        "get_device_host_keys",
    ]

    for fn_name in target_functions:
        fn = getattr(db, fn_name)
        sig = inspect.signature(fn)
        positional_params = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY)
        ]
        assert positional_params == [], (
            f"{fn_name} has positional parameters {positional_params!r} — "
            "all security-relevant parameters must be keyword-only (* separator)"
        )


# ── Test 6: delete_host_key is a no-op for a missing row ──────────────────────

def test_delete_host_key_missing_row_is_noop(isolated_db, device_id):
    """delete_host_key() must not raise when the row does not exist.

    The SSH-04 Delete button may fire after the UI has already refreshed and
    the selected key_id is stale.  A no-op (not an exception) is the correct
    behavior.
    """
    # No key has been stored — delete a non-existent id
    db.delete_host_key(key_id=99999)
    # If we reach here without an exception, the no-op contract is satisfied


# ── Test 7: get_device_host_keys ordering — newest first ──────────────────────

def test_get_device_host_keys_ordered_newest_first(isolated_db, device_id):
    """get_device_host_keys must return rows ordered by added_at DESC.

    We store two keys with different key_types.  Because CURRENT_TIMESTAMP
    resolution is one second and both inserts may land in the same second,
    we use update_host_key on the first row to bump its added_at — guaranteeing
    a deterministic ordering without needing time.sleep().
    """
    # Store RSA key first, then ED25519
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type="ssh-rsa", fingerprint=_FP_A, key_blob=_BLOB_A,
    )
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_B, key_blob=_BLOB_B,
    )
    # Bump added_at on the ED25519 row so it is definitively the newest
    db.update_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_B, key_blob=_BLOB_B,
    )

    rows = db.get_device_host_keys(device_id=device_id)
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    # ED25519 was bumped last — it must appear first
    assert rows[0]["key_type"] == _KEY_TYPE, (
        f"Expected newest key_type {_KEY_TYPE!r} first, got {rows[0]['key_type']!r}"
    )
