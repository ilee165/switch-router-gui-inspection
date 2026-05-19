import sqlite3
import bcrypt
import os
from pathlib import Path

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

        cur = conn.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            hashed = bcrypt.hashpw("admin".encode(), bcrypt.gensalt())
            conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("admin", hashed , "admin"),
            )

# ── User functions ─────────────────────────────────────────────────────────────

def verify_user(username: str, password: str):
    """Return user row if credentials valid, else None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row and bcrypt.checkpw(password.encode(), row["password"].encode()):
        return dict(row)
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
 
 
def add_device(name, hostname, ip_address, platform, port, username, password, enable_pass="", notes=""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO devices (name, hostname, ip_address, platform, port, username, password, enable_pass, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, hostname, ip_address, platform, port, username, password, enable_pass, notes),
        )
 
 
def update_device(device_id, name, hostname, ip_address, platform, port, username, password, enable_pass="", notes=""):
    with get_conn() as conn:
        conn.execute(
            """UPDATE devices SET name=?, hostname=?, ip_address=?, platform=?, port=?, username=?, password=?,
               enable_pass=?, notes=? WHERE id=?""",
            (name, hostname, ip_address, platform, port, username, password, enable_pass, notes, device_id),
        )
 
 
def delete_device(device_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
 