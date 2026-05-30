# Phase 4: SSH Host Key Verification — Research

**Researched:** 2026-05-29
**Domain:** Paramiko host key policy API, PyQt6 cross-thread dialog synchronization, SQLite schema migration
**Confidence:** HIGH — all findings verified by executing code against the installed library versions

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- D-01: "Accept" and "Always Trust" are both permanent storage actions — both write the key to `host_keys`. No session-only accept.
- D-02: Fingerprint displayed as SHA256:Base64 (OpenSSH standard).
- D-03: Dialog shows hostname/IP, key type, and SHA256:Base64 fingerprint.
- D-04: Window X button (dialog close) = Reject — abort connection, store nothing.
- D-05: Changed key dialog has three buttons: "Connect Anyway" (no update), "Update Key" (replace stored key + connect), "Cancel" (abort).
- D-06: Changed key dialog title "Host Key Changed". Shows both old and new fingerprints. Warning line calls out MITM risk.
- D-07: "Connect Anyway" path shows status bar message: `"Connected (host key mismatch not resolved)"`.
- D-08: SSH-04 is a new "SSH" tab inside the existing `DeviceManagerDialog`.
- D-09: SSH tab uses `make_table()` from `panels/base.py`. Columns: Key Type | Fingerprint | Added.
- D-10: Deletion is the only action in the SSH tab — no re-verify button.

### Claude's Discretion

- `host_keys` table exact schema (guidance given: include both `device_id` and `hostname+port+key_type`).
- Exact Paramiko injection mechanism — researcher/planner decides.
- Cross-thread dialog mechanism — planner decides exact mechanism.
- Fingerprint computation location — `db.py` or connector code.
- "Update Key" exact DELETE predicate.

### Deferred Ideas (OUT OF SCOPE)

- "Re-verify" / "Test Key" button in SSH tab.
- Global Known Hosts manager across all devices.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SSH-01 | On first connect to an unknown host, show fingerprint dialog with Accept / Reject / Always Trust | Paramiko MissingHostKeyPolicy + cross-thread dialog pattern |
| SSH-02 | Accepted host keys stored persistently in `host_keys` table in SQLite | Schema design + CRUD functions in db.py |
| SSH-03 | Stored host key mismatch on reconnect → warning dialog, explicit accept required | Policy checks stored blob vs. live blob; dialog D-05/D-06 |
| SSH-04 | User can view and delete stored host key entries from device settings | SSH tab in DeviceManagerDialog using make_table() |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

| Directive | Implication for Phase 4 |
|-----------|------------------------|
| Never rewrite whole files — targeted edits only | Each plan specifies exact insertion points by line number |
| `styles.py` is off-limits | SSH dialogs use existing QSS selectors (primaryBtn, dangerBtn, sectionHeader) |
| Explain changes as you make them | Plan descriptions must explain what each code block does and why |
| panels/ never touch db.py directly | connector.py never imports db.py or PyQt6 — verifier callable injected |
| All network calls via `_start_worker()` | Host key policy runs on FetchWorker thread; dialog crosses to main thread |
| SQL safety: always `?` placeholders, never f-strings | All host_keys CRUD uses parameterized queries |
| Adding a new device field → update `db.py` then `device_manager.py` | host_keys table: db.py first, then DeviceManagerDialog SSH tab |
| Security rules: no verify=False, no credentials in logs | Policy code must never log key blobs; verify audit required in connector.py plan |

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SSH host key policy enforcement | connector.py | — | Policy runs at Paramiko connection time; connector owns all SSH |
| Host key lookup / storage | db.py | — | All DB access is in db.py; connector never touches DB directly |
| Cross-thread dialog orchestration | FetchWorker (panels/base.py) | main GUI thread | Worker thread triggers dialog; main thread owns all Qt widgets |
| First-connect fingerprint dialog (SSH-01) | host_key_dialog.py (new) or device_manager.py | main.py (status bar) | Qt dialog must live on main thread |
| Changed key warning dialog (SSH-03) | host_key_dialog.py (new) or device_manager.py | main.py (status bar) | Same Qt thread constraint |
| SSH-04 management UI | device_manager.py | db.py (data source) | New SSH tab inside DeviceManagerDialog |
| Status bar notice D-07 | main.py | — | `_set_status()` already wired to panel `status_message` signals |

---

## Paramiko/Netmiko Host Key Policy API

[VERIFIED: executed against paramiko==4.0.0, netmiko==4.7.0 installed in project venv]

### MissingHostKeyPolicy hook signature

```python
class MissingHostKeyPolicy:
    def missing_host_key(self, client, hostname: str, key) -> None:
        # To accept: simply return
        # To reject: raise any Exception (SSHException is conventional)
        pass
```

The `key` parameter is a `paramiko.PKey` subclass instance. At call time, `hostname` is the string passed to `SSHClient.connect()` — the same value as `device["hostname"]` in `_netmiko_device()`.

**Key object API (all verified on live keys):**

| Method/Property | Returns | Use |
|-----------------|---------|-----|
| `key.get_name()` | `str` e.g. `'ssh-rsa'`, `'ecdsa-sha2-nistp256'`, `'ssh-ed25519'` | Key type for display and DB storage |
| `key.asbytes()` | `bytes` — raw public key blob | Blob for DB storage and exact comparison |
| `key.fingerprint` | `str` e.g. `'SHA256:tgi43IGzv0...'` | SHA256:Base64 fingerprint (Paramiko 3.2+) — use directly for display |
| `key.get_fingerprint()` | `bytes` (16 bytes, MD5) | **DO NOT USE** — this is MD5, not the SHA256 format we need |

**Use `key.fingerprint` (the property) — not `key.get_fingerprint()` (the method, which returns MD5).**

`key.fingerprint` is identical to the OpenSSH `ssh-keygen -l` format and was verified to produce the same result as manual `hashlib.sha256(key.asbytes()).digest()` + base64 encoding with trailing `=` stripped.

### How Netmiko exposes the policy

Netmiko's `BaseConnection.__init__` sets `self.key_policy` based on the `ssh_strict` boolean:

```python
if not ssh_strict:
    self.key_policy = paramiko.AutoAddPolicy()   # default — DANGEROUS
else:
    self.key_policy = paramiko.RejectPolicy()
```

`key_policy` is then applied in `_build_ssh_client()` which is called from `_open()` at the end of `__init__`. There is **no direct `key_policy` parameter** to `ConnectHandler`.

**Verified injection mechanism: `auto_connect=False` + attribute assignment before `_open()`:**

```python
conn = ConnectHandler(**device_kwargs, auto_connect=False)
conn.key_policy = RemoteInHostKeyPolicy(verifier_fn)  # inject custom policy
conn._open()                                           # now connects with custom policy
# use conn...
conn.disconnect()
```

This was verified to work: `conn.key_policy` accepts any `MissingHostKeyPolicy` subclass instance after construction with `auto_connect=False`. The `_open()` method is part of Netmiko's public-enough API (not name-mangled).

**Alternative: subclass approach.** Override `_build_ssh_client()`:

```python
class RemoteInSSHClient(BaseConnection):
    def __init__(self, *args, verifier_fn, **kwargs):
        self._verifier_fn = verifier_fn
        super().__init__(*args, **kwargs)  # auto_connect=True OK here
    
    def _build_ssh_client(self):
        client = super()._build_ssh_client()
        client.set_missing_host_key_policy(RemoteInHostKeyPolicy(self._verifier_fn))
        return client
```

**Recommendation: use `auto_connect=False` + attribute assignment.** It is simpler than subclassing, does not require a new class file, and was verified to work. The existing `connector.py` `with ConnectHandler(**...) as conn:` pattern needs to change to explicit construction + `_open()` + `disconnect()` (or a try/finally block), but this is a small, targeted change.

### `_netmiko_device()` integration point

Current code at `connector.py:45`:
```python
"system_host_keys": True,   # SSH-01 placeholder to replace
```

The `system_host_keys` flag must be set to `False` in Phase 4 — we own all host key verification through the custom policy. Leaving it `True` would load the OS known_hosts file and potentially bypass the dialog for already-trusted system keys.

### AutoAddPolicy is prohibited

`paramiko.AutoAddPolicy` silently accepts any server key. The plan must never set `ssh_strict=False` (the Netmiko default) and leave it. The custom `RemoteInHostKeyPolicy` replaces both `AutoAddPolicy` and `RejectPolicy`.

---

## Qt Cross-Thread Dialog Mechanism

[VERIFIED: PyQt6 6.11.0, Qt 6.11.0 installed in project venv]

### The problem

`FetchWorker.run()` executes on a `QThread`. Paramiko calls `missing_host_key()` synchronously during the SSH handshake — the worker thread must **block** waiting for the user's dialog choice before it can return from `missing_host_key()` (accept or raise). Qt dialogs must only be created and shown on the main GUI thread.

### Recommended mechanism: pyqtSignal with `threading.Event`

```python
# In the host key verifier object (lives on main thread as a QObject):
class HostKeyVerifier(QObject):
    # Emitted from worker thread; received on main thread via QueuedConnection
    first_connect_requested = pyqtSignal(str, str, str)   # hostname, key_type, fingerprint
    changed_key_requested   = pyqtSignal(str, str, str, str, str)  # hostname, key_type, old_fp, new_fp, new_blob

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event = threading.Event()
        self._result = {}          # thread-safe write before event.set()

    def verify_first_connect(self, *, hostname: str, key_type: str, fingerprint: str) -> str:
        """Called from worker thread. Blocks until user responds. Returns 'accept' or 'reject'."""
        self._event.clear()
        self._result.clear()
        self.first_connect_requested.emit(hostname, key_type, fingerprint)
        self._event.wait()         # blocks worker thread; main thread is free
        return self._result.get('action', 'reject')

    def _on_first_connect_dialog(self, hostname: str, key_type: str, fingerprint: str):
        """Runs on main thread via QueuedConnection. Shows dialog, sets event."""
        # ... show dialog ...
        self._result['action'] = dialog_result
        self._event.set()          # unblocks worker thread
```

**Why `threading.Event` over `BlockingQueuedConnection`:**

`BlockingQueuedConnection` would require `QMetaObject.invokeMethod()`. In PyQt6, `invokeMethod` uses `QGenericArgument` — its API is complex and not pythonic. `threading.Event` achieves the same blocking behavior with simpler, testable Python code. Both are correct; `threading.Event` is the cleaner implementation for this codebase.

**Why not `BlockingQueuedConnection` directly on the signal:**

PyQt6's `signal.connect(slot, type=Qt.ConnectionType.BlockingQueuedConnection)` would block the worker thread but requires the slot to set some return value mechanism anyway — `threading.Event` makes that return mechanism explicit and readable.

**Thread safety guarantee:** `self._result` is written on the main thread BEFORE `event.set()` is called, and read on the worker thread AFTER `event.wait()` returns. No mutex needed — the Event provides the happens-before relationship.

### Connection type for the signal

```python
verifier.first_connect_requested.connect(
    verifier._on_first_connect_dialog,
    Qt.ConnectionType.QueuedConnection   # explicit for clarity; AutoConnection would also queue it
)
```

`QueuedConnection` is correct because the emitter (worker thread) and receiver (main thread) are in different threads — Qt will dispatch to the main thread's event loop automatically.

### Dependency injection — the "three-body problem"

`connector.py` cannot import `db.py` or `PyQt6`. The verifier callable is injected at call time:

```python
# connector.py signature change:
def get_interfaces(device: dict, session_key: bytes, *, host_key_verifier=None) -> dict:
    ...
    conn = ConnectHandler(**_netmiko_device(device, session_key), auto_connect=False)
    if host_key_verifier is not None:
        conn.key_policy = RemoteInHostKeyPolicy(host_key_verifier)
    conn._open()
    ...
```

`RemoteInHostKeyPolicy` in `connector.py` calls `host_key_verifier(hostname, key_type, fingerprint, key_blob)` — a plain callable — and either returns (accept) or raises `SSHException` (reject). It has no knowledge of Qt or SQLite.

The `HostKeyVerifier` object (which does know about Qt and db.py) is created in the panel layer and passed in. This keeps all three concerns — SSH, DB, GUI — in their correct architectural tiers.

---

## SQLite Migration Pattern

[VERIFIED: confirmed against db.py lines 17-47 and tested SQLite behavior directly]

### Table creation — confirmed pattern

Add `host_keys` table creation inside the `executescript` block in `init_db()`:

```python
conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (...);
    CREATE TABLE IF NOT EXISTS devices (...);
    CREATE TABLE IF NOT EXISTS host_keys (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
        hostname    TEXT NOT NULL,
        port        INTEGER NOT NULL DEFAULT 22,
        key_type    TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        key_blob    TEXT NOT NULL,
        added_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(device_id, hostname, port, key_type)
    );
""")
```

**Critical gotcha verified:** `DEFAULT (datetime('now'))` raises `sqlite3.OperationalError: default value of column is not constant` inside `executescript`. Use `DEFAULT CURRENT_TIMESTAMP` instead — SQLite's built-in constant. This is a real pitfall that will break `init_db()` on first run if not handled.

### UNIQUE constraint

`UNIQUE(device_id, hostname, port, key_type)` is the binding item from 04-REVIEWS.md. This prevents duplicate entries and makes the "Update Key" DELETE+INSERT atomic at the DB constraint level. Verified: a duplicate INSERT correctly raises `sqlite3.IntegrityError`.

### Foreign key cascade — important caveat

`ON DELETE CASCADE` in the schema does NOT automatically work. SQLite requires `PRAGMA foreign_keys = ON` per connection to enforce it. `db.py`'s `get_conn()` does not set this pragma.

**Decision for plan:** Modify `delete_device()` to explicitly delete host_keys rows before deleting the device row:

```python
def delete_device(device_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM host_keys WHERE device_id = ?", (device_id,))
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
```

This is safer than enabling FK enforcement globally, which could affect existing code paths in ways that are hard to predict.

### No ALTER TABLE needed for host_keys

`host_keys` is a new table (not an existing table getting a new column), so no `try/except OperationalError` guard is needed for the table itself. The `try/except` pattern from `db.py:44-47` applies only to `ALTER TABLE ADD COLUMN`. `CREATE TABLE IF NOT EXISTS` is idempotent.

---

## Paramiko Key Type, Blob, and Fingerprint Extraction

[VERIFIED: executed against paramiko==4.0.0]

### In the MissingHostKeyPolicy hook

```python
class RemoteInHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, verifier_fn):
        self._verify = verifier_fn   # keyword-only enforced at construction

    def missing_host_key(self, client, hostname: str, key) -> None:
        key_type    = key.get_name()           # e.g. 'ecdsa-sha2-nistp256'
        fingerprint = key.fingerprint          # e.g. 'SHA256:uNiVztksCsDhcc0u9e8B...'
        key_blob    = base64.b64encode(key.asbytes()).decode()  # for DB storage

        action = self._verify(
            hostname=hostname,
            key_type=key_type,
            fingerprint=fingerprint,
            key_blob=key_blob,
        )
        if action == 'reject':
            raise paramiko.SSHException(f"User rejected host key for {hostname!r}")
        # returning normally = accept
```

### Fingerprint format verification

`key.fingerprint` (the property, added in Paramiko 3.2, available in our installed 4.0.0) produces the exact same string as manual computation:

```python
import hashlib, base64
manual = 'SHA256:' + base64.b64encode(
    hashlib.sha256(key.asbytes()).digest()
).decode().rstrip('=')
assert key.fingerprint == manual  # verified True
```

**Use `key.fingerprint` directly** — no manual computation needed.

### Key type strings

| Key algorithm | `key.get_name()` returns |
|---------------|-------------------------|
| RSA | `'ssh-rsa'` |
| ECDSA P-256 | `'ecdsa-sha2-nistp256'` |
| ECDSA P-384 | `'ecdsa-sha2-nistp384'` |
| Ed25519 | `'ssh-ed25519'` |

These are the strings stored in `host_keys.key_type` and displayed in the SSH tab "Key Type" column.

### Comparison for SSH-03 (changed key detection)

```python
# Lookup: SELECT * FROM host_keys WHERE device_id=? AND hostname=? AND port=? AND key_type=?
# If found:
stored_blob = row['key_blob']
new_blob    = base64.b64encode(key.asbytes()).decode()
if stored_blob != new_blob:
    # SSH-03: key has changed — show warning dialog
    ...
else:
    # Keys match — silent accept, return from missing_host_key
    return
```

Blob comparison is direct string equality after base64 encoding — no cryptographic comparison function needed since both values use the same encoding.

### where fingerprints are computed

Compute `fingerprint` using `key.fingerprint` in `connector.py`'s `RemoteInHostKeyPolicy` and pass it to the verifier callable. Store it in the DB. This avoids re-computation in `db.py` and keeps the Paramiko dependency in `connector.py` where it belongs. `db.py` functions accept `fingerprint` as a string argument.

---

## host_keys Table CRUD Design

### Schema (final)

```sql
CREATE TABLE IF NOT EXISTS host_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    hostname    TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 22,
    key_type    TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    key_blob    TEXT NOT NULL,
    added_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(device_id, hostname, port, key_type)
);
```

### Required db.py functions (all keyword-only security params)

```python
def get_host_key(*, device_id: int, hostname: str, port: int, key_type: str) -> dict | None:
    """Return stored host_key row or None if not found."""

def add_host_key(*, device_id: int, hostname: str, port: int,
                 key_type: str, fingerprint: str, key_blob: str) -> None:
    """Insert a new trusted host key. Raises IntegrityError on duplicate."""

def update_host_key(*, device_id: int, hostname: str, port: int,
                    key_type: str, fingerprint: str, key_blob: str) -> None:
    """Replace stored key (DELETE + INSERT). Used for 'Update Key' action."""

def list_host_keys(device_id: int) -> list[dict]:
    """Return all stored keys for a device. Used by SSH tab in device_manager."""

def delete_host_key(host_key_id: int) -> None:
    """Delete a single host key row by ID. Used by SSH tab Delete button."""

def delete_host_keys_for_device(device_id: int) -> None:
    """Delete all host keys for a device. Called by delete_device()."""
```

All parameters that carry cryptographic data (`key_blob`, `fingerprint`, `key_type`) must be keyword-only (per binding item #1 from 04-REVIEWS.md).

---

## Architecture: How the Three Files Connect

```
FetchWorker thread                    Main GUI thread
─────────────────────────────         ──────────────────────────────────
connector.get_interfaces(             HostKeyVerifier._on_dialog()
  device, session_key,                  ↓ shows Qt dialog
  host_key_verifier=verifier)           ↓ stores result in dict
  ↓                                     ↓ event.set()
  ConnectHandler(auto_connect=False)
  conn.key_policy = RemoteInHostKeyPolicy(verifier)
  conn._open()
    → Paramiko SSH handshake
    → policy.missing_host_key(client, hostname, key)
        → verifier.verify(hostname, key_type, fp, blob)
            → emit signal (QueuedConnection)
            → event.wait()   ←───── blocks here ←─── main thread handles dialog
            ← event set, read result
        → return (accept) or raise SSHException (reject)
  conn connects (or raises)
```

---

## DeviceManagerDialog SSH Tab Architecture

### Current structure (no QTabWidget)

`DeviceManagerDialog._build_ui()` uses a `QSplitter` with a left `QListWidget` (device inventory) and a right `QVBoxLayout` containing `DeviceFormWidget` directly.

### Required change for SSH tab

Wrap the right panel in a `QTabWidget`:
- Tab 0: "Device Details" — contains the existing `DeviceFormWidget`
- Tab 1: "SSH Keys" — new widget with `make_table(["Key Type", "Fingerprint", "Added"])` + "DELETE KEY" button

`QTabWidget` is not currently imported in `device_manager.py` — must add to imports.

### SSH tab behavior

- SSH tab is only populated when a device is selected from the list (`_on_item_clicked`)
- Clicking "Delete" removes the selected row from `host_keys` and calls `db.delete_host_key(id)`
- No action if no row selected — show `QMessageBox.warning`
- `device_id` is stored as `Qt.ItemDataRole.UserRole` on each table row for the delete call (same pattern as the device list)

### Session key: SSH tab does NOT need it

The SSH tab only reads and deletes `host_keys` rows — no credential decryption needed. `DeviceManagerDialog._session_key` is available if needed, but the SSH tab functions do not use it.

---

## Plan Decomposition

### Recommended breakdown: 5 PLAN files

| Plan | Covers | Wave |
|------|--------|------|
| `04-01-PLAN.md` | DB layer: `host_keys` table schema + CRUD functions in `db.py`, `delete_device()` cascade fix | Wave 1 |
| `04-02-PLAN.md` | `connector.py`: `RemoteInHostKeyPolicy` class, `auto_connect=False` injection pattern, `system_host_keys=False`, verifier param added to all public connector functions, security audit sub-task | Wave 1 |
| `04-03-PLAN.md` | `HostKeyVerifier` QObject + cross-thread dialog (first-connect SSH-01 dialog + changed-key SSH-03 dialog) in `host_key_dialog.py` | Wave 2 |
| `04-04-PLAN.md` | Wire verifier into panels: pass `host_key_verifier` from `BasePanel._start_worker` → connector functions; status bar D-07 integration | Wave 2 |
| `04-05-PLAN.md` | SSH-04 UI: add SSH tab to `DeviceManagerDialog` with `make_table()` + delete action | Wave 2 |
| `04-06-PLAN.md` | Verification: adversarial test checklist (reject path, tampered row, dialog cancelled, key not stored after Reject), security posture audit | Wave 3 |

**Wave 1** (Plans 1-2): Pure Python, no Qt. Can be written and tested with `python -c` scripts. No UI needed.

**Wave 2** (Plans 3-5): Qt dialog and wiring. Requires the app to run. Dependencies on Wave 1 completing.

**Wave 3** (Plan 6): Verification only.

### Alternative: 4 plans

If the planner prefers fewer files, Plans 3+4 can merge (dialog code + wiring together). Plans 1+2 should stay separate — DB and connector are independent and touch different files.

---

## Key Risks

### Risk 1: `_open()` is semi-private (MEDIUM)

`BaseConnection._open()` is not documented as a public API. It could change in future Netmiko versions. Mitigation: pin `netmiko>=4.7.0,<5.0.0` in `requirements.txt`, or use the subclass approach (overriding `_build_ssh_client()`) which uses only the documented hook `_get_ssh_client_instance()`. The subclass approach is slightly more robust to future Netmiko changes.

**Planner decision required:** `auto_connect=False + _open()` (simpler) vs. subclass `_build_ssh_client()` (more robust). Both verified to work.

### Risk 2: `threading.Event.wait()` with no timeout (LOW-MEDIUM)

If the dialog is never shown (e.g., the main thread is blocked), `event.wait()` blocks forever and hangs the worker thread. Mitigation: add `timeout=30` to `event.wait()` and treat timeout as 'reject'. Plan must specify this timeout explicitly.

### Risk 3: `system_host_keys=True` currently in production (LOW)

`connector.py:45` currently sets `"system_host_keys": True`. This loads the OS `~/.ssh/known_hosts` and means connections to hosts already in known_hosts will never trigger `missing_host_key()`. Phase 4 must set this to `False` so all key verification goes through the custom policy.

### Risk 4: Dialog called before HostKeyVerifier is connected (MEDIUM)

If `connector.py` functions are called without `host_key_verifier` provided (e.g., from a code path that hasn't been updated), the default `None` means the old behavior runs — which is `system_host_keys=True` if not also changed. Plan must update ALL six public connector functions (`get_interfaces`, `get_routing_table`, `get_bgp_neighbors`, `get_ospf_neighbors`, `get_arp_table`, `get_mac_table`, `run_cli_command`) and verify none are missed.

### Risk 5: X-button on dialog (covered by D-04, but needs explicit code path)

Qt `QDialog.exec()` returns `QDialog.DialogCode.Rejected` (value 0) when the user closes with the X button. The dialog must return 'reject' for this case explicitly — it cannot rely on a button click signal alone.

### Risk 6: "Connect Anyway" leaves inconsistent state for next `missing_host_key()` call (LOW)

If the user clicks "Connect Anyway" (D-05), the stored key is NOT updated. On the next connection, `missing_host_key()` will fire again with the same mismatch. This is correct behavior (D-05 says the warning reappears). The plan must document this so the implementer does not accidentally update the stored key.

---

## Code Examples

### RemoteInHostKeyPolicy (connector.py)

```python
# Source: Verified against paramiko==4.0.0 installed in project venv
import base64
import paramiko

class RemoteInHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Custom Paramiko host key policy for RemoteIn.
    
    Calls verifier_fn to look up stored keys and show dialogs.
    Never imports db.py or PyQt6 — those are the caller's concern.
    """
    def __init__(self, verifier_fn):
        self._verify = verifier_fn

    def missing_host_key(self, client, hostname: str, key) -> None:
        key_type    = key.get_name()
        fingerprint = key.fingerprint          # SHA256:Base64, Paramiko 3.2+
        key_blob    = base64.b64encode(key.asbytes()).decode()

        action = self._verify(
            hostname=hostname,
            key_type=key_type,
            fingerprint=fingerprint,
            key_blob=key_blob,
        )
        if action == 'reject':
            raise paramiko.SSHException(
                f"User rejected host key for {hostname!r}"
            )
        # returning = accept
```

### ConnectHandler injection (connector.py)

```python
# Replace: with ConnectHandler(**_netmiko_device(device, session_key)) as conn:
# With (pseudo-code showing the pattern):
kwargs = _netmiko_device(device, session_key)
conn = ConnectHandler(**kwargs, auto_connect=False)
if host_key_verifier is not None:
    conn.key_policy = RemoteInHostKeyPolicy(host_key_verifier)
try:
    conn._open()
    if device["platform"] not in NO_ENABLE_PLATFORMS:
        conn.enable()
    source, data = _send(conn, "show interfaces")
finally:
    conn.disconnect()
```

### host_keys table schema (db.py)

```sql
-- CURRENT_TIMESTAMP not datetime('now') — executescript requires constant defaults
CREATE TABLE IF NOT EXISTS host_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    hostname    TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 22,
    key_type    TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    key_blob    TEXT NOT NULL,
    added_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(device_id, hostname, port, key_type)
);
```

### Cross-thread dialog skeleton (host_key_dialog.py)

```python
# Source: Verified against PyQt6 6.11.0
import threading
from PyQt6.QtCore import QObject, pyqtSignal, Qt

class HostKeyVerifier(QObject):
    first_connect_requested = pyqtSignal(str, str, str)   # hostname, key_type, fingerprint
    changed_key_requested   = pyqtSignal(str, str, str, str, str)  # hostname, key_type, old_fp, new_fp, new_blob

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event  = threading.Event()
        self._result: dict = {}
        # Signals connected to _on_*() slots via QueuedConnection from caller

    def __call__(self, *, hostname: str, key_type: str,
                 fingerprint: str, key_blob: str) -> str:
        """Callable passed to RemoteInHostKeyPolicy. Runs on worker thread."""
        # ... lookup stored key from db (injected reference to db functions)
        # ... emit appropriate signal
        # ... event.wait(timeout=30)
        return self._result.get('action', 'reject')

    def _set_result_and_unblock(self, action: str):
        """Called from main-thread slot after dialog closes."""
        self._result['action'] = action
        self._event.set()
```

---

## Security Domain

`security_enforcement: true`, `security_asvs_level: 1` per config.json.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Indirectly | SSH host key = server authentication; reject unknown keys |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes | Fingerprint strings must be validated before DB storage |
| V6 Cryptography | Yes | SHA256 for fingerprint (not MD5); raw blob comparison for key matching |
| V9 Communications | Yes | HTTPS/SSH only; no plaintext; TLS cert validation untouched |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Man-in-the-middle on first connect | Spoofing | SHA256 fingerprint shown; user must explicitly accept |
| Key substitution attack (SSH-03) | Tampering | Blob comparison; changed key dialog with MITM warning |
| Fingerprint display spoofing | Spoofing | Use `key.fingerprint` (computed from wire bytes), not user-supplied string |
| Key blob stored as string allows injection | Tampering | base64 encoding normalizes blob; `?` placeholders prevent SQL injection |
| Dialog timeout hangs worker thread | DoS | `threading.Event.wait(timeout=30)` — treat timeout as reject |
| Key not cleared after Reject | Information Disclosure | Plan must verify: Reject path stores nothing (adversarial test required) |

### connector.py security audit checklist (binding per 04-REVIEWS.md #3)

Every plan touching `connector.py` must include a sub-task:
- grep for `strict_host_key_checking` — must not be `False`
- grep for `verify=False` — must not exist
- grep for `disabled_algorithms` — must not include SHA-2 downgrade
- grep for `allow_agent=True` — must not exist (it's `False` in current `_netmiko_device`)
- confirm `system_host_keys` is removed/False after Phase 4 change

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `auto_connect=False` + setting `conn.key_policy` then calling `conn._open()` will remain stable for `netmiko>=4.7.0,<5.0.0` | Paramiko/Netmiko API | If Netmiko changes `_open()` in a patch, the injection breaks; mitigate by pinning version |
| A2 | `key.fingerprint` property is available on all key types (RSA, ECDSA, Ed25519) since Paramiko 3.2 | Key API | Ed25519 `generate()` not tested (method not available); `fingerprint` property verified present on Ed25519Key class |

All other claims are VERIFIED against installed library versions.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| paramiko | MissingHostKeyPolicy, key API | Yes | 4.0.0 | — |
| netmiko | ConnectHandler, auto_connect=False | Yes | 4.7.0 | — |
| PyQt6 | Dialog, QObject, pyqtSignal, threading | Yes | 6.11.0 | — |
| SQLite | host_keys table, CURRENT_TIMESTAMP | Yes | stdlib | — |
| threading | threading.Event for cross-thread sync | Yes | stdlib | — |

No missing dependencies.

---

## Sources

### Primary (HIGH confidence — verified by execution)
- `paramiko==4.0.0` installed in project venv — `MissingHostKeyPolicy`, `PKey.fingerprint`, `PKey.asbytes()`, `PKey.get_name()` verified via `inspect.getsource()` and live key generation
- `netmiko==4.7.0` installed in project venv — `BaseConnection.__init__`, `_build_ssh_client()`, `_open()`, `key_policy` attribute lifecycle verified via `inspect.getsource()`
- `PyQt6==6.11.0` installed in project venv — `BlockingQueuedConnection`, `QueuedConnection`, `QMetaObject.invokeMethod` verified via `help()` and enum inspection
- SQLite stdlib — `CURRENT_TIMESTAMP` default, `UNIQUE` constraint, `IntegrityError` behavior verified via live test database

### Secondary (HIGH confidence — codebase)
- `connector.py` — `_netmiko_device()` integration point at line 45 verified by direct read
- `db.py` — `executescript` pattern at lines 19-47 verified; `try/except OperationalError` for column additions; `get_conn()` confirmed no FK pragma
- `device_manager.py` — `DeviceManagerDialog` structure verified; no existing `QTabWidget`; `session_key` flows from `main.py._open_device_manager()` at line 226
- `panels/base.py` — `make_table()`, `FetchWorker`, `PALETTE` verified for reuse

---

## Metadata

**Confidence breakdown:**
- Paramiko API: HIGH — verified by executing code against installed library
- Netmiko injection mechanism: HIGH — verified via live object inspection
- Qt cross-thread pattern: HIGH — verified Qt version, connection types, and `threading.Event` mechanism
- SQLite schema: HIGH — verified schema creation, CURRENT_TIMESTAMP constraint, UNIQUE behavior, and FK enforcement requirement
- Plan decomposition: MEDIUM — based on codebase structure analysis; planner may adjust wave boundaries

**Research date:** 2026-05-29
**Valid until:** 2026-06-29 (stable libraries; Paramiko/Netmiko/PyQt6 are slow-moving)
