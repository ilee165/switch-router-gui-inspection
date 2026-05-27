# RemoteIn — Code Cleanup & Quality Milestone

## What This Is

Focused cleanup milestone — no new features. Resolves highest-value technical
debt in `connector.py` and the panels layer.

**Core Value:** Extract `_genie_fetch()` to eliminate six copy-pasted Genie
blocks in `connector.py`. Everything else supports that or stands independently.

## Context

- **Owner:** Isaac — network engineer learning to code
- **Runtime:** Windows, PyQt6, Python 3.11+, Netmiko + NTC templates
- **Style:** Commit-by-commit narrative — explain each change as a coding lesson
- **Branch:** gsd-review-code-cleanup

## Key Decisions

| Decision | Outcome |
|---|---|
| `_genie_fetch()` returns `dict or None` | None signals fallback to TextFSM |
| `conn.enable()` guarded by `NO_ENABLE_PLATFORMS` | Platform keys are source of truth |
| `DualTablePanel` extraction deferred | Only 2 panels use it; assess next milestone |
| Security out of scope | Dedicated security milestone |
| `PALETTE` keys: success/error/caution | Centralizes #10B981, #EF4444, #F59E0B |
| BGP cols 0/4 both show `nbr_ip` | Intentional — matches TextFSM path behavior (D-07) |

## Validated Requirements

| ID | Description | Validated |
|----|-------------|-----------|
| MAINT-01 | `_genie_fetch()` helper eliminates six duplicated Genie blocks | Phase 1 |
| BUG-02 | EOS/JunOS enable-mode guard added | Phase 1 |
| DEAD-01 | `run_in_thread()` dead code removed | Phase 1 |
| MAINT-02 | `BasePanel._on_result` raises `NotImplementedError` | Phase 2 |
| MAINT-03 | `PALETTE` constant — no inline hex in panel files | Phase 2 |
| BUG-01 | BGP Genie columns corrected (router_id, nbr_ip, vrf_name) | Phase 2 |
| DEAD-02 | CLI history table uses `make_table()` | Phase 2 |

## Current State

Both phases complete as of 2026-05-27. Milestone: Code Cleanup & Quality — COMPLETE.

Candidate next work (not committed):
- CR-01: Fix OSPF TextFSM key `"address"` → `"ip_address"` in `_populate_ospf_textfsm()`
- Security milestone: device credential encryption, SSH host key verification
- Testing milestone: pytest suite

---
*Last updated: 2026-05-27*
