# ROADMAP.md — RemoteIn Code Cleanup & Quality

## Overview

Two-phase cleanup milestone. Phase 1 consolidates all `connector.py` changes
(the highest-leverage file in the codebase). Phase 2 cleans up the panels
layer. Both phases are independent of each other — Phase 2 does not depend on
Phase 1 completing first, but the logical order flows from backend-to-frontend.

---

## Phases

- [x] **Phase 1: connector.py Cleanup** - Extract _genie_fetch(), guard enable(), remove run_in_thread()
- [ ] **Phase 2: Panels Cleanup** - Fix BasePanel contract, add PALETTE, fix BGP Genie columns, refactor CLI table

---

## Phase Details

### Phase 1: connector.py Cleanup

**Goal**: `connector.py` has no duplicated Genie blocks, no unsafe enable() call, and no dead threading utility
**Mode:** mvp
**Depends on**: Nothing
**Requirements**: MAINT-01, BUG-02, DEAD-01
**Success Criteria** (what must be TRUE):

  1. A single `_genie_fetch(device, cmd)` helper exists and all six `get_*` functions call it — no copy-pasted Genie connect/parse/disconnect blocks remain
  2. Fetching data from an Arista EOS or Juniper JunOS device does not raise an enable-mode error or exception
  3. `run_in_thread()` does not appear anywhere in `connector.py`

**Plans:** 1 planPlans:

- [x] 01-01-PLAN.md — DEAD-01 + BUG-02 + MAINT-01: remove run_in_thread, guard enable() for EOS/JunOS, extract _genie_fetch helper (4 tasks, sequential within plan; ends in human-verify checkpoint)

### Phase 2: Panels Cleanup

**Goal**: The panels layer has a consistent contract, a single source of color truth, correct BGP data rendering, and a consistent table helper usage
**Mode:** mvp
**Depends on**: Nothing (can run independently, but logically follows Phase 1)
**Requirements**: MAINT-02, MAINT-03, BUG-01, DEAD-02
**Success Criteria** (what must be TRUE):

  1. Calling `BasePanel._on_result()` without overriding it raises `NotImplementedError` (matching the existing pattern for `_build_content` and `_run_fetch`)
  2. Color hex values `#10B981`, `#EF4444`, and `#F59E0B` appear only in `PALETTE` in `panels/base.py` — not as inline literals in any panel file
  3. The BGP panel shows correct Router ID, Remote IP, and VRF column data when Genie is the parse source on Linux/Mac
  4. The CLI panel history table is built via `make_table()` from `base.py`, not a custom table construction

**Plans**: TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. connector.py Cleanup | 1/1 | Complete | 2026-05-27 |
| 2. Panels Cleanup | 0/1 | Not started | - |
