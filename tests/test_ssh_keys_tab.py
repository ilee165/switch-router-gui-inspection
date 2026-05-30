"""
Adversarial tests for the SSH Keys tab in DeviceManagerDialog (SSH-04).

Covers the GUI layer of SSH-04 — specifically _load_ssh_keys, _delete_host_key,
and _refresh_list behaviour on the DeviceManagerDialog.

Test strategy
-------------
These tests instantiate DeviceManagerDialog directly using a minimal session key
and an isolated in-memory DB (via the isolated_db fixture from conftest.py).
A session-scoped QApplication is created once per session; PyQt6 requires exactly
one QApplication instance for any QWidget to work without crashing.

The tests call dialog methods directly rather than simulating mouse clicks so
that the GUI logic is exercised deterministically without event-loop interaction.
QMessageBox pop-ups are suppressed via monkeypatching wherever they would block
the test run.

All tests use the `isolated_db` fixture so the production DB at
~/.switch_router_gui/data.db is never opened.

Security checks included:
  - key_blob is NOT displayed in the table (only key_type, fingerprint, added_at)
  - UserRole data in column 0 holds the correct integer key ID for deletion
  - db.delete_host_key is called with key_id= keyword arg (enforced by db.py signature)
  - db.get_device_host_keys is called with device_id= keyword arg (same)
"""

import sys

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

import db
from device_manager import DeviceManagerDialog


# ── QApplication fixture ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    """Create a single QApplication instance for the entire test session.

    PyQt6 requires exactly one QApplication before any QWidget is constructed.
    scope="session" ensures it is created once and reused — creating multiple
    QApplication instances in one process crashes PyQt6.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    # Do NOT call app.quit() or app.exec() — tests are not running an event loop.


# ── Shared test constants ──────────────────────────────────────────────────────

_SALT = b"sshtabtest_salt_"   # 16 bytes — fixed for determinism
_LOGIN_PASS = "test_login_pass"

_HOST = "10.0.0.1"
_PORT = 22
_KEY_TYPE_ED = "ssh-ed25519"
_KEY_TYPE_RSA = "ssh-rsa"
_FP_A = "SHA256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_FP_B = "SHA256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_BLOB_A = "dGVzdGtleWJsb2JB"   # base64("testkeyblob A")
_BLOB_B = "dGVzdGtleWJsb2JC"   # base64("testkeyblob B")


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture()
def session_key(isolated_db):
    """Return a deterministic Fernet key derived from a fixed password + salt."""
    return db.derive_session_key(_LOGIN_PASS, _SALT)


@pytest.fixture()
def device_id(isolated_db, session_key):
    """Insert one device row and return its integer primary key.

    host_keys has a FK to devices(id), so every test that stores host keys
    needs at least one device row or the INSERT raises IntegrityError.
    """
    db.add_device(
        "test-router", _HOST, _HOST,
        "ios", _PORT, "admin", "cisco123",
        enable_pass="", notes="",
        session_key=session_key,
    )
    return db.list_devices()[0]["id"]


@pytest.fixture()
def dialog(qapp, isolated_db, session_key):
    """Create a DeviceManagerDialog with a fresh isolated DB.

    The dialog is not shown (no .show() or .exec()) — we call its methods
    directly to avoid blocking the test runner on a modal event loop.
    """
    dlg = DeviceManagerDialog(session_key=session_key)
    yield dlg
    dlg.close()


# ── Test 1: Empty device shows placeholder; table hidden ───────────────────────

def test_empty_device_shows_placeholder(dialog, device_id):
    """Device with no stored keys: empty-state label visible, table hidden, rowCount=0.

    _load_ssh_keys is the primary entry point for populating the tab. This test
    calls it directly after ensuring no host keys exist for the device.
    """
    dialog._load_ssh_keys(device_id)

    assert not dialog._ssh_empty_label.isHidden(), (
        "_ssh_empty_label must not be hidden when no host keys are stored"
    )
    assert dialog._ssh_table.isHidden(), (
        "_ssh_table must be hidden when no host keys are stored"
    )
    assert dialog._ssh_table.rowCount() == 0, (
        f"rowCount must be 0 with no stored keys, got {dialog._ssh_table.rowCount()}"
    )


# ── Test 2: Device with keys populates table ───────────────────────────────────

def test_device_with_keys_populates_table(dialog, device_id):
    """Two stored host keys: table visible, label hidden, correct column values.

    Verifies that _load_ssh_keys reads key_type, fingerprint, and added_at
    into columns 0, 1, 2 respectively — and does NOT expose key_blob.
    """
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE_ED, fingerprint=_FP_A, key_blob=_BLOB_A,
    )
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE_RSA, fingerprint=_FP_B, key_blob=_BLOB_B,
    )

    dialog._load_ssh_keys(device_id)

    assert dialog._ssh_table.rowCount() == 2, (
        f"Expected 2 rows, got {dialog._ssh_table.rowCount()}"
    )
    assert dialog._ssh_empty_label.isHidden(), (
        "_ssh_empty_label must be hidden when keys are present"
    )
    assert not dialog._ssh_table.isHidden(), (
        "_ssh_table must not be hidden when keys are present"
    )

    # Collect displayed key_type values from column 0
    displayed_key_types = {
        dialog._ssh_table.item(r, 0).text()
        for r in range(dialog._ssh_table.rowCount())
    }
    assert _KEY_TYPE_ED in displayed_key_types, (
        f"Expected key_type {_KEY_TYPE_ED!r} in table, got {displayed_key_types!r}"
    )
    assert _KEY_TYPE_RSA in displayed_key_types, (
        f"Expected key_type {_KEY_TYPE_RSA!r} in table, got {displayed_key_types!r}"
    )

    # Collect displayed fingerprints from column 1
    displayed_fps = {
        dialog._ssh_table.item(r, 1).text()
        for r in range(dialog._ssh_table.rowCount())
    }
    assert _FP_A in displayed_fps, f"Expected {_FP_A!r} in table fingerprints"
    assert _FP_B in displayed_fps, f"Expected {_FP_B!r} in table fingerprints"

    # Security check: key_blob must NOT appear in any visible cell (3 columns)
    for r in range(dialog._ssh_table.rowCount()):
        for c in range(dialog._ssh_table.columnCount()):
            item = dialog._ssh_table.item(r, c)
            if item is not None:
                assert _BLOB_A not in item.text(), (
                    f"key_blob _BLOB_A must not be displayed in table cell ({r},{c})"
                )
                assert _BLOB_B not in item.text(), (
                    f"key_blob _BLOB_B must not be displayed in table cell ({r},{c})"
                )


# ── Test 3: Delete removes row from table and DB ───────────────────────────────

def test_delete_removes_row_from_table_and_db(dialog, device_id, monkeypatch):
    """Delete selected row: table cleared, DB row gone.

    Patches QMessageBox.question to auto-confirm Yes so the test does not block
    on the confirmation dialog. Verifies both the table rowCount and the DB state.
    """
    from PyQt6.QtWidgets import QMessageBox

    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE_ED, fingerprint=_FP_A, key_blob=_BLOB_A,
    )

    dialog._current_device_id = device_id
    dialog._load_ssh_keys(device_id)

    assert dialog._ssh_table.rowCount() == 1, "Pre-condition: table must have 1 row"

    # Auto-confirm the deletion dialog
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **kw: QMessageBox.StandardButton.Yes
    )

    dialog._ssh_table.selectRow(0)
    dialog._delete_host_key()

    assert dialog._ssh_table.rowCount() == 0, (
        f"Expected 0 rows after delete, got {dialog._ssh_table.rowCount()}"
    )
    remaining = db.get_device_host_keys(device_id=device_id)
    assert remaining == [], (
        f"Expected empty list from DB after delete, got {remaining!r}"
    )


# ── Test 4: Delete with no selection shows info message, no crash ──────────────

def test_delete_with_no_selection_does_not_crash(dialog, device_id, monkeypatch):
    """_delete_host_key with no row selected must show info message and not crash.

    Patches QMessageBox.information to a no-op so the dialog box doesn't block.
    The key assertion is that no exception propagates to the test runner.
    """
    from PyQt6.QtWidgets import QMessageBox

    info_called = []
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda *a, **kw: info_called.append(True)
    )

    # Ensure no row is selected (table is empty, so selection is implicitly empty)
    dialog._load_ssh_keys(device_id)  # device has no keys → table is hidden/empty

    # Must not raise
    dialog._delete_host_key()

    assert info_called, (
        "QMessageBox.information must be called when no row is selected"
    )


# ── Test 5: _refresh_list clears SSH tab ──────────────────────────────────────

def test_refresh_list_clears_ssh_tab(dialog, device_id):
    """After _refresh_list(), SSH table must be empty and _current_device_id None.

    Simulates the common scenario: user selects a device (keys loaded), then a
    save/delete action triggers _refresh_list(). The tab must reset to blank.
    """
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE_ED, fingerprint=_FP_A, key_blob=_BLOB_A,
    )

    dialog._current_device_id = device_id
    dialog._load_ssh_keys(device_id)

    assert dialog._ssh_table.rowCount() == 1, "Pre-condition: table should have 1 row"

    dialog._refresh_list()

    assert dialog._ssh_table.rowCount() == 0, (
        f"Expected 0 rows after _refresh_list, got {dialog._ssh_table.rowCount()}"
    )
    assert dialog._current_device_id is None, (
        f"Expected _current_device_id=None after _refresh_list, "
        f"got {dialog._current_device_id!r}"
    )


# ── Test 6: Key ID stored in UserRole data ────────────────────────────────────

def test_key_id_stored_in_userrole(dialog, device_id):
    """Column 0 item's UserRole data must equal the DB primary key for the row.

    The Delete action retrieves the key ID from UserRole data — if this is wrong
    or missing, deletion will either crash or delete the wrong row.
    """
    db.store_host_key(
        device_id=device_id, hostname=_HOST, port=_PORT,
        key_type=_KEY_TYPE_ED, fingerprint=_FP_A, key_blob=_BLOB_A,
    )

    # Get the actual DB row to know the real primary key
    stored_rows = db.get_device_host_keys(device_id=device_id)
    assert len(stored_rows) == 1, "Pre-condition: one row must exist"
    expected_key_id = stored_rows[0]["id"]

    dialog._load_ssh_keys(device_id)

    assert dialog._ssh_table.rowCount() == 1, "Pre-condition: table must have 1 row"
    item = dialog._ssh_table.item(0, 0)
    assert item is not None, "Column 0 item must not be None"

    stored_key_id = item.data(Qt.ItemDataRole.UserRole)
    assert stored_key_id == expected_key_id, (
        f"UserRole key ID {stored_key_id!r} does not match DB id {expected_key_id!r} "
        "— _delete_host_key would delete the wrong row"
    )
