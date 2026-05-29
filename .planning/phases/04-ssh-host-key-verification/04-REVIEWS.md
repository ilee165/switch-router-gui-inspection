---
phase: 4
source: Phase 3 retrospective (03-REVIEWS.md)
reviewers: [gemini, claude]
reviewed_at: 2026-05-29T14:25:00-04:00
review_type: forward_guidance
note: >
  Phase 4 has no completed plans yet. This REVIEWS.md carries forward the
  Phase 4-specific planning action items produced by the Phase 3 cross-AI
  retrospective review. Apply all items below to every Phase 4 plan.
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
