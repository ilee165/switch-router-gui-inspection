---
phase: 4
reviewers: [gemini, codex]
reviewed_at: 2026-05-30T08:20:00Z
plans_reviewed:
  - 04-01-PLAN.md
  - 04-02-PLAN.md
  - 04-03-PLAN.md
  - 04-04-PLAN.md
  - 04-05-PLAN.md
  - 04-06-PLAN.md
self_cli_skipped: claude
---

# Cross-AI Plan Review — Phase 4: SSH Host Key Verification

## Gemini Review

### Summary

The proposed plans are exceptionally well-structured, demonstrating high engineering rigor and a deep understanding of the SSH TOFU (Trust On First Use) security model. The architectural separation is preserved via dependency injection (`verifier_fn`), and the transition from a worker thread to a modal GUI dialog is handled using the correct synchronization primitives (`threading.Event`). The inclusion of a mandatory security audit and keyword-only parameter enforcement across all layers is a standout feature that aligns perfectly with the project's "safe, offline tool" value proposition.

### Strengths

- **Engineering Rigor**: The mandatory security audit of `connector.py` (searching for `verify=False` or `AutoAddPolicy`) is an excellent proactive measure to ensure the implementation does not mask legacy issues.
- **Architectural Integrity**: `connector.py` remains "pure" (no PyQt6 or DB imports) by receiving a callable. This ensures the SSH logic is testable in isolation and maintains a clean boundary between the protocol and the application.
- **Robust Threading Pattern**: The use of `threading.Event` for blocking the worker thread while a `QueuedConnection` signal triggers the GUI is the idiomatic way to handle this in PyQt6, avoiding the common pitfalls of complex shared state.
- **Security-First UX**: Treating the dialog "X" button as a `Reject` (Safe Default) and providing side-by-side fingerprints in the "Changed Key" dialog are superior design choices that follow security best practices.
- **Defensive Programming**: Making security-critical parameters keyword-only (`*`) at the function signature level is a strong "defense in depth" strategy to prevent positional argument errors.

### Concerns

- **HIGH: Race Condition in `HostKeyVerifier`** — `self._pending` is an instance variable. If a user triggers Fetch on two panels nearly simultaneously, their calls to `verify_host_key` will collide. The second call overwrites `self._pending`, potentially causing one thread to receive the result of the other's dialog or causing the app to hang.
- **MEDIUM: DB CASCADE dependency** — The plan correctly identifies that `PRAGMA foreign_keys` is not enabled and fixes `delete_device` manually. However, future developers adding new tables might forget the manual cascade. Enabling `PRAGMA foreign_keys = ON` in `get_conn()` globally would be safer.
- **LOW: Paramiko Version Assumption** — The plan relies on `key.fingerprint` returning `SHA256:Base64` directly. This property was introduced in Paramiko 3.x. A version check or fallback would guarantee compatibility.

### Suggestions

- **Fix Concurrency**: Modify `HostKeyVerifier.verify_host_key` to avoid instance-level storage. Instead of `self._pending`, use a `dict` keyed by `threading.get_ident()` to isolate state per-thread.
- **Global DB Pragma**: Add `conn.execute("PRAGMA foreign_keys = ON")` to the `get_conn()` helper in `db.py`.
- **Dialog Parenting**: Ensure dialogs receive the `MainWindow` as a parent for correct modal centering.
- **Status Bar Persistence**: The D-07 "Connected (host key mismatch not resolved)" message may be immediately overwritten by the panel's own success message — consider ordering or color differentiation.

### Risk Assessment

**Level: MEDIUM**

The plans are 95% correct from a security and logic perspective. The **concurrency race condition** in `HostKeyVerifier` is the primary technical risk. Once state-passing is made thread-safe, the risk level drops to **LOW**.

---

## Codex Review

### Summary

Overall, the phase design is directionally strong: it separates DB persistence, SSH policy injection, GUI prompting, panel wiring, and final verification into sensible waves. The plans cover the four SSH requirements and include useful adversarial tests. The largest risks are not missing features, but contract mismatches between plans, unsafe fallback paths, and cross-thread state handling. As written, the plans are close, but I would not approve implementation without tightening the verifier/device identity contract, the `verifier_fn=None` fallback, SQLite referential integrity assumptions, and concurrency behavior.

### Strengths

- Clear phase boundaries: Phase 4 stays focused on host key verification and does not reopen credential encryption.
- Good architecture intent: `connector.py` receives an injected verifier callback instead of importing GUI code.
- Correct host key comparison strategy: storing and comparing the full public key blob is better than comparing only displayed fingerprints.
- Good security UX coverage: first-connect, reject, silent reconnect, changed-key warning, connect-anyway, and update-key paths are all specified.
- `system_host_keys=False` is correctly called out as mandatory; otherwise OS `known_hosts` could bypass RemoteIn's trust database.
- Dialog close behavior defaults to reject — the right safe default.
- Changed-key dialog requirements are strong: both old and new fingerprints, MITM warning, and explicit update-vs-connect-anyway choices.

### Concerns

- **HIGH: `device_id` contract is inconsistent across 04-02, 04-03, and 04-04** — `HostKeyVerifier.verify_host_key` requires `device_id`, but `RemoteInHostKeyPolicy.missing_host_key` only passes `hostname`, `port`, `key_type`, `fingerprint`, and `key_blob`. 04-04 passes `self._verifier.verify_host_key` directly with no wrapper adding `device_id`. This is a blocking integration gap — the verifier cannot look up or store the key without knowing which device it belongs to.

- **HIGH: `verifier_fn=None` fallback silently bypasses the new security model** — 04-02 and 04-04 describe this as "safe degradation," but for a security phase it is not safe. If wiring is missed anywhere, SSH connects without RemoteIn host key verification. After Phase 4, production Netmiko calls should fail closed if no verifier is supplied.

- **HIGH: SQLite foreign key assumptions are wrong unless `PRAGMA foreign_keys=ON` is enabled** — 04-01 says `store_host_key` may raise `sqlite3.IntegrityError` for a nonexistent `device_id`, but the plan also states foreign keys are not enabled. In that state, SQLite will allow orphaned `host_keys` rows.

- **HIGH: Single `_pending` field is not safe for concurrent fetches** — The plan assumes one pending check at a time, but the app has multiple panels. A second host-key prompt can overwrite `_pending`, causing wrong decisions, stuck workers, or DB writes for the wrong connection.

- **HIGH: Timeout handling can race with the dialog** — If the worker times out after 30 seconds and clears `_pending` while the modal dialog is still open, a later user click may write into `None` or stale state. The slot should capture a per-request object/token instead of reading mutable shared `_pending`.

- **HIGH: Plan 04-02's "connector imports no db" checklist may conflict with credential decryption** — If `connector.py` already imports `decrypt_field` from `db.py` for Phase 3 credential decryption, the checklist goal is either impossible or requires a `crypto.py` extraction. The plan should resolve this explicitly.

- **MEDIUM: D-07 status message may fire before connection succeeds** — 04-04 emits the note from `verify_host_key` after "Connect Anyway." At that moment, authentication or command execution can still fail. The message could incorrectly say "Connected."

- **MEDIUM: `INSERT OR REPLACE` changes primary key and `added_at`** — SQLite REPLACE deletes and reinserts, changing the row's PK. `ON CONFLICT ... DO UPDATE SET` is cleaner and preserves row identity.

- **MEDIUM: `Accept Once` semantics are intentionally misleading** — D-01 says Accept Once and Always Trust both store the key. Most users expect "Accept Once" to be session-only. UI text should clarify that both choices persist.

- **MEDIUM: Genie bypass remains a security gap** — Genie path does not get host key verification. The code should gate this explicitly by platform or disable Genie when verification is required.

- **MEDIUM: Paramiko fingerprint property version should be pinned** — Requirements should pin compatible Paramiko/Netmiko versions or add a compatibility helper.

- **LOW: Standalone assert scripts may conflict with pytest if it exists** — If `tests/conftest.py` or pytest tests already exist, adding standalone scripts fragments testing.

- **LOW: `closeEvent(None)` in dialog tests is fragile** — `closeEvent` expects a close event object. Prefer `dialog.close()` or constructing a real `QCloseEvent`.

- **LOW: DB error handling is uneven** — Explicit `QMessageBox.warning` around key operations would be more user-friendly.

### Suggestions

- **Fix the verifier contract before implementation** — Create a per-device wrapper in `BasePanel.set_device` or `main.py`:

  ```python
  verifier_fn = lambda **kwargs: self._verifier.verify_host_key(device_id=device["id"], **kwargs)
  ```

  This keeps `verify_host_key` keyword-only and injects `device_id` at the call site without modifying the Paramiko hook signature.

- **Make missing verifier fail closed** — A missing verifier should raise `RuntimeError`, not silently connect without verification. Use an explicit test fixture for tests that bypass it.

- **Enable SQLite foreign keys in `get_conn()`**:

  ```python
  conn.execute("PRAGMA foreign_keys = ON")
  ```

- **Replace `_pending` with request-scoped state** — Use a per-thread dict keyed by `threading.get_ident()`, or a `PendingHostKeyCheck` dataclass passed through the signal.

- **Add a `threading.Lock`** to protect verifier state if multiple workers can call it.

- **Move D-07 status message** to after `conn._open()` succeeds in `_connect_with_policy`, not when the user dismisses the dialog.

- **Prefer SQLite upsert** over `INSERT OR REPLACE`:

  ```sql
  INSERT INTO host_keys (...) VALUES (...)
  ON CONFLICT(device_id, hostname, port, key_type)
  DO UPDATE SET fingerprint = excluded.fingerprint,
                key_blob = excluded.key_blob,
                added_at = CURRENT_TIMESTAMP
  ```

- **Add explicit tests** for: missing verifier fails closed; nonexistent `device_id` cannot create orphan keys; two simultaneous prompts do not cross-write; timeout + late dialog click does not crash; "Connect Anyway" does not update DB and does not emit "Connected" if connection later fails.

### Risk Assessment

**Overall risk: MEDIUM-HIGH**

Feature design is mostly complete and security-aware, but several integration contracts are currently inconsistent. The biggest risks are silent bypass if `verifier_fn` is missing, missing `device_id` propagation through the Paramiko hook, SQLite orphan rows due to disabled foreign keys, and race conditions in the cross-thread verifier. These can be fixed without redesign, but must be resolved before implementation begins.

---

## Consensus Summary

Both reviewers independently identified the same critical risks. This cross-AI agreement gives high confidence these are real issues.

### Agreed Strengths

- **Correct cross-thread mechanism**: `threading.Event` + `QueuedConnection` signal is the right PyQt6 pattern for blocking a worker while showing a GUI dialog
- **Architectural integrity**: `connector.py` receiving a `verifier_fn` callable (not importing PyQt6 or db) is correct layering
- **Security-first defaults**: X button = Reject, SHA256 fingerprints, full key blob storage for cryptographic comparison
- **Keyword-only argument enforcement**: Applying the Phase 3 lesson consistently across all new security-sensitive functions
- **Changed-key dialog design**: Both fingerprints displayed, MITM warning text, three explicit choices

### Agreed Concerns

| Concern | Severity | Both Reviewers |
|---------|----------|----------------|
| `_pending` race condition — concurrent panel fetches can collide | **HIGH** | yes |
| SQLite foreign keys disabled — orphaned rows and inaccurate error contracts | **HIGH/MEDIUM** | yes |
| Paramiko `key.fingerprint` property version dependency | **LOW/MEDIUM** | yes |

### Codex-Only HIGH Concerns

| Concern | Severity |
|---------|----------|
| `device_id` not propagated from `RemoteInHostKeyPolicy` hook to `verify_host_key` — blocking integration gap | **HIGH** |
| `verifier_fn=None` fails open — silently bypasses security model | **HIGH** |
| Timeout race: worker clears `_pending` while dialog is still open | **HIGH** |
| `connector.py` "no db import" rule may conflict with Phase 3 credential decryption | **HIGH** |
| D-07 status message fires before connection actually succeeds | **MEDIUM** |

### Priority Fixes Before Merging

1. **Fix `device_id` propagation** — Wrap `verify_host_key` at the call site to close-bind `device_id` from the current device:
   ```python
   verifier_fn = lambda **kwargs: self._verifier.verify_host_key(device_id=device["id"], **kwargs)
   ```

2. **Fix `_pending` race condition** — Replace the single instance variable with a per-thread dict keyed by `threading.get_ident()`.

3. **Enable `PRAGMA foreign_keys = ON`** in `get_conn()` — gives referential integrity globally and makes the `store_host_key` error contract accurate.

4. **Make `verifier_fn=None` fail closed** — A missing verifier should raise `RuntimeError`, not silently connect without verification.

5. **Resolve `connector.py` import rule** — Verify whether `connector.py` imports anything from `db.py` for Phase 3 credential decryption. If so, update the audit checklist or extract a `crypto.py` module.

---

*To incorporate this feedback into planning: `/gsd-plan-phase 4 --reviews`*
