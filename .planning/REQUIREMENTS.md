# REQUIREMENTS.md — RemoteIn Code Cleanup & Quality

Milestone: Code Cleanup & Quality
Generated: 2026-05-25

---

## Active Requirements

| ID | Description | Phase | Status |
|---|---|---|---|
| MAINT-01 | `_genie_fetch(device, cmd)` helper in `connector.py` replaces six copy-pasted Genie blocks | 1 | Complete |
| BUG-02 | EOS/JunOS fetch does not throw enable-mode error | 1 | Complete |
| DEAD-01 | `run_in_thread()` removed from `connector.py` | 1 | Complete |
| MAINT-02 | `BasePanel._on_result` raises `NotImplementedError` when not overridden | 2 | Pending |
| MAINT-03 | `PALETTE` dict in `panels/base.py` — no inline hex literals in panel files | 2 | Pending |
| BUG-01 | BGP table shows correct Router ID, Remote IP, VRF when Genie is parse source | 2 | Pending |
| DEAD-02 | CLI history table built via `make_table()` from `base.py` | 2 | Pending |

## Out of Scope

- Credential encryption, SSH host key dialog, brute-force protection — security milestone
- pytest suite — testing milestone
- Role enforcement beyond menu hiding — feature milestone
- Connection pooling, export to CSV, `DualTablePanel` extraction — future milestones
