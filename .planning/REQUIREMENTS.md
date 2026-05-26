# REQUIREMENTS.md — RemoteIn Code Cleanup & Quality

Milestone: Code Cleanup & Quality
Generated: 2026-05-25

---

## v1 Requirements

### Maintainability

- [ ] **MAINT-01**: Developer can see a single `_genie_fetch(device, cmd)` helper in `connector.py` replacing six identical copy-pasted Genie blocks
- [ ] **MAINT-02**: `BasePanel._on_result` raises `NotImplementedError` when not overridden (consistent with `_build_content` and `_run_fetch`)
- [ ] **MAINT-03**: Panel color constants (`#10B981`, `#EF4444`, `#F59E0B`) come from a shared `PALETTE` dict in `panels/base.py` — not repeated inline across panel files

### Bug Fixes

- [ ] **BUG-01**: BGP table shows correct data under "Router ID", "Remote IP", "VRF" headers when Genie is the parse source (Linux/Mac)
- [ ] **BUG-02**: Fetching data from Arista EOS or Juniper JunOS devices does not throw an enable-mode error when no enable password is configured

### Dead Code

- [ ] **DEAD-01**: `run_in_thread()` is removed from `connector.py` (unused — all threading goes through `BasePanel._start_worker()`)
- [ ] **DEAD-02**: CLI history table is built using `make_table()` helper from `base.py`, consistent with all other panel tables

---

## v2 Requirements (Deferred)

- Credential encryption for device passwords (separate security milestone)
- SSH host key trust dialog (separate security milestone)
- pytest suite for db.py, connector helpers, panel _on_result logic (separate testing milestone)
- Role enforcement for operator accounts beyond menu hiding
- Connection pooling / SSH session caching
- Export to CSV or clipboard
- `DualTablePanel` base class extraction for NeighborPanel + ArpMacPanel

---

## Out of Scope

- Plaintext device credential storage — security milestone
- SSH host key verification bypass (`ssh_strict=False`) — security milestone
- Login brute-force protection — security milestone
- New device platform support — feature milestone
- New data panels — feature milestone
- UI redesign or theme changes — not this milestone (styles.py is off-limits)
- QThread leak guard in `_start_worker()` — reliability milestone (non-trivial, needs design)

---

## Traceability

| REQ-ID | Phase | Status |
|--------|-------|--------|
| MAINT-01 | Phase 1 | Pending |
| BUG-02 | Phase 1 | Pending |
| DEAD-01 | Phase 1 | Pending |
| MAINT-02 | Phase 2 | Pending |
| MAINT-03 | Phase 2 | Pending |
| BUG-01 | Phase 2 | Pending |
| DEAD-02 | Phase 2 | Pending |
