# Phase 4: SSH Host Key Verification - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add SSH host key verification to every device connection. First connect to an
unknown device shows a fingerprint dialog (Accept / Always Trust / Reject).
Accepted keys are stored in a new `host_keys` SQLite table. Reconnect silently
if the key matches; warn and offer options if the key has changed. Device settings
gains a new "SSH" tab for viewing and deleting stored host keys.

Files in scope: `db.py`, `connector.py`, `device_manager.py` (or new
`host_key_dialog.py`), `main.py` (status bar wiring only if needed)

Out of scope: "Test Connection" / re-verify button in SSH tab, global known-hosts
manager, certificate-based SSH auth, per-session-only (non-stored) accept.

</domain>

<decisions>
## Implementation Decisions

### First-Connect Fingerprint Dialog (SSH-01)

- **D-01:** "Accept" and "Always Trust" are **both permanent storage actions** —
  both write the key to `host_keys`. The distinction is label clarity, not
  behavior. There is no session-only accept option. Simpler for a single-user
  local tool; the key dialog already implies explicit intent.
- **D-02:** Fingerprint is displayed in **SHA256:Base64 format** (OpenSSH standard,
  e.g., `SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s`). This is what
  PuTTY, OpenSSH, and Netmiko use — network engineers will recognize it.
- **D-03:** Dialog shows three pieces of information:
  1. Hostname (or IP) being connected to
  2. Key type (e.g., `ecdsa-sha2-nistp256`, `ssh-rsa`, `ssh-ed25519`)
  3. SHA256:Base64 fingerprint
- **D-04:** If the user closes the dialog with the window X button (not Accept /
  Always Trust / Reject), treat it as **Reject** — abort the connection, store
  nothing. Closing without an explicit choice defaults to safe.

### Changed Host Key Dialog (SSH-03)

- **D-05:** Changed key warning dialog has **three buttons**:
  - **"Connect Anyway"** — connect this session; stored key is NOT updated.
    The mismatch warning will reappear on next connect.
  - **"Update Key"** — replace the stored key with the new one AND connect.
    Resolves the mismatch permanently.
  - **"Cancel"** — abort connection entirely.
- **D-06:** Dialog **title: "Host Key Changed"** (warning tone, not neutral).
  Dialog body shows **both fingerprints** so the user can compare:
  - Stored key: `{key_type} SHA256:{old_fingerprint}`
  - New key: `{key_type} SHA256:{new_fingerprint}`
  With a warning line: "This may indicate a MITM attack or a legitimate key
  change (device reimaged/rotated)."
- **D-07:** When user clicks "Connect Anyway" (without updating), after
  connection succeeds, the **status bar** shows: `"Connected (host key mismatch
  not resolved)"` — a subtle, non-blocking reminder that the stored key is stale.

### SSH-04 Host Key Management UI

- **D-08:** SSH-04 is implemented as a **new "SSH" tab** inside the existing
  `DeviceManagerDialog` (same dialog that edits device credentials). Consistent
  placement — device settings is where users expect it.
- **D-09:** The SSH tab contains a table with three columns: **Key Type |
  Fingerprint | Added**. Uses `make_table()` from `panels/base.py` for
  consistency with all other tables in the app. A "Delete" button below the
  table removes the selected key row.
- **D-10:** No "Re-verify" / "Test Connection" button in the SSH tab. Deletion
  is the only action. Re-verification happens automatically on the next connect
  attempt — no extra scope needed.

### Claude's Discretion

- **host_keys table schema:** The planner/researcher decides the exact schema.
  Suggested: `(id, device_id INTEGER REFERENCES devices(id), hostname TEXT,
  port INTEGER, key_type TEXT, fingerprint TEXT, key_blob TEXT, added_at TEXT)`.
  Use both `device_id` (for SSH-04 UI — filter by device) and
  `hostname + port + key_type` (for Paramiko verification lookup). Schema
  migration follows the `CREATE TABLE IF NOT EXISTS` + `try/except OperationalError`
  pattern from `db.py:42`.
- **Paramiko integration:** The researcher/planner determines the exact hook.
  Netmiko wraps Paramiko; the standard approach is a custom `MissingHostKeyPolicy`
  subclass injected via `ConnectHandler` kwargs. Cross-thread dialog from
  `FetchWorker` to main GUI thread requires Qt signals or `threading.Event` —
  planner decides the exact mechanism.
- **Raw key storage:** Key bytes for exact comparison stored as base64 in
  `key_blob`. Fingerprint (SHA256:Base64) stored separately for display in SSH-04
  tab without re-computing. Planner decides whether to compute fingerprints in
  `db.py` or in connector code.
- **"Update Key" implementation:** DELETE old row matching `(device_id, key_type)`
  or `(hostname, port, key_type)`, then INSERT new key. Exact DELETE predicate
  deferred to planner.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Planning artifacts
- `.planning/ROADMAP.md` — Phase 4 goal, success criteria, files in scope
- `.planning/REQUIREMENTS.md` — SSH-01, SSH-02, SSH-03, SSH-04 requirement text
- `.planning/PROJECT.md` — Key Decisions table (SSH host key dialog decision confirmed)
- `.planning/phases/04-ssh-host-key-verification/04-REVIEWS.md` — Phase 3
  retrospective action items binding for Phase 4 plans (keyword-only args,
  error contracts, connector.py audit, adversarial tests, security verification)

### Source files being changed
- `connector.py` — `_netmiko_device()` at line 27: replace `"system_host_keys": True`
  with the custom Paramiko policy hook; also contains the SSH audit checklist
  from 04-REVIEWS.md D-03 requirement
- `db.py` — add `host_keys` table + CRUD functions; follow `executescript` +
  `try/except OperationalError` migration pattern at lines 19–47
- `device_manager.py` — add "SSH" tab to `DeviceManagerDialog`; uses
  `make_table()` for the host keys table

### Prior phase patterns
- `.planning/milestones/v1.0-phases/02-panels-cleanup/02-CONTEXT.md` —
  `make_table()` usage and `PALETTE` constant patterns
- `.planning/phases/03-credential-encryption/03-REVIEWS.md` — binding action
  items (same file as 04-REVIEWS.md source)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `make_table(headers: list[str]) -> QTableWidget` in `panels/base.py` — use
  for the SSH tab host keys table; columns: `["Key Type", "Fingerprint", "Added"]`
- `PALETTE["error"]` (`#EF4444`) — appropriate for warning/changed-key UI elements
- `PALETTE["caution"]` (`#F59E0B`) — for the amber warning tone in changed-key dialog
- `QMessageBox.warning(parent, title, str(e))` — established in Phase 3 for
  user-visible security warnings; changed-key dialog may use this or a custom dialog

### Established Patterns
- `*, session_key: bytes` keyword-only argument pattern (Phase 3, db.py:288) —
  all new db.py functions that take security params must use this pattern
- `CREATE TABLE IF NOT EXISTS` in `executescript` + `ALTER TABLE ... ADD COLUMN`
  with `try/except OperationalError` (db.py:19–47) — schema migration pattern;
  use for `host_keys` table creation
- `FetchWorker` + `QThread` in `panels/base.py` — SSH connections run on a
  background thread; any dialog triggered during connection must cross to the
  main GUI thread via Qt signals
- `_netmiko_device()` returns a `dict` of kwargs passed to `ConnectHandler` —
  adding a `sock` or custom policy parameter follows the same dict-extension
  pattern at connector.py:27

### Integration Points
- `connector.py:_netmiko_device()` line 45 — `"system_host_keys": True` is the
  exact placeholder to replace with the Phase 4 Paramiko policy hook. The comment
  on lines 41–47 explicitly marks this as the SSH-01 insertion point.
- `device_manager.py:DeviceManagerDialog` — existing tabs (form fields) use
  `QTabWidget`; adding a new "SSH" tab follows the same constructor pattern
- `main.py` status bar — `self._set_status(str)` is the method to call for the
  "key mismatch not resolved" status bar notice (D-07); panel `status_message`
  signals already wire into it

</code_context>

<specifics>
## Specific Ideas

- The first-connect dialog resembles PuTTY's host key prompt — that's the
  target UX reference. Network engineers who use PuTTY will find it immediately
  familiar.
- The changed-key dialog explicitly calls out the MITM attack risk in the body
  text (not just the title). This matches the threat model for a security-focused
  tool: users should understand WHY the warning exists.
- SHA256:Base64 is the format `ssh-keygen -l` displays. If a user runs
  `ssh-keygen -l -f /dev/stdin <<< "$(ssh-keyscan -t ecdsa 10.0.0.1)"`, the
  fingerprint they see should match what RemoteIn shows.

</specifics>

<deferred>
## Deferred Ideas

- **"Re-verify" / "Test Key" button** — suggested during SSH-04 UI discussion.
  Would connect to the device from device settings and compare the live key to
  the stored one. Out of scope for Phase 4; deferred to a future milestone.
  (Aligns with "Connection health check — Test Connection button" already in
  CLAUDE.md deferred list.)
- **Global Known Hosts manager** — a menu-level view of all stored host keys
  across all devices. Out of scope; SSH-04 is device-scoped by design.

</deferred>

---

*Phase: 04-ssh-host-key-verification*
*Context gathered: 2026-05-29*
