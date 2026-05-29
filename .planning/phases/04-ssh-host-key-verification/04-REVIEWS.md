---
phase: 4
source: Phase 3 retrospective (03-REVIEWS.md) + Phase 4 pre-plan design review
reviewers: [gemini, claude]
reviewed_at: 2026-05-29T15:44:00-04:00
review_type: forward_guidance + pre_plan_design_review
note: >
  Part 1: Phase 4-specific planning action items from the Phase 3 cross-AI
  retrospective. Part 2: Gemini pre-plan design review of CONTEXT.md +
  decisions before any PLAN.md files existed. Both parts bind every Phase 4 plan.
---

# Cross-AI Review Guidance — Phase 4: SSH Host Key Verification

> **Source:** Phase 3 Credential Encryption retrospective (Gemini + Claude).
> Phase 3 execution produced 9 post-execution findings (3 critical, 4 warnings).
> The retrospective identified root causes in plan specification quality and
> produced these binding action items for Phase 4.

---

## Action Items for Phase 4 Planning

Apply these constraints to **every Phase 4 plan**:

### 1. Required keyword-only arguments for security params

No optional defaults on security-critical parameters. When a parameter is
required for correct security behavior, make it keyword-only with no default.

> **Rationale:** Phase 3 CR-03 (double-encryption bug) traced directly to
> `session_key=None` default. The plan identified the anti-pattern and then
> specified the exact implementation that enabled it.

**Rule:** If a caller cannot provide the value, that call site is wrong —
raise at the wrong call site, not deeper in the stack.

### 2. Error contract for every function that can partially fail

Every function spec must include: "on failure, do X (show QMessageBox /
skip-and-log / raise)." **"Non-fatal" is not a specification.**

> **Rationale:** Phase 3 CR-02 (silent exception swallow in migration) traced
> to "non-fatal — unencrypted rows remain readable" with no specified UI
> response. In code, "non-fatal" became "silent failure."

**Rule:** Any plan step that says "catch exception and continue" must specify
the minimum user-visible feedback (e.g., `QMessageBox.warning(self, 'title', str(e))`).

### 3. In-file security audit when touching connector.py

Any Phase 4 plan modifying `connector.py` must include a sub-task:

> *"Before committing, grep connector.py for `strict_host_key_checking`,
> `verify=False`, `disabled_algorithms`, `allow_agent=True` and verify none
> are set to insecure values."*

> **Rationale:** Phase 3 CR-01 (`strict_host_key_checking=False`) and WR-02
> (legacy algorithm downgrade) were pre-existing in connector.py. Phase 3
> plans touched the file for security reasons but never audited the file's
> existing SSH configuration.

### 4. Verification checkpoints must include security verification

Phase 4's verification checkpoint must verify that host key checking
**actually rejects** unknown hosts — not just that the dialog appears.

> **Rationale:** Phase 3's 03-06-PLAN.md was functional verification only.
> Four of the seven post-execution findings were not in scope because the
> plans never specified those behaviors. A security milestone's verification
> checkpoint must audit security posture of every modified file.

**Required in Phase 4 verification checkpoint:**
- Attempt connection to mock/test host with unknown key → dialog must appear
- Attempt connection to mock/test host with *changed* key → warning must appear
- Attempt connection without user acceptance → connection must abort
- grep connector.py for insecure SSH config patterns after modification

### 5. Adversarial test category

Phase 4 test plans must include at least one test per new security-critical
function that tests the **failure path**, not just the success path.

> **Rationale:** Phase 3 test plan verified what the plan said would work,
> not what could go wrong. All 7 tests could pass while `_is_fernet_token`
> had a detection bug and migration silently swallowed errors.

**Required adversarial tests for Phase 4:**
- Changed host key → connection must be blocked (not silently accepted)
- Rejected host → key must not appear in `host_keys` table
- `host_keys` table contains tampered key fingerprint → behavior must be defined
- Dialog cancelled → connection must abort cleanly

### 6. Anti-pattern notes must close the anti-pattern in the spec

If a plan describes a failure mode, the specification must make it
**impossible** via required args / fail-loud behavior. If the plan says
"never do X," the spec must make X a compile-time or import-time error.

> **Rationale:** Phase 3 CR-03 was the most preventable finding — the plan
> identified the anti-pattern verbatim, then specified the exact implementation
> that enabled it. The warning and the implementation contradicted each other.

**Rule:** Anti-pattern notes in plans are bugs unless accompanied by a
specification that makes the anti-pattern unreachable.

---

## Key Lessons from Phase 3 (Gemini + Claude Consensus)

| Lesson | Mechanism | Phase 4 Application |
|--------|-----------|---------------------|
| Permissive API defaults enable silent failures | `session_key=None` → CR-03 | All host key params: keyword-only, no default |
| Transport security is a separate audit from feature correctness | CR-01, WR-02 missed | Explicit connector.py security audit sub-task |
| "Non-fatal" without UI spec → silent failure | CR-02 | Every failure path specifies user-visible response |
| Test plan for happy path only → false confidence | CR-02, WR-04 undetected | Mandatory adversarial test category |
| Verification checkpoint for features, not security posture | All 7 findings missed | Security verification steps required in 04-06 |
| Anti-pattern warnings must be spec'd closed | CR-03 self-described | Anti-pattern → required arg or compile-time error |

---

## SSH-Specific Planning Risks (Phase 4 Focus)

These risks are new to Phase 4 and not covered by Phase 3 patterns:

- **TOCTOU on host key verification:** The key must be checked immediately
  before the connection is established, not cached from a previous check.
- **Netmiko's `AutoAddPolicy` / `RejectPolicy`:** The plan must explicitly
  specify which Paramiko policy class is used and why `AutoAddPolicy` is
  prohibited.
- **`host_keys` table integrity:** The table stores trust decisions. A plan
  that reads this table must specify behavior when the row is corrupt/missing.
- **Key fingerprint display format:** SHA256 hex vs Base64 — be explicit.
  Netmiko/Paramiko use `get_host_key_fingerprint()` returns; the plan must
  specify the exact format shown in the dialog.
- **Dialog lifecycle:** If the user closes the fingerprint dialog with the
  window X button (not Accept/Reject), the plan must specify what happens.

---

## Part 2: Gemini Pre-Plan Design Review

> **Reviewer:** Gemini CLI  
> **Review type:** Pre-plan design review (CONTEXT.md + decisions; no PLAN.md files existed)  
> **Reviewed at:** 2026-05-29T15:44:00-04:00

### Summary

The design for Phase 4 is architecturally sound and prioritizes security over
convenience by enforcing modal, blocking dialogs for unknown or changed host keys.
The decision to treat "Accept" and "Always Trust" identically simplifies the
implementation for a single-user local tool without compromising the security model.
The primary technical challenge lies in the orchestration between the background SSH
thread (`FetchWorker`), the `connector.py` abstraction, and the main GUI thread,
while respecting the strict separation of concerns between the database and the
connection logic.

### Strengths

- Security posture is correct: modal blocking dialogs, explicit user decision
  required, no silent acceptance of unknown or changed keys
- D-04 (X button = Reject) is an excellent safe-default decision
- D-01 (Accept = Always Trust) is the right simplification for a single-user local tool
- SHA256:Base64 fingerprint format matches what network engineers already know from OpenSSH/PuTTY
- Re-using `make_table()` for SSH-04 correctly avoids reinventing styled table widgets

### Concerns

- **Thread Deadlock Risk (HIGH):** The Paramiko `MissingHostKeyPolicy` will be
  triggered inside the `FetchWorker` thread. Since this thread needs to wait for a
  user response from the main GUI thread, a simple signal/slot mechanism won't
  suffice because the SSH connection is synchronous and blocking. If not handled
  with precision, this will freeze the worker or the entire UI.

- **Architectural Coupling (MEDIUM):** The "no DB in connector" and "no GUI in
  connector" rules create a "three-body problem." `connector.py` needs host keys
  to verify them, but it can't fetch them directly. A clean dependency injection
  pattern (e.g., passing a verifier interface/callable) is required to avoid
  breaking these architectural boundaries.

- **Netmiko Abstraction Limits (MEDIUM):** Netmiko wraps Paramiko's connection
  logic. Injecting a custom `MissingHostKeyPolicy` usually requires reaching into
  Netmiko's internal `paramiko_kwargs`. The plan must verify this injection
  works *before* the socket is opened — not all Netmiko versions expose this
  cleanly.

- **Duplicate Key Records (LOW):** Devices reachable via multiple IPs/hostnames
  will result in multiple prompts and DB entries. While cryptographically correct,
  this may be confusing in a device-centric UI if the user expects one key per
  Device object.

### Suggestions

- **Synchronization Strategy:** Use `QtCore.QMetaObject.invokeMethod` with
  `Qt.ConnectionType.BlockingQueuedConnection` to call the dialog from the
  background thread. This allows the background thread to safely block waiting
  for the user's Accept/Reject response before continuing the SSH handshake.

- **Host Key Verifier Interface:** Define a `HostKeyVerifier` callable or
  interface. The `FetchWorker` provides the implementation (handles `db.py` lookup
  + UI signaling). `connector.py` receives it as an argument and calls it — never
  imports `db.py` or PyQt6 directly. This resolves the three-body problem cleanly.

- **Schema Unique Constraint:** Add a `UNIQUE(device_id, hostname, port, key_type)`
  constraint to the `host_keys` table. This makes the "Update Key"
  (DELETE + INSERT) logic atomic and prevents logical duplicates.

- **Store Raw Key Blob:** Store the actual public key `key_blob` in the database
  (already in the proposed schema). Ensure Paramiko verification uses the raw
  blob for cryptographic comparison, not just the fingerprint string.

- **Status Bar Specificity:** When connection is rejected via dialog, bubble up
  the specific reason ("User rejected host key" vs "Host key mismatch") so the
  status bar notice at D-07 is accurate and actionable.

### Risk Assessment

**Risk Level: MEDIUM**

The security logic is robust, but the **cross-thread blocking dialog** pattern is
a classic source of UI freezes or deadlocks in PyQt6. The success of this phase
depends on a disciplined synchronization pattern between `FetchWorker` and the GUI
thread. Additionally, the strict separation of `connector.py` from `db.py` requires
a clean dependency injection strategy to maintain architectural integrity.

---

## Consensus Summary (Phase 3 Retrospective + Gemini Design Review)

### Agreed Strengths
- Security-first defaults throughout: reject on ambiguity, no silent acceptance
- Reuse of established patterns (`make_table`, `QTabWidget`, keyword-only args)
- Dialog UX matches network engineer expectations (OpenSSH/PuTTY fingerprint format)

### Agreed Top Concerns

1. **Cross-thread dialog synchronization (HIGH)** — Both reviews flag this as the
   highest-risk implementation problem. The plan must specify the exact Qt
   mechanism (`BlockingQueuedConnection` or `threading.Event`) before any code
   is written.

2. **Dependency injection for connector.py (MEDIUM)** — `connector.py` cannot
   import `db.py` or PyQt6. The plan must name the injection boundary explicitly
   (a callable/verifier passed as a parameter).

3. **Netmiko `paramiko_kwargs` injection (MEDIUM)** — Verify the exact Netmiko
   API for injecting a custom `MissingHostKeyPolicy` before finalizing the plan.
   Document the Netmiko version constraint.

4. **Every failure path needs a specified UI response (Phase 3 lesson)** —
   "Non-fatal" is not a specification. Each catch block must name what the user
   sees.

### Binding Items for Every Phase 4 Plan
1. Keyword-only args for all security params — no defaults on `key_blob`, `fingerprint`, etc.
2. Cross-thread dialog mechanism named explicitly in the plan (not deferred to implementer)
3. `host_keys` UNIQUE constraint on `(device_id, hostname, port, key_type)`
4. Adversarial tests: reject path, tampered row, dialog cancelled
5. connector.py security audit sub-task in any plan that touches `connector.py`
6. Verification checkpoint includes security posture check (key not stored after Reject)
