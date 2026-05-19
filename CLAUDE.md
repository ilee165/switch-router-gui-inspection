# CLAUDE.md

This file tells Claude how to understand, navigate, and contribute to this repo.
Read this fully before making any changes.

---

## What this repo is

**RemoteIn** — a local desktop GUI for querying Cisco (and other vendor)
network devices over SSH. Built with PyQt6. Runs fully offline.

The primary user is a Network Engineer who is also learning to code.
Claude should balance being a coding assistant AND a coding teacher equally —
explain what code is doing and why, not just fix it silently.

---

## Stack

| Layer | Tool |
|---|---|
| GUI framework | PyQt6 |
| Structured parsing | pyATS + Genie (Linux/Mac only) |
| SSH / CLI fallback | Netmiko |
| App authentication | bcrypt + SQLite |
| Device inventory | SQLite (~/.net_inspector/data.db) |

> **Windows note:** pyATS and Genie are Linux/Mac only. On Windows, the app
> runs entirely on Netmiko and returns raw CLI output. This is expected behavior
> — the code handles it automatically via the `GENIE_AVAILABLE` flag in
> `connector.py`.

---

## Project structure

```
net-inspector/
├── main.py              # App entry point, login dialog, main window
├── db.py                # SQLite — users and device inventory
├── connector.py         # pyATS/Genie + Netmiko connection logic
├── device_manager.py    # Device add/edit/delete dialog
├── user_manager.py      # Admin user management dialog
├── styles.py            # QSS dark theme (amber accent, industrial)
├── requirements.txt     # Python dependencies
├── CLAUDE.md            # This file
└── panels/
    ├── __init__.py      # Exports all panel classes
    ├── base.py          # BasePanel, FetchWorker, make_table, set_cell
    ├── interfaces.py    # Interface status/stats panel
    ├── routing.py       # Routing table panel
    ├── bgp_ospf.py      # BGP and OSPF neighbor panel
    ├── arp_mac.py       # ARP and MAC address table panel
    └── cli.py           # Free-form CLI command panel with history
```

---

## Architecture rules

**Layering — each file only talks to its neighbors:**
- `panels/` calls `connector.py` only — never touches `db.py` directly
- `main.py` calls `db.py` for device data and passes dicts to panels
- `connector.py` has no knowledge of the GUI

**Two-path pattern in `connector.py`:**
Every fetch function tries Genie first (structured data), falls back to
Netmiko (raw CLI) if Genie is unavailable or the parser doesn't exist.
Returns `{"source": "genie", "data": ...}` or `{"source": "raw", "data": ...}`.
Panels check `data["source"]` to decide whether to render a table or raw text.

**Inheritance pattern in `panels/`:**
- `BasePanel` in `base.py` handles: fetch button, spinner, threading, error
  handling, status bar signal
- Every panel subclasses `BasePanel` and implements exactly three methods:
  - `_build_content(layout)` — what widgets to show
  - `_run_fetch()` — which connector function to call
  - `_on_result(data)` — what to do with the returned data
- Do not add threading, button logic, or error handling inside individual panels —
  that all lives in `BasePanel`

---

## Database

- SQLite file lives at `~/.switch_router_gui/data.db`
- Two tables: `users` and `devices`
- Passwords are bcrypt-hashed — never stored or logged as plaintext
- `init_db()` in `db.py` is called once on startup from `main.py`
- Default login seeded on first run: `admin` / `admin`
- SQL queries always use `?` placeholders — never f-strings in SQL

**devices table columns:**
`id, name, hostname, ip_address, platform, port, username, password, enable_pass, notes`

**users table columns:**
`id, username, password, role`  (role is either `'admin'` or `'operator'`)

---

## Supported platforms

| Key | OS |
|---|---|
| `ios` | Cisco IOS |
| `iosxe` | Cisco IOS-XE |
| `iosxr` | Cisco IOS-XR |
| `nxos` | Cisco NX-OS |
| `eos` | Arista EOS |
| `junos` | Juniper JunOS |

Platform keys are stored in the database and mapped to Netmiko device types
via `PLATFORM_MAP` in `connector.py`.

---

## Styling rules

- All styles live exclusively in `styles.py` as the `QSS` string
- Do NOT modify `styles.py` or the dark theme under any circumstances
- Widgets are styled by type (`QPushButton`) or by objectName (`QPushButton#primaryBtn`)
- To apply a named style to a widget: `widget.setObjectName("primaryBtn")`
- Color palette:

| Hex | Role |
|---|---|
| `#1A1A1E` | Main background |
| `#0D0D0F` | Deep background (inputs, tables) |
| `#F59E0B` | Amber accent (focus, headers, selections) |
| `#10B981` | Green (up, success, online) |
| `#EF4444` | Red (down, error, danger) |
| `#6B7280` | Muted grey (secondary text) |
| `#D4D0C8` | Off-white (primary text) |

---

## How to run

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

---

## Claude's rules for this repo

1. **Never rewrite whole files** — always use targeted edits. Show what changed
   and explain why.

2. **Never touch `styles.py`** — the dark theme is intentional and final.

3. **Explain changes as you make them** — the owner is learning to code.
   After every edit, explain what changed, where it fits in the architecture,
   and what concept it demonstrates.

4. **Respect the layering** — don't let panels touch the database, don't put
   business logic in `main.py`, don't put GUI code in `connector.py`.

5. **Before adding a new panel** — subclass `BasePanel`, implement the three
   required methods, add it to `panels/__init__.py`, and add a tab in `main.py`.
   That's the full checklist.

6. **Before adding a new device field** — update in this order:
   `db.py` (table + functions) → `device_manager.py` (form + save logic).
   Check both `add_device` and `update_device`.

7. **SQL safety** — always use `?` placeholders. Never build SQL strings with
   f-strings or concatenation.

8. **Threading** — all network calls go through `_start_worker()` in `BasePanel`.
   Never run blocking network calls on the main GUI thread.

9. **When in doubt about structure** — re-read this file and the architecture
   rules above before making changes.
