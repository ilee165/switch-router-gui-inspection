---
phase: 3
reviewers: [gemini, claude]
reviewed_at: 2026-05-29T14:25:00-04:00
plans_reviewed:
  - 03-01-PLAN.md
  - 03-02-PLAN.md
  - 03-03-PLAN.md
  - 03-04-PLAN.md
  - 03-05-PLAN.md
  - 03-06-PLAN.md
skipped_reviewers:
  cursor: not installed
  codex: not installed
  openai: not a supported reviewer flag (no such CLI)
review_type: retrospective
phase_status: complete (2026-05-29, 27/27 must-haves verified)
post_execution_findings: 9 (3 critical, 4 warnings, 2 info — all critical/warning fixed)
---

# Cross-AI Plan Review — Phase 3: Credential Encryption (Retrospective)

> **Note:** Phase 3 is complete. This is a retrospective review of the plans
> themselves, conducted after execution, code review, and all critical/warning
> fixes. Findings are recorded as learning for Phase 4 planning quality.

---

## Gemini Review

### Summary

The Phase 3 plans represent a logically sound and well-structured approach to
implementing encryption-at-rest. The progression from cryptographic foundations
(Wave 1) to integration (Waves 2–3) and final verification (Wave 4) demonstrates
a clear understanding of dependency management. The plans successfully addressed
the core value of "offline safety" by ensuring keys are derived from user input
rather than stored. However, the plans prioritized functional completion over
defensive coding edge-cases, leading to several critical security and integrity
issues that required post-execution remediation.

### Strengths

- **Logical decomposition:** Dividing work into Waves ensured that infrastructure
  (db.py) was stable before integration began, preventing development blocking.
- **Idempotency by design:** Plan 03-01 explicitly required schema updates to be
  idempotent — a high-maturity practice for SQLite desktop app migrations.
- **Memory safety awareness:** Requiring `get_device`/`list_devices` to return
  ciphertext and decryption to happen only at connection time shows strong
  adherence to CRED-04's "short-lived memory reference" requirement.
- **Test isolation:** Using `tmp_path`-based `conftest.py` in Plan 03-02 ensures
  security testing never touches production data.

### Concerns

- **[HIGH] Permissive API defaults:** Plans 03-03 and 03-04 allowed
  `session_key=None` as a default parameter. In a security-critical context,
  `None` should be an error state, not a default. This allowed accidental
  paths where code could save data without a key, leading to the CR-03
  double-encryption bug.
- **[HIGH] Transport security blind spot:** The plans focused exclusively on
  encryption-at-rest but ignored transport implications of modifying
  `connector.py`. Touching connection logic without auditing default security
  settings (like `strict_host_key_checking`) left a MITM vulnerability open
  (CR-01, WR-02).
- **[MEDIUM] Implicit failures in migration:** Plan 03-05 described migration
  as "non-fatal" without specifying the user-visible response to failure. In
  code, "non-fatal" became "silent failure," leaving users in an insecure
  state without knowing it (CR-02).
- **[LOW] Weak heuristics for token detection:** Plan 03-01's `_is_fernet_token`
  relied on length and base64 checks without specifying the Fernet version byte
  validation — prone to false positives on base64-like plaintext (WR-04).

### Suggestions

- **Strict typing and keyword-only arguments:** Future plans should mandate `*`
  in function signatures for security parameters, forcing callers to be explicit.
- **Explicit UI error states:** Plans involving background tasks should define
  the required UI response for failure.
- **Defense-in-depth tests:** Expand test plans to include negative testing —
  invalid key, malformed ciphertext, partial migration failure.
- **Holistic security review:** When a plan touches a security-sensitive module,
  include a task to audit existing transport-layer defaults.

### Plan-by-Plan Notes

| Plan | Assessment |
|------|------------|
| 03-01 | Strong foundation; `_is_fernet_token` spec too vague → WR-04 |
| 03-02 | Good coverage of happy path; missing error-path tests → CR-02, WR-04 |
| 03-03 | Correct design; missed SSH audit opportunity → CR-01, WR-02 |
| 03-04 | Identified double-encryption risk then left `None` default → CR-03 |
| 03-05 | Correct wiring; migration error handling underspecified → CR-02 |
| 03-06 | Functional verification only; no security audit step → all 7 findings missed |

### Overall Verdict

**RETROSPECTIVE: APPROVE_WITH_LESSONS**

The plans are architecturally sound. The high-level logic (PBKDF2 → Fernet →
RAM-only) was correct, which prevented a total failure of the security model.
However, "last-mile" implementation details (error handling, default parameters,
transport security) were loose enough to introduce critical vulnerabilities.
The core learning: for Phase 4, plans must explicitly define **Failure Modes**
and **Strict Interfaces** rather than just happy-path functionality.

**Overall risk: MEDIUM**

---

## Claude Review

### Plan 03-01 — Crypto helpers + schema migration

#### Summary

Plan 03-01 is the strongest plan in the phase. It correctly identifies all six
required functions, establishes the right abstraction boundaries (raw ciphertext
on read paths, encryption only at write paths), and anticipates the most dangerous
anti-pattern (hazmat PBKDF2 single-use instance). The specification of 600k
iterations is a concrete, correct choice. However, the plan under-specifies error
handling in two places that surfaced as code review findings, and the
`_is_fernet_token` spec is imprecise enough to produce a subtly incorrect
implementation.

#### Strengths

- Correctly prohibits `cryptography.hazmat.PBKDF2HMAC` with explicit rationale
  (single-use-per-instance footgun) — prevents a non-obvious silent bug
- Correctly mandates `get_device()`/`list_devices()` return raw ciphertext,
  pushing decryption responsibility to callers — clean separation of concerns
- Idempotent schema migration via `try/except OperationalError` is right for
  a schema-as-code SQLite app with no formal migration runner
- Specifying `session_key` as keyword-only in `add_device`/`update_device`
  prevents accidental positional argument misuse
- Empty string and None guards handle the real-world case of devices with no
  enable password

#### Concerns

- **[HIGH] `_is_fernet_token` spec is too vague.** "prefix + base64 length check
  (>= 57 bytes decoded)" doesn't mention the Fernet version byte (`\x80`), that
  base64 must be URL-safe, or that padding validation matters. WR-04 was a direct
  consequence.
- **[HIGH] `migrate_plaintext_passwords` error handling not specified.** The plan
  specifies the return type (`int`) but says nothing about what happens when a
  row's migration fails mid-batch. This silence led to CR-02.
- **[MEDIUM] `get_or_create_salt` atomicity not specified.** Doesn't specify what
  happens if the row-write succeeds but a subsequent read-back fails. WR-01 was
  the result.
- **[LOW] No Unicode password specification.** `derive_session_key` encoding
  (UTF-8) is assumed but not stated.

#### Suggestions

- Expand `_is_fernet_token` spec: check `\x80` Fernet version byte after base64
  decode, use `urlsafe_b64decode`, verify decoded length is exactly 73+ bytes.
- Add error-handling contract to `migrate_plaintext_passwords`: "on per-row
  failure, log row ID and skip; return `(migrated_count, failed_count)` tuple."
- Add atomicity requirement to `get_or_create_salt`: "re-read persisted salt
  from DB after write and use the persisted value, not the in-memory bytes."

#### Risk Assessment: **MEDIUM**

Crypto design is sound. Risk concentrated in implementation details of two
functions where underspecification produced subtly wrong code that passed obvious
tests but failed edge-case review.

#### Retrospective Note

Three of the seven post-execution findings (CR-02, WR-01, WR-04) trace directly
to underspecification here. A plan-level security review checklist for crypto
functions would have caught these. Specifically: *"specify the exact algorithm
for token detection with test vectors"* and *"specify error-handling contract for
all functions that can partially fail."*

---

### Plan 03-02 — Unit test scaffold

#### Summary

The test plan is well-structured for the happy path but is missing tests for
error paths and the behaviors that later caused review findings. Tests verified
correctness under nominal conditions, not against adversarial or degenerate inputs.

#### Strengths

- `test_key_never_written_to_disk` is an excellent security-property test —
  checks actual DB file bytes, not just application-layer behavior
- `test_no_double_encryption` directly tests the most dangerous data-corruption
  scenario; migration idempotency is correctly verified
- `test_get_device_returns_ciphertext` enforces the read-path architectural
  invariant that protects all callers
- `tmp_path` isolation via `conftest.py` is the right approach for SQLite

#### Concerns

- **[HIGH] No test for wrong-key decryption.** `decrypt_field` is specified to
  return `None` on `InvalidToken`. No test verifies this contract — a future
  refactor would silently break callers without a failing test.
- **[HIGH] No test for `_is_fernet_token` edge cases.** WR-04 was a token
  detection bug. The test plan has no test for: non-token base64 misidentified
  as token, actual token correctly identified, or wrong-version-byte string.
- **[MEDIUM] No test for migration failure path.** A
  `test_migrate_fails_gracefully_on_corrupt_row` would have surfaced CR-02.
- **[MEDIUM] No test for `get_or_create_salt` idempotency.**
- **[LOW] 7 tests for a security-critical module is thin.**

#### Suggestions

- Add `test_decrypt_wrong_key_returns_none`
- Add `test_fernet_token_detection` with parameterized cases
- Add `test_migrate_partial_failure`
- Add `test_get_or_create_salt_stable`

#### Risk Assessment: **MEDIUM**

All 7 tests can pass while `_is_fernet_token` has a detection bug and migration
silently swallows errors. False confidence risk.

#### Retrospective Note

The pattern: the test plan verified *what the plan said would work*, not *what
could go wrong*. Phase 4 SSH verification plans should include an explicit
"adversarial test" category — tests designed around failure modes and
attacker-controlled inputs.

---

### Plan 03-03 — connector.py + panels/base.py

#### Summary

Plan 03-03 correctly implements CRED-04. The threading design is sound and
function signature changes are consistent. However, the STRIDE note reaches the
wrong conclusion about `session_key=None` safety, and the plan misses an
opportunity to audit connector.py's existing SSH security posture — which would
have caught CR-01 and WR-02.

#### Strengths

- Centralizing decryption in `_netmiko_device` and `_genie_testbed` is
  architecturally correct — one change point covers both transport paths
- Raising `ValueError` on `None` return is the right fail-loud behavior
- Including `panels/base.py` in scope prevents the common error of updating
  connector.py's signature without updating callers
- `set_device(device, session_key=None)` correctly threads session_key through
  the panel layer without requiring all panels to change constructors

#### Concerns

- **[HIGH] STRIDE note reaches the wrong conclusion.** The plan argues
  `session_key=None` is safe in `BasePanel` because the `if not self._device:
  return` guard ensures session_key is only None when device is also None. This
  reasoning is correct for `BasePanel.fetch()` but doesn't apply to
  `DeviceManagerDialog.load_device()`. CR-03 found exactly this gap.
- **[HIGH] No audit of existing SSH security configuration.** This plan modifies
  connector.py for security reasons but doesn't audit existing SSH config.
  CR-01 (`strict_host_key_checking=False`) and WR-02 (legacy algorithm downgrade)
  were already present — the plan authors were already in the file.
- **[MEDIUM] No test plan for connector changes.**
- **[LOW] `_genie_fetch` fallback path threading implied but not stated.**

#### Suggestions

- Expand STRIDE to audit every caller of `decrypt_field` and every location where
  a device dict's password field is read — not just `BasePanel`.
- Add sub-task: *"Audit connector.py for existing SSH security configuration
  before applying session_key threading. Flag `strict_host_key_checking`,
  `look_for_keys`, and `disabled_algorithms` for review."*
- Add `test_decrypt_called_at_connection_time` to the test plan.

#### Risk Assessment: **MEDIUM**

Design is correct. The risk: STRIDE reasoning created false confidence, and the
plan missed an in-scope opportunity to catch two pre-existing SSH security issues.

#### Retrospective Note

CR-01 and WR-02 were pre-existing issues in connector.py that the plan touched
but didn't audit. The lesson: when a security-focused plan touches a file, it
should include a mini security audit of that file's existing configuration.

---

### Plan 03-04 — device_manager.py

#### Summary

Plan 03-04 is internally contradictory in a critical way: it correctly identifies
the double-encryption anti-pattern, explains exactly why it's dangerous, and then
specifies the precise implementation that enables it. The anti-pattern warning is
accurate, but the specified `session_key=None` default creates the code path it
warned against.

#### Strengths

- Explicit "critical anti-pattern avoided" note is good plan hygiene
- Keyword-only `session_key` in `DeviceManagerDialog.__init__` prevents
  accidental omission at the constructor call site
- `if _pw is not None else ""` guard for `setText` prevents crash on decrypt failure
- `_on_item_clicked` threading session_key through to `load_device` is correct

#### Concerns

- **[CRITICAL] Plan specifies `session_key=None` default in `load_device` while
  simultaneously warning about the exact failure mode this enables.** CR-03
  fixed this by making it a required keyword-only argument. The plan's own
  anti-pattern warning should have been the specification.
- **[HIGH] The fallback guard `if session_key else device['password']` silently
  loads ciphertext into the form when session_key is None.** In a
  post-migration world, a user would see a Fernet token and potentially save it,
  causing double-encryption.
- **[MEDIUM] No specification for `decrypt_field` returning `None`.** Silence
  means an empty field, which a user might "fix" by typing a new password —
  silently losing the real credential.
- **[LOW] Inconsistent keyword-only discipline** between `DeviceManagerDialog`
  and `DeviceFormWidget`.

#### Suggestions

- Change `load_device` to `load_device(device, *, session_key: bytes)` —
  required keyword-only, no default.
- Add specification for `decrypt_field` returning `None`: show a warning label;
  do not allow form save while decrypt result is None.
- Replace fallback guard with explicit pre-condition: if session_key is None,
  raise ValueError — programming error, not a recoverable runtime state.

#### Risk Assessment: **HIGH**

The double-encryption failure mode is unrecoverable. The specification created
the exact path it warned against. Most actionable and most preventable finding.

#### Retrospective Note

CR-03 was the most predictable post-execution finding because it was described
in the plan itself. The lesson: if a plan includes an "anti-pattern to avoid"
section, the specification must make that anti-pattern **impossible** — not just
unlikely. Required keyword-only arguments are the tool.

---

### Plan 03-05 — main.py: login-time key derivation

#### Summary

Plan 03-05 is well-scoped and correctly places key derivation at the earliest
safe point (post-bcrypt, pre-MainWindow). The propagation chain to all five
downstream consumers is complete and correctly ordered. The primary gap is that
migration error handling ("non-fatal — unencrypted rows remain readable") is too
vague, which led to the silent swallow that CR-02 fixed.

#### Strengths

- `derive_session_key` immediately after bcrypt verification is the correct
  lifecycle point
- `MainWindow.__init__(self, user: dict, session_key: bytes)` as required
  positional argument makes it impossible to construct MainWindow without a key
- STRIDE note that session_key is never written to disk is correct and followed
- All 5 panels in `_on_device_selected` ensures no panel can be activated with
  a stale or missing session_key

#### Concerns

- **[HIGH] "Migration failure is non-fatal" is underspecified.** Plan doesn't
  say what the user sees. The pre-CR-02 implementation swallowed the exception
  silently. Should have specified: *"display a QMessageBox.warning with the
  error detail and continue login."*
- **[MEDIUM] Bootstrap failure path unspecified.** If `login.session_key` is
  not set (dialog cancelled), `main()` would construct `MainWindow` with None.
- **[MEDIUM] Session key lifecycle not addressed.** Should explicitly note this
  is out of scope for Phase 3.
- **[LOW] Migration timing relative to MainWindow creation not stated.**

#### Suggestions

- Add to Task 1: migration try/except must call `QMessageBox.warning(self,
  'Migration Warning', str(e))`.
- Add guard to `main()`: check `login.session_key is not None` before
  constructing `MainWindow`.
- Add explicit out-of-scope note for session key lifecycle.

#### Risk Assessment: **LOW**

Wiring design is correct and complete. Risks are in error path handling and
migration UX — both fixed by CR-02.

#### Retrospective Note

For Phase 4: any plan step that says "catch exception and continue" should
specify the minimum user-visible feedback. Silent exception handling in
security-adjacent code is almost always a mistake.

---

### Plan 03-06 — Functional verification checkpoint

#### Summary

Plan 03-06 is a good functional verification checklist but is limited to feature
correctness. It verifies that credentials are encrypted and decrypt-on-demand
works, but includes no security verification steps. For a security milestone, the
verification checkpoint should itself have a security dimension.

#### Strengths

- "DB inspection — passwords start with gAAAA" is an excellent zero-tooling
  human verification step
- "Device Manager edit form shows plaintext" directly verifies CRED-04 at
  the UI layer
- "Second login still decrypts correctly" catches the salt persistence bug class
- Separating automated suite from human checklist is correct

#### Concerns

- **[HIGH] No security-specific verification steps.** A step like *"grep
  connector.py for `strict_host_key_checking`, `disabled_algorithms` and verify
  no insecure values"* would have caught CR-01 and WR-02.
- **[MEDIUM] 7-test suite is the only automated check.** Given the test plan
  gaps, passing these 7 tests provides less assurance than it appears to.
- **[MEDIUM] "Optional: real device SSH connection"** should be required if
  any test device is available.
- **[LOW] No integration-level idempotency check.**

#### Suggestions

- Add security verification section: *"grep each modified file for known insecure
  configuration patterns before closing the phase."*
- Add Step 7: Close app and re-login; verify all credentials still decrypt.
- Add annotation: *"Note: test suite covers happy path only."*

#### Risk Assessment: **LOW**

The checkpoint does what it specifies. The risk is that it specifies too little —
functional verification only, for a security milestone.

#### Retrospective Note

Four of the seven post-execution findings (CR-01, WR-02, WR-03, WR-04) were not
in scope for this checklist because the plans never specified those behaviors.
A security milestone's verification checkpoint should explicitly audit security
posture of every modified file, not just new code correctness.

---

### Phase-Level Summary (Claude)

| Plan | Overall | Highest Severity Gap | Predictability |
|------|---------|---------------------|----------------|
| 03-01 | Good | Vague `_is_fernet_token` spec | WR-04, WR-01 predictable from spec |
| 03-02 | Fair | Missing error-path tests | CR-02, WR-04 predictable from test gaps |
| 03-03 | Good | False STRIDE confidence, no SSH audit | CR-01, WR-02 preventable with in-file audit |
| 03-04 | Fair | Spec enables the anti-pattern it warns against | CR-03 preventable — plan identified the risk |
| 03-05 | Good | Error handling underspecified | CR-02 fix scope partly preventable |
| 03-06 | Fair | Functional-only verification for security milestone | All 7 findings missed |

---

## Consensus Summary

### Agreed Strengths

- **Wave-based dependency ordering** (both) — infrastructure-first prevents
  integration-blocking bugs
- **Idempotent schema migration** (both) — correct pattern for schema-as-code
  SQLite without a migration runner
- **Memory-safe read path** (both) — `get_device`/`list_devices` returning
  ciphertext correctly enforces CRED-04
- **Test isolation via `tmp_path`** (both) — no production DB risk during testing
- `test_key_never_written_to_disk` and `test_no_double_encryption` as high-value
  security-property tests

### Agreed Concerns

| Concern | Severity | Finding | Both reviewers |
|---------|----------|---------|----------------|
| `session_key=None` default in security-critical path | HIGH | CR-03 | ✓ |
| No audit of existing SSH config when touching connector.py | HIGH | CR-01, WR-02 | ✓ |
| Migration error handling underspecified | MEDIUM | CR-02 | ✓ |
| `_is_fernet_token` spec too vague | MEDIUM | WR-04 | ✓ |
| Missing error-path tests | MEDIUM | CR-02, WR-04 | ✓ |
| Salt persistence atomicity unspecified | MEDIUM | WR-01 | ✓ |

### Action Items for Phase 4 Planning

Apply these to all Phase 4 plans:

1. **Required keyword-only arguments for security params** — no `session_key=None`
   defaults. When a parameter is required for correct security behavior, make it
   keyword-only with no default. If a caller cannot provide the value, that call
   site is wrong.

2. **Error contract for every function that can partially fail** — every spec
   must include: "on failure, do X (show QMessageBox / skip-and-log / raise)."
   "Non-fatal" is not a specification.

3. **In-file security audit when touching connector.py** — any Phase 4 plan
   modifying connector.py must include: *"before committing, grep for
   `strict_host_key_checking`, `verify=False`, `disabled_algorithms`,
   `allow_agent=True` and verify none are insecure."*

4. **Verification checkpoints must include security verification** — Phase 4's
   verification checkpoint should verify that host key checking *actually rejects*
   unknown hosts, not just that the dialog appears.

5. **Adversarial test category** — Phase 4 test plans must include at least one
   test per new security-critical function that tests the failure path, not just
   the success path.

6. **Anti-pattern notes must close the anti-pattern in the spec** — if a plan
   describes a failure mode, the specification must make it impossible via
   required args / fail-loud behavior. If the plan says "never do X," the spec
   should make X a compile-time or import-time error.

To incorporate feedback into planning:
  /gsd-plan-phase 4 --reviews
