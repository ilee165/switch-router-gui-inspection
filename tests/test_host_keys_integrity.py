"""
Integrity tests for host_keys DB enforcement and connector.py import boundary.

These tests target the three defects fixed in plan 04-08:

  Test 1 (FK enforced): PRAGMA foreign_keys = ON in get_conn means a
      store_host_key call with a non-existent device_id raises
      sqlite3.IntegrityError — the contract documented in the store_host_key
      docstring is now accurate.

  Test 2 (upsert preserves PK): The ON CONFLICT DO UPDATE in store_host_key
      updates an existing row in place — the row's primary key does not change
      between two calls with the same (device_id, hostname, port, key_type)
      tuple and a different fingerprint. Exactly one row exists after both calls.

  Test 3 (connector import boundary): connector.py contains no PyQt6 import,
      no host-key DB function calls, and does contain the allowed
      `from db import decrypt_field`.  Resolves the impossible "connector
      imports no db" checklist item from the original 04-02 plan by narrowing
      it to the accurate audit boundary.

Standalone runner
-----------------
Run directly:  python tests/test_host_keys_integrity.py
Run via pytest: pytest tests/test_host_keys_integrity.py

The pytest path uses the `isolated_db` fixture from conftest.py.
The standalone path patches db.DB_PATH to a tempfile manually.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Allow `python tests/test_host_keys_integrity.py` to find the project root
# modules (db, connector) when run from the repo root or from tests/.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import db


# ── Shared test constants ──────────────────────────────────────────────────────

_SALT       = b"integrity_salt16"   # 16 bytes — fixed for determinism
_LOGIN_PASS = "test_login_pass"
_HOST       = "10.0.0.1"
_PORT       = 22
_KEY_TYPE   = "ssh-ed25519"
_FP_A       = "SHA256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_FP_B       = "SHA256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_BLOB_A     = "dGVzdGtleWJsb2JB"   # base64("testkeyblob A")
_BLOB_B     = "dGVzdGtleWJsb2JC"   # base64("testkeyblob B")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_session_key() -> bytes:
    return db.derive_session_key(_LOGIN_PASS, _SALT)


def _insert_device(session_key: bytes) -> int:
    """Insert a device row and return its id (list_devices after insert)."""
    db.add_device(
        "test-router", _HOST, _HOST,
        "ios", _PORT, "admin", "cisco123",
        enable_pass="", notes="",
        session_key=session_key,
    )
    return db.list_devices()[0]["id"]


# ── Test 1: FK enforcement — non-existent device_id raises IntegrityError ─────

def test_fk_enforced() -> None:
    """store_host_key with a device_id that does not exist must raise IntegrityError.

    Requires PRAGMA foreign_keys = ON in get_conn().  Without that PRAGMA,
    SQLite ignores the REFERENCES devices(id) declaration and silently inserts
    the orphaned row — this test would PASS incorrectly on the old code.
    """
    sk = _make_session_key()
    _insert_device(sk)   # device with id=1 is valid

    try:
        db.store_host_key(
            device_id=999999,   # does NOT exist in devices
            hostname=_HOST,
            port=_PORT,
            key_type=_KEY_TYPE,
            fingerprint=_FP_A,
            key_blob=_BLOB_A,
        )
        raise AssertionError(
            "Expected sqlite3.IntegrityError for non-existent device_id, but no exception raised. "
            "PRAGMA foreign_keys = ON may be missing from get_conn()."
        )
    except sqlite3.IntegrityError:
        pass   # correct — FK enforcement rejected the orphaned row

    print("PASS test_fk_enforced")


# ── Test 2: Upsert preserves PK — ON CONFLICT DO UPDATE, not delete+reinsert ─

def test_upsert_preserves_pk() -> None:
    """Calling store_host_key twice with the same tuple must NOT change the row id.

    With INSERT OR REPLACE the second call would delete the existing row and
    insert a new one with a new autoincremented id.  With ON CONFLICT DO UPDATE
    the existing row is updated in place — id is unchanged.

    Also asserts exactly one row exists after both calls (no phantom duplicate).
    """
    sk = _make_session_key()
    dev_id = _insert_device(sk)

    # First insert
    db.store_host_key(
        device_id=dev_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_A, key_blob=_BLOB_A,
    )
    row_before = db.get_host_key(
        device_id=dev_id, hostname=_HOST, port=_PORT, key_type=_KEY_TYPE
    )
    assert row_before is not None, "Pre-condition: row should exist after first store"
    id_before = row_before["id"]

    # Second call — same tuple, different fingerprint
    db.store_host_key(
        device_id=dev_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE, fingerprint=_FP_B, key_blob=_BLOB_B,
    )
    row_after = db.get_host_key(
        device_id=dev_id, hostname=_HOST, port=_PORT, key_type=_KEY_TYPE
    )
    assert row_after is not None, "Row must still exist after upsert"

    # PK must be unchanged
    id_after = row_after["id"]
    assert id_after == id_before, (
        f"Row id changed: before={id_before}, after={id_after}. "
        "INSERT OR REPLACE deletes+reinserts (churns PK); "
        "ON CONFLICT DO UPDATE preserves it."
    )

    # Fingerprint must reflect the new value
    assert row_after["fingerprint"] == _FP_B, (
        f"Expected fingerprint {_FP_B!r}, got {row_after['fingerprint']!r}"
    )

    # Exactly one row — no phantom duplicate
    all_keys = db.get_device_host_keys(device_id=dev_id)
    assert len(all_keys) == 1, (
        f"Expected exactly 1 row after upsert, got {len(all_keys)}"
    )

    print("PASS test_upsert_preserves_pk")


# ── Test 3: connector.py import boundary — no PyQt6, no host-key DB calls ─────

def test_connector_import_boundary() -> None:
    """connector.py must respect the layering audit boundary documented in 04-08.

    Allowed:  from db import decrypt_field   (pure crypto helper, no I/O)
    Forbidden: import PyQt6 / from PyQt6     (GUI must not leak into connector)
    Forbidden: db.store_host_key / db.get_host_key / db.update_host_key /
               db.delete_host_key / db.get_device_host_keys
               (host key persistence is the verifier's responsibility, injected
               via verifier_fn — connector.py must remain persistence-free)
    """
    connector_path = Path(__file__).parent.parent / "connector.py"
    source = connector_path.read_text(encoding="utf-8")

    # Allowed import must be present
    assert "from db import decrypt_field" in source, (
        "connector.py must contain 'from db import decrypt_field' — "
        "this is the only allowed db import"
    )

    # GUI imports are forbidden — check non-comment lines only.
    # We scan each line after stripping leading whitespace; lines starting
    # with '#' are comments and may legitimately reference PyQt6 by name
    # in the audit boundary documentation comment.
    import_lines = [
        line for line in source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    import_source = "\n".join(import_lines)

    assert "import PyQt6" not in import_source, (
        "connector.py must not contain 'import PyQt6' in non-comment lines — "
        "GUI must not leak into connector"
    )
    assert "from PyQt6" not in import_source, (
        "connector.py must not contain 'from PyQt6' in non-comment lines — "
        "GUI must not leak into connector"
    )

    # Host-key DB functions are forbidden (persistence is the verifier's job)
    forbidden_calls = [
        "db.store_host_key",
        "db.get_host_key",
        "db.update_host_key",
        "db.delete_host_key",
        "db.get_device_host_keys",
    ]
    for fn in forbidden_calls:
        assert fn not in import_source, (
            f"connector.py must not call {fn!r} — host key persistence is the "
            "verifier's responsibility, injected via verifier_fn"
        )

    print("PASS test_connector_import_boundary")


# ── Pytest entry points ────────────────────────────────────────────────────────
# The three functions above are valid pytest test functions (name starts with
# "test_").  The isolated_db fixture from conftest.py redirects db.DB_PATH to
# a temp file and calls db.init_db() before each test.

import pytest   # noqa: E402  (import after functions — avoids import at top for standalone)


@pytest.fixture(autouse=True)
def _reset_db_between_tests(isolated_db):
    """Ensure each test runs in its own isolated, schema-initialized DB."""
    pass   # isolated_db handles patching and init; autouse applies it to all tests


# ── Standalone runner ──────────────────────────────────────────────────────────

def _run_standalone() -> None:
    """Patch db.DB_PATH to a tempfile, run all three tests, print summary.

    Each test gets its own fresh tempfile so they share no state.  On Windows,
    SQLite holds a file lock until the process exits, so we use a separate
    tempfile per test rather than deleting and recreating the same file.
    """
    import traceback

    original_path = db.DB_PATH

    tests = [
        test_fk_enforced,
        test_upsert_preserves_pk,
        test_connector_import_boundary,
    ]
    passed = 0
    failed = 0
    tmp_files: list[str] = []

    for test_fn in tests:
        # Fresh tempfile per test — avoids Windows file-lock issues when
        # trying to delete and recreate the same file within the same process.
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        tmp_files.append(tmp.name)

        db.DB_PATH = Path(tmp.name)
        db.init_db()

        try:
            test_fn()
            passed += 1
        except Exception:
            print(f"FAIL {test_fn.__name__}")
            traceback.print_exc()
            failed += 1

    # Restore original path
    db.DB_PATH = original_path

    # Best-effort cleanup — may fail on Windows due to open file handles;
    # the OS cleans up temp files on process exit regardless.
    for path in tmp_files:
        try:
            os.unlink(path)
        except OSError:
            pass

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_standalone()
