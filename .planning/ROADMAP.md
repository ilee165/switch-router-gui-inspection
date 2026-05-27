# ROADMAP.md — RemoteIn Code Cleanup & Quality

## Phases

| # | Name | Status | Requirements | Completed |
|---|---|---|---|---|
| 1 | connector.py Cleanup | Complete | MAINT-01, BUG-02, DEAD-01 | 2026-05-27 |
| 2 | Panels Cleanup | Not started | MAINT-02, MAINT-03, BUG-01, DEAD-02 | - |

## Phase 2 Plans

- [ ] 02-01-PLAN.md — MAINT-02 + MAINT-03 + BUG-01 + DEAD-02: enforce `_on_result`
  contract, add `PALETTE` + replace inline hex in 3 files, fix BGP Genie column
  tuple, migrate CLI table to `make_table()` (4 tasks + human-verify checkpoint;
  sequential due to shared `base.py` and `bgp_ospf.py` edits)

## Success Criteria — Phase 2

1. `BasePanel._on_result()` raises `NotImplementedError` when not overridden
2. Hex values `#10B981`, `#EF4444`, `#F59E0B` only in `PALETTE` in `panels/base.py`
3. BGP panel shows correct Router ID, Remote IP, VRF when Genie is parse source
4. CLI history table built via `make_table()` from `base.py`
