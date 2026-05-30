---
status: partial
phase: 04-ssh-host-key-verification
source: [04-VERIFICATION.md]
started: 2026-05-30T04:10:00Z
updated: 2026-05-30T04:10:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. First-connect dialog appears for unknown host
expected: Dialog titled 'Unknown Host Key' with hostname, key type, SHA256 fingerprint, and three buttons: Reject / Accept Once / Always Trust
result: [pending]

### 2. Always Trust stores key in host_keys table
expected: Connection proceeds; DB row in host_keys with correct device_id, hostname, key_type, fingerprint
result: [pending]

### 3. Reject aborts connection and leaves no DB row
expected: Connection aborted, status bar shows error, zero rows in host_keys
result: [pending]

### 4. Silent reconnect after Always Trust (no dialog)
expected: No dialog; connection completes; panel data loads normally
result: [pending]

### 5. Changed host key triggers warning dialog
expected: 'Host Key Changed' dialog with both fingerprints, MITM warning, Cancel / Connect Anyway / Update Key buttons
result: [pending]
setup: Manually corrupt stored key_blob in host_keys then reconnect

### 6. SSH Keys tab shows stored keys (no key_blob)
expected: Table shows Key Type / Fingerprint / Added columns. DELETE SELECTED KEY button present. No raw key material visible.
result: [pending]

### 7. Delete key from SSH Keys tab
expected: Confirmation dialog → Yes → row disappears from table and from host_keys DB
result: [pending]

### 8. Fingerprint format matches ssh-keygen -l output
expected: Fingerprint starts with 'SHA256:' matching openssh-keygen -l for the same server
result: [pending]

## Summary

total: 8
passed: 0
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps
