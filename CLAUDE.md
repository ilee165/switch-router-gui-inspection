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
| Structured parsing (Linux/Mac) | pyATS + Genie |
| Structured parsing (all OS) | Netmiko + ntc-templates (TextFSM) |
| SSH / CLI fallback | Netmiko (raw string when no template matches) |
| App authentication | bcrypt + SQLite |
| Device inventory | SQLite (`~/.switch_router_gui/data.db`) |

> **Windows note:** pyATS and Genie are Linux/Mac only. On Windows, the app
> uses Netmiko with TextFSM via `ntc-templates`. Raw CLI output is the final
> fallback. The `GENIE_AVAILABLE` flag in `connector.py` controls which path runs.

---

## Project structure

```
switch-router-gui-inspection/
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

**Three-path pattern in `connector.py`:**
Every fetch function tries Genie first, then Netmiko+TextFSM, then raw CLI.
All public `get_*` functions return `{"source": <sentinel>, "data": <payload>}`.

| `source` | `data` type | When |
|---|---|---|
| `"genie"` | `dict` (nested) | Genie parsed — Linux/Mac only |
| `"textfsm"` | `list[dict]` | Netmiko + NTC template matched |
| `"raw"` | `str` | No template matched; plain CLI text |

Panels check `data["source"]` and branch accordingly.

`_send(conn, command)` wraps `send_command(..., use_textfsm=True)` and returns
`("textfsm", list)` or `("raw", str)`.

`_genie_fetch(device, cmd)` connects via Genie, parses, disconnects. Returns
`dict` or `None` on failure — silent fallthrough preserves three-path strategy.

`run_cli_command()` returns a plain `str` (not a dict) — CLI panel sends
arbitrary commands with no guaranteed template.

**Inheritance pattern in `panels/`:**
- `BasePanel` handles: fetch button, spinner, threading, error handling, status bar signal
- Every panel subclasses `BasePanel` and implements exactly three methods:
  - `_build_content(layout)` — what widgets to show
  - `_run_fetch()` — which connector function to call
  - `_on_result(data)` — what to do with the returned data
- Do not add threading, button logic, or error handling inside individual panels

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

`NO_ENABLE_PLATFORMS = {"eos", "junos"}` — skip `conn.enable()` for these.
`PLATFORM_MAP` in `connector.py` is the single source of truth for platform routing.

---

## Styling rules

- All styles live exclusively in `styles.py` as the `QSS` string
- Do NOT modify `styles.py` or the dark theme under any circumstances
- Widgets are styled by type or by objectName: `widget.setObjectName("primaryBtn")`
- Color palette (reference only — use `PALETTE` in `panels/base.py` for panel code):

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
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
python main.py
```

---

## Claude's rules for this repo

1. **Never rewrite whole files** — always use targeted edits. Show what changed and explain why.
2. **`styles.py` is off-limits** — never change existing colors, fonts, or rules. You MAY add new named selectors for new widgets only.
3. **Explain changes as you make them** — the owner is learning to code. After every edit, explain what changed, where it fits in the architecture, and what concept it demonstrates.
4. **Respect the layering** — panels never touch the database; no business logic in `main.py`; no GUI code in `connector.py`.
5. **Adding a new panel** — subclass `BasePanel`, implement the three required methods, add to `panels/__init__.py`, add a tab in `main.py`.
6. **Adding a new device field** — update in order: `db.py` → `device_manager.py`. Check both `add_device` and `update_device`.
7. **SQL safety** — always use `?` placeholders. Never f-strings in SQL.
8. **Threading** — all network calls go through `_start_worker()` in `BasePanel`. Never block the main GUI thread.

---

## Roadmap

### Active (this milestone — branch: gsd-security-milestone)

- [x] CRED-01: Device passwords encrypted at rest in SQLite (AES-256 via Fernet)
- [x] CRED-02: Encryption key derived from login password (PBKDF2) — never stored on disk
- [x] CRED-03: Existing plaintext passwords migrated to encrypted form on first login
- [x] CRED-04: Decrypted password exists in memory only for the duration of a connection
- [x] SSH-01: First connect to unknown host shows fingerprint dialog (Accept / Reject / Always Trust)
- [x] SSH-02: Accepted host keys stored in SQLite `host_keys` table
- [x] SSH-03: Changed host key on reconnect triggers warning dialog before proceeding
- [x] SSH-04: User can view and delete stored host keys from device settings

### Deferred

- pytest suite (testing milestone)
- Role enforcement for operators (feature milestone)
- Connection pooling / SSH session caching (performance milestone)
- Export to CSV/clipboard (feature milestone)
- `DualTablePanel` base class for `NeighborPanel` + `ArpMacPanel` (refactor milestone)
- Connection health check — "Test Connection" button in `device_manager.py`

---

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow

Entry points:
- `/gsd-quick` — small fixes, doc updates
- `/gsd-debug` — investigation and bug fixing
- `/gsd-execute-phase` — planned phase work

Do not make direct repo edits outside a GSD workflow unless explicitly asked.
<!-- GSD:workflow-end -->
