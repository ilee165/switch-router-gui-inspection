"""
Shared pytest fixtures for RemoteIn tests.

The most important fixture here is `isolated_db`, which redirects db.DB_PATH
to a temporary file created by pytest's tmp_path fixture.  Every test that
imports or exercises db.py should use this fixture so the production DB at
~/.switch_router_gui/data.db is never opened during the test run.

How it works
------------
db.DB_PATH is a module-level Path constant.  Monkeypatching it (and the
get_conn() helper that reads it) before calling db.init_db() means the entire
test session for that test function operates in an isolated, throwaway SQLite
file that is automatically deleted when the tmp_path scope exits.

Usage in tests::

    def test_something(isolated_db):
        import db
        db.add_device(...)  # writes to tmp path, NOT production DB
"""

import pytest
import db


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Redirect db.DB_PATH to a fresh SQLite file under pytest's tmp_path.

    1. Build a path inside the pytest-managed temp directory.
    2. Monkeypatch db.DB_PATH so every subsequent call to db.get_conn() opens
       the temp file instead of the real one.
    3. Call db.init_db() to create the schema in the temp location.
    4. Yield the temp Path so tests can inspect the raw file if needed.
    5. tmp_path cleanup is handled automatically by pytest after the test.
    """
    temp_db = tmp_path / "test_data.db"
    monkeypatch.setattr(db, "DB_PATH", temp_db)
    db.init_db()
    yield temp_db
