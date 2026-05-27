# REQUIREMENTS.md — RemoteIn Security

Milestone: Security (v1.1)
Generated: 2026-05-27

---

## Prior Milestone Requirements (Code Cleanup & Quality — Complete)

| ID | Description | Phase | Status |
|---|---|---|---|
| MAINT-01 | `_genie_fetch(device, cmd)` helper in `connector.py` replaces six copy-pasted Genie blocks | 1 | Complete |
| BUG-02 | EOS/JunOS fetch does not throw enable-mode error | 1 | Complete |
| DEAD-01 | `run_in_thread()` removed from `connector.py` | 1 | Complete |
| MAINT-02 | `BasePanel._on_result` raises `NotImplementedError` when not overridden | 2 | Complete |
| MAINT-03 | `PALETTE` dict in `panels/base.py` — no inline hex literals in panel files | 2 | Complete |
| BUG-01 | BGP table shows correct Router ID, Remote IP, VRF when Genie is parse source | 2 | Complete |
| DEAD-02 | CLI history table built via `make_table()` from `base.py` | 2 | Complete |

---

## Active Requirements (Security — v1.1)

### Credential Encryption

- [ ] **CRED-01**: Device passwords are encrypted at rest in SQLite using AES-256 (Fernet)
- [ ] **CRED-02**: The encryption key is derived from the user's login password via PBKDF2 — key is never stored on disk
- [ ] **CRED-03**: On first login after upgrade, existing plaintext passwords in the DB are automatically migrated to encrypted form
- [ ] **CRED-04**: Decrypted passwords exist only in memory for the duration of a connection and are never written back to disk

### SSH Host Key Verification

- [ ] **SSH-01**: On first connect to an unknown host, a dialog shows the server's key fingerprint with Accept / Reject / Always Trust options
- [ ] **SSH-02**: Accepted host keys are stored persistently in a `host_keys` table in SQLite
- [ ] **SSH-03**: If a stored host key no longer matches on reconnect, a warning dialog is shown and the user must explicitly accept before connecting
- [ ] **SSH-04**: User can view and delete stored host key entries from device settings

## Out of Scope

| Feature | Reason |
|---|---|
| External key management (Vault, Windows Credential Manager) | Overkill for single-user desktop app |
| Multi-user credential isolation | Single-user app; one SQLite DB per installation |
| Certificate-based SSH authentication | Future milestone |
| Per-user key derivation (multi-account) | Single login; out of scope |
| pytest suite | Testing milestone |
| Role enforcement beyond menu hiding | Feature milestone |
| Connection pooling, export to CSV, `DualTablePanel` extraction | Future milestones |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CRED-01 | Phase 3 | Pending |
| CRED-02 | Phase 3 | Pending |
| CRED-03 | Phase 3 | Pending |
| CRED-04 | Phase 3 | Pending |
| SSH-01 | Phase 4 | Pending |
| SSH-02 | Phase 4 | Pending |
| SSH-03 | Phase 4 | Pending |
| SSH-04 | Phase 4 | Pending |

**Coverage:** 8 active requirements — 8 mapped to phases, 0 unmapped.
