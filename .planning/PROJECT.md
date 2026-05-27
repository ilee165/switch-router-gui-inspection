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

---
*Last updated: 2026-05-25*
