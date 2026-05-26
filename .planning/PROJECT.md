# RemoteIn — Code Cleanup & Quality Milestone

## What This Is

A focused cleanup milestone for **RemoteIn** — a local PyQt6 desktop GUI for
querying Cisco and other vendor network devices over SSH.

This milestone does not add features. It resolves the highest-value technical
debt identified in the codebase map: structural duplication in `connector.py`,
visible bugs in panel rendering, and dead code that adds noise without purpose.

Security concerns (plaintext device credentials, SSH host key verification)
are explicitly out of scope — they belong in a dedicated security milestone.

---

## Core Value

**The single most important thing:** Extract `_genie_fetch()` to eliminate the
six copy-pasted Genie blocks in `connector.py` — the highest-leverage single
change in the codebase. Everything else supports that or stands independently.

---

## Context

- **Owner:** Isaac (isaacdwlee@gmail.com) — network engineer learning to code
- **Runtime:** Windows, PyQt6, Python 3.11+, Netmiko + NTC templates
- **Style:** Commit-by-commit narrative — explain each change as a coding lesson
- **Branch:** gsd-review-code-cleanup

### Existing Capabilities (Validated)

The codebase already delivers:

- ✓ PyQt6 desktop GUI with dark amber theme — existing
- ✓ Login dialog with bcrypt-hashed user accounts — existing
- ✓ Device inventory in SQLite — existing
- ✓ Three-path parsing: Genie → TextFSM → raw CLI — existing
- ✓ Five data panels: Interfaces, Routing, BGP/OSPF, ARP/MAC, CLI — existing
- ✓ BasePanel threading pattern (QThread + FetchWorker) — existing
- ✓ Admin user management dialog — existing
- ✓ Six supported platforms: ios, iosxe, iosxr, nxos, eos, junos — existing

---

## Requirements

### Validated

(All existing capabilities above — shipped and working)

### Active

**Maintainability Refactors:**
- [ ] Extract `_genie_fetch(device, cmd)` helper in `connector.py` — eliminates 6× copy-paste (priority #1)
- [ ] Fix `BasePanel._on_result` stub to raise `NotImplementedError` like `_build_content` and `_run_fetch`
- [ ] Extract shared `DualTablePanel` logic from `NeighborPanel` and `ArpMacPanel` (or at minimum document the pattern)

**Bug Fixes:**
- [ ] Fix BGP Genie path column mismatch in `panels/bgp_ospf.py` — `up_down`/`prefixes`/`description` mapped to wrong headers
- [ ] Guard `conn.enable()` call in `connector.py` — skip for EOS and JunOS platforms that have no enable mode
- [ ] Add shared color palette constant in `panels/base.py` to replace repeated hex strings across panel files

**Dead Code Removal:**
- [ ] Remove `run_in_thread()` from `connector.py` — unused, never called by any panel
- [ ] Make CLI history table use `make_table()` helper consistently with all other panels

### Out of Scope

- Credential encryption — separate security milestone
- SSH host key trust dialog — separate security milestone
- Adding a test suite — separate quality milestone
- Role enforcement for operators — separate feature milestone
- Connection pooling / SSH session caching — separate performance milestone
- Export to CSV/clipboard — separate feature milestone
- New device platforms or vendor support — not this milestone

---

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| `_genie_fetch()` returns `dict or None` | None signals fallback to TextFSM; callers check before using | Active |
| `conn.enable()` guarded by platform key | Simpler than capability flags; platform keys are already the source of truth | Active |
| `DualTablePanel` extraction | May be too abstract given only 2 panels use it; assess after bug fixes | Pending |
| Security out of scope | Credential encryption is non-trivial and touches auth flow; safer as a dedicated milestone | Decided |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-05-25 after initialization*
