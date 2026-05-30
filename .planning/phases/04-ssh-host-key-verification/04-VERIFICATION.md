---
phase: 04-ssh-host-key-verification
verified: 2026-05-30T04:06:28Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Connect to an unknown SSH host and confirm the first-connect dialog appears"
    expected: "Dialog titled 'Unknown Host Key' appears with hostname, key type, SHA256 fingerprint, and three buttons: Reject / Accept Once / Always Trust"
    why_human: "Requires a live SSH target or mock SSH server; cannot verify dialog presentation without a running app and real Paramiko handshake"
  - test: "Click 'Always Trust' on first-connect dialog and verify key is stored in host_keys table"
    expected: "Connection proceeds, DB row exists in host_keys with correct device_id, hostname, key_type, fingerprint"
    why_human: "Requires live SSH connection and DB inspection"
  - test: "Click 'Reject' on first-connect dialog and verify no DB row is created"
    expected: "Connection aborted, status bar shows 'ERROR: Host key rejected by user', zero rows in host_keys"
    why_human: "Requires live SSH connection"
  - test: "Reconnect to the same host after 'Always Trust' and verify silent reconnect (no dialog)"
    expected: "No dialog appears, connection completes, panel data loads normally"
    why_human: "Requires live SSH connection with key already stored"
  - test: "Manually corrupt the stored key_blob in host_keys and reconnect"
    expected: "Dialog titled 'Host Key Changed' appears, showing both stored and new fingerprints, with MITM warning text, and three buttons: Cancel / Connect Anyway / Update Key"
    why_human: "Requires live SSH connection and direct DB manipulation"
  - test: "Open Device Manager, click a device with a stored host key, click SSH Keys tab"
    expected: "Table shows stored key with columns Key Type / Fingerprint / Added. DELETE SELECTED KEY button present. No key_blob visible anywhere in the tab."
    why_human: "Requires visual confirmation and a device with a stored key in the DB"
  - test: "Select a key row in SSH Keys tab and click DELETE SELECTED KEY"
    expected: "Confirmation dialog appears. After Yes, row disappears from table and is gone from host_keys DB."
    why_human: "Requires GUI interaction with a populated SSH Keys tab"
  - test: "Verify fingerprint format in first-connect dialog matches ssh-keygen -l output"
    expected: "Fingerprint starts with 'SHA256:' followed by base64 characters — matches openssh-keygen -l -f output for the same server key"
    why_human: "Requires comparing dialog output against a known SSH server key fingerprint"
---

# Phase 04: SSH Host Key Verification — Verification Report

**Phase Goal:** SSH Host Key Verification — implement SSH-01 through SSH-04 so the app shows fingerprint dialogs on first connect, stores accepted keys, warns on changed keys, and lets users view/delete stored keys.
**Verified:** 2026-05-30T04:06:28Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SSH-01: Connecting to an unknown host triggers a dialog showing the key fingerprint | VERIFIED | `FirstConnectDialog` in `host_key_dialog.py` is shown by `HostKeyVerifier._show_host_key_dialog` when `situation=="new"`. `RemoteInHostKeyPolicy.missing_host_key` calls `verifier_fn`, which calls `verify_host_key`, which emits `host_key_check_requested`. Full chain traced. |
| 2 | SSH-02: Accepted keys are stored in the `host_keys` SQLite table | VERIFIED | `db.store_host_key` (INSERT OR REPLACE) called from `verify_host_key` when result is `"always_trust"`. `host_keys` table with `UNIQUE(device_id, hostname, port, key_type)` constraint exists in `db.init_db()`. |
| 3 | SSH-02: Silent reconnect when stored key matches live key (no dialog) | VERIFIED | `verify_host_key` calls `db.get_host_key` first; if `stored["key_blob"] == key_blob` returns `"accept_once"` immediately without emitting signal. Confirmed by Test 6. |
| 4 | SSH-03: Changed key triggers a warning dialog with both fingerprints and MITM warning | VERIFIED | `ChangedKeyDialog` shown when `situation=="changed"`. Body text contains "Stored key", "New key", "MITM attack" warning. Old fingerprint sourced from `self._pending["stored_fingerprint"]`. |
| 5 | SSH-03: "Connect Anyway" connects without updating DB; mismatch reappears next connect | VERIFIED | `_on_connect_anyway` returns `"accept_once"`, which `verify_host_key` does not write to DB. Only `"always_trust"` and `"update_key"` trigger DB writes. |
| 6 | SSH-04: SSH Keys tab visible in DeviceManagerDialog with Key Type, Fingerprint, Added columns | VERIFIED | `QTabWidget` with "Details" and "SSH Keys" tabs in `device_manager.py`. `make_table(["Key Type", "Fingerprint", "Added"])` used. `key_blob` not displayed. |
| 7 | SSH-04: Delete button removes key from table and DB with confirmation | VERIFIED | `_delete_host_key` shows `QMessageBox.question`, then calls `db.delete_host_key(key_id=key_id)`, then calls `_load_ssh_keys` to refresh. Confirmed by Test 3. |
| 8 | Cross-thread safety: worker blocks on `threading.Event`; dialog runs on main thread; timeout defaults to reject | VERIFIED | `threading.Event` + `event.wait(timeout=30)` in `verify_host_key`. Signal delivered via QueuedConnection (default). Timeout path (`fired=False`) sets `result="reject"`. Confirmed by Test 7. |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db.py` — `host_keys` table | DDL with UNIQUE constraint, CURRENT_TIMESTAMP default | VERIFIED | Lines 40-50: exact DDL matches plan spec including `UNIQUE(device_id, hostname, port, key_type)` |
| `db.py` — `delete_device()` cascade | Deletes host_keys before device, atomically | VERIFIED | Lines 337-345: `DELETE FROM host_keys WHERE device_id = ?` before device delete, same `with get_conn()` block |
| `db.py` — 5 CRUD functions | `store_host_key`, `get_host_key`, `update_host_key`, `delete_host_key`, `get_device_host_keys` | VERIFIED | All 5 present at lines 351-471, all keyword-only (inspect confirmed: 5 PASS) |
| `connector.py` — `RemoteInHostKeyPolicy` | Subclasses `MissingHostKeyPolicy`, uses `key.fingerprint` (SHA256), raises on reject | VERIFIED | Lines 18-65: correct implementation, `key.fingerprint` property used, raises `paramiko.SSHException` on non-accept |
| `connector.py` — `_connect_with_policy()` | `auto_connect=False` + `conn.key_policy` + `conn._open()` | VERIFIED | Lines 174-200: all three injection steps present |
| `connector.py` — `system_host_keys: False` | Prevents OS known_hosts bypass | VERIFIED | Line 102: `"system_host_keys": False` with explanatory comment |
| `connector.py` — all `get_*` accept `verifier_fn=None` | 7 public functions updated | VERIFIED | `get_interfaces`, `get_routing_table`, `get_bgp_neighbors`, `get_ospf_neighbors`, `get_arp_table`, `get_mac_table`, `run_cli_command` all confirmed |
| `host_key_dialog.py` | `HostKeyVerifier`, `FirstConnectDialog`, `ChangedKeyDialog` | VERIFIED | All three classes present, 434 lines, full implementation |
| `panels/base.py` — `BasePanel` | `_verifier_fn=None` in `__init__`, `set_device` accepts `verifier_fn=None` | VERIFIED | Lines 64, 89-93: both present |
| All 5 panels — `_run_fetch` | Pass `self._verifier_fn` to connector calls | VERIFIED | Confirmed via grep: interfaces, routing, bgp_ospf (both), arp_mac (both), cli all pass `self._verifier_fn` |
| `main.py` — wiring | `HostKeyVerifier` created, signals connected, `verifier_fn` passed to panels | VERIFIED | Lines 116-118, 227-231: verifier created on main thread, both signals connected, `verifier_fn=self._verifier.verify_host_key` passed in `_on_device_selected` |
| `device_manager.py` — SSH Keys tab | `QTabWidget`, `make_table`, empty-state label, delete button | VERIFIED | Lines 166-197: full tab implementation matching plan spec |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `RemoteInHostKeyPolicy.missing_host_key` | `verify_host_key` | `self._verifier_fn(hostname=, port=, ...)` keyword kwargs | VERIFIED | Lines 54-60 in connector.py |
| `verify_host_key` (worker thread) | `_show_host_key_dialog` (main thread) | `host_key_check_requested` signal, QueuedConnection | VERIFIED | Signal emitted line 128; connection in main.py line 117 |
| `_show_host_key_dialog` | worker unblock | `self._pending["event"].set()` in `finally` block | VERIFIED | Lines 231-232 in host_key_dialog.py; `finally` guarantees execution |
| `verify_host_key` | `db.store_host_key` | `result == "always_trust"` branch | VERIFIED | Lines 154-167 |
| `verify_host_key` | `db.update_host_key` | `result == "update_key"` branch, remapped to `"always_trust"` | VERIFIED | Lines 169-183 |
| `MainWindow._on_device_selected` | `HostKeyVerifier.device_id` | `self._verifier.device_id = device["id"]` | VERIFIED | Line 227 in main.py — device_id set before panels updated |
| `_delete_host_key` | `db.delete_host_key` | `key_id=key_id_item.data(Qt.ItemDataRole.UserRole)` | VERIFIED | Lines 277-288 in device_manager.py |
| Panel `_run_fetch` | `connector.get_*` | `self._verifier_fn` as positional arg | VERIFIED | All 5 panels confirmed via grep |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `DeviceManagerDialog._load_ssh_keys` | `keys` list | `db.get_device_host_keys(device_id=device_id)` | Yes — SELECT from host_keys table with real FK | FLOWING |
| `host_key_dialog.HostKeyVerifier.verify_host_key` | `stored` | `db.get_host_key(device_id=, hostname=, port=, key_type=)` | Yes — SELECT with 4-column WHERE clause | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 40 tests pass | `python -m pytest tests/ -q` | `40 passed in 12.06s` | PASS |
| db CRUD keyword-only check | `python -c "import inspect, db; ..."` | 5 PASS lines | PASS |
| `verify_host_key` keyword-only check | `python -c "import inspect; from host_key_dialog import HostKeyVerifier; ..."` | `verify_host_key PASS` | PASS |
| `system_host_keys` is False | `grep "system_host_keys" connector.py` | Line 102: `"system_host_keys": False` | PASS |
| No verify=False in connector.py | `grep "verify=False" connector.py` | Zero matches | PASS |
| No AutoAddPolicy in connector.py | `grep "AutoAddPolicy\|auto_add_policy" connector.py` | Zero matches | PASS |
| No allow_agent in connector.py | `grep "allow_agent" connector.py` | Zero matches | PASS |
| No TBD/FIXME/XXX debt markers | `grep -n "TBD\|FIXME\|XXX" connector.py host_key_dialog.py db.py device_manager.py panels/base.py main.py` | Zero matches | PASS |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SSH-01 | 04-02, 04-03, 04-04 | First connect to unknown host shows fingerprint dialog | SATISFIED | `FirstConnectDialog` shown via `RemoteInHostKeyPolicy` → `verify_host_key` → signal → `_show_host_key_dialog`; Test 6 (signal not emitted for known key), Test 7 (timeout rejects) |
| SSH-02 | 04-01, 04-03 | Accepted host keys stored in SQLite `host_keys` table | SATISFIED | `host_keys` table in `db.init_db()`, `store_host_key` INSERT OR REPLACE, called on `"always_trust"`; Test 8 confirms |
| SSH-03 | 04-02, 04-03, 04-04 | Changed host key on reconnect triggers warning dialog | SATISFIED | `ChangedKeyDialog` shown when `situation=="changed"`; `update_host_key` called on "Update Key"; `accept_once` skips DB on "Connect Anyway" |
| SSH-04 | 04-01, 04-05 | User can view and delete stored host keys from device settings | SATISFIED | SSH Keys tab in `DeviceManagerDialog`, `_load_ssh_keys`, `_delete_host_key` with confirmation; Tests 1-6 in test_ssh_keys_tab.py all pass |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `connector.py` | 7 | `from db import decrypt_field` | INFO | Pre-existing import (present before Phase 4). Plan 04-02 security checklist states "connector.py imports no db module functions" — this import was required by Phase 3 for credential decryption and predates Phase 4. Phase 4 correctly avoids all new db imports in connector by using verifier_fn injection. Not a Phase 4 regression. |

### Human Verification Required

The automated test suite passes fully (40/40 tests across all test files covering db CRUD, RemoteInHostKeyPolicy, dialog behaviors, and SSH Keys tab). The following items require a running application with a real or mock SSH target — they cannot be verified programmatically without a live Paramiko handshake.

**1. SSH-01: First-Connect Dialog Presentation**

**Test:** Add a device pointing to an SSH host not previously connected to (or clear `host_keys` table). Select the device, click FETCH on any panel.
**Expected:** Dialog titled "Unknown Host Key" appears showing hostname:port, key type, and a `SHA256:...` fingerprint. Three buttons: Reject, Accept Once, Always Trust.
**Why human:** Requires live Paramiko SSH handshake to trigger `missing_host_key`; dialog rendering requires visual confirmation.

**2. SSH-02: Key Stored After Accept**

**Test:** From the first-connect dialog, click "Always Trust". Inspect the `host_keys` table.
**Expected:** Connection proceeds; one row in `host_keys` with correct device_id, hostname, key_type, non-empty fingerprint.
**Why human:** Requires live connection; DB inspection must be manual.

**3. SSH-02: Reject Leaves No Trace**

**Test:** From the first-connect dialog, click "Reject". Inspect the `host_keys` table.
**Expected:** Connection aborted; status bar shows "ERROR: Host key rejected by user"; zero rows in `host_keys`.
**Why human:** Requires live connection.

**4. SSH-02: Silent Reconnect**

**Test:** With a key stored from step 2, select the same device and click FETCH again.
**Expected:** No dialog appears; connection completes; panel data loads normally.
**Why human:** Requires live connection; silent behavior cannot be asserted without running the event loop against a real host.

**5. SSH-03: Changed-Key Dialog**

**Test:** Run `UPDATE host_keys SET key_blob = 'ZmFrZWtleWJsb2I=', fingerprint = 'SHA256:FAKECHANGEDKEY' WHERE id = 1;` against the DB. Select the same device, click FETCH.
**Expected:** Dialog titled "Host Key Changed" appears, showing the fake stored fingerprint AND the real server fingerprint, containing "MITM attack" warning text, with three buttons: Cancel / Connect Anyway / Update Key.
**Why human:** Requires live connection and DB manipulation.

**6. SSH-04: SSH Keys Tab Visual Confirmation**

**Test:** Open File → Device Manager, click a device with at least one stored key, click the "SSH Keys" tab.
**Expected:** Table shows Key Type, Fingerprint, Added columns. Key blob is not visible anywhere. "DELETE SELECTED KEY" button is present below the table.
**Why human:** Visual confirmation of tab layout, column content, and absence of sensitive data requires running the app.

**7. SSH-04: Delete Key Flow**

**Test:** In the SSH Keys tab, select a row and click "DELETE SELECTED KEY".
**Expected:** Confirmation dialog appears; after clicking Yes, the row disappears from the table and the DB row is gone.
**Why human:** Requires modal dialog interaction.

**8. Fingerprint Format Matches ssh-keygen**

**Test:** Note the `SHA256:...` fingerprint shown in the first-connect dialog. Run `ssh-keygen -l` against the same server key.
**Expected:** The dialog fingerprint matches `ssh-keygen -l` output exactly (same SHA256:Base64 string).
**Why human:** Requires comparing live dialog output against an external CLI tool.

---

## Gaps Summary

No automated gaps found. All 8 observable truths verified. All artifacts are substantive and wired. The full 40-test suite passes. The only open items are live-app behavioral checks that require a running SSH target — these are the standard human verification items expected for any SSH security feature.

The `from db import decrypt_field` in `connector.py` is a pre-Phase-4 import required for credential decryption. Phase 4 correctly avoided adding any new db imports by injecting `verifier_fn`. This is not a Phase 4 gap.

---

_Verified: 2026-05-30T04:06:28Z_
_Verifier: Claude (gsd-verifier)_
