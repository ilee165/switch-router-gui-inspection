# RemoteIn — Security Milestone

## What This Is

RemoteIn is a local desktop GUI for querying Cisco (and other vendor) network
devices over SSH. Built with PyQt6. Runs fully offline on Windows.

The primary user is a Network Engineer who is also learning to code.

## Core Value

A safe, offline tool — device credentials are never stored or transmitted in
plaintext, and SSH connections verify server identity before trusting them.

## Context

- **Owner:** Isaac — network engineer learning to code
- **Runtime:** Windows, PyQt6, Python 3.11+, Netmiko + NTC templates
- **Style:** Commit-by-commit narrative — explain each change as a coding lesson
- **Branch:** gsd-security-milestone
- **Prior milestone:** Code Cleanup & Quality (v1.0) — COMPLETE 2026-05-27

## Key Decisions

| Decision | Outcome |
|---|---|
| `_genie_fetch()` returns `dict or None` | None signals fallback to TextFSM — ✓ |
| `conn.enable()` guarded by `NO_ENABLE_PLATFORMS` | Platform keys are source of truth — ✓ |
| `DualTablePanel` extraction deferred | Only 2 panels use it; assess next milestone |
| Credential key derives from login password | No external keystore needed; key gone at logout |
| SSH host key: show dialog on first connect | Matches PuTTY UX; user controls trust explicitly |

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

## Active Requirements

| ID | Description | Phase | Status |
|----|-------------|-------|--------|
| CRED-01 | Device passwords encrypted at rest in SQLite (AES-256 via Fernet) | 3 | Pending |
| CRED-02 | Encryption key derived from login password (PBKDF2) — never stored | 3 | Pending |
| CRED-03 | Existing plaintext passwords migrated to encrypted form on first login | 3 | Pending |
| CRED-04 | Decrypted password exists only in memory during a connection | 3 | Pending |
| SSH-01 | First connect to unknown host shows fingerprint dialog (Accept / Reject / Always Trust) | 4 | Pending |
| SSH-02 | Accepted host keys stored in SQLite `host_keys` table | 4 | Pending |
| SSH-03 | Reconnect with changed host key triggers a warning dialog before proceeding | 4 | Pending |
| SSH-04 | User can view and delete stored host keys from device settings | 4 | Pending |

## Current State

Security milestone v1.1 started 2026-05-27. No phases complete yet.

---
*Last updated: 2026-05-27 — start of Security milestone v1.1*
