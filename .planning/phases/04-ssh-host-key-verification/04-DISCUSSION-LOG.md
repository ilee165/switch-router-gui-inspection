# Discussion Log — Phase 4: SSH Host Key Verification

**Date:** 2026-05-29
**Phase:** 04-ssh-host-key-verification
**Areas discussed:** Accept vs Always Trust, Changed key response, SSH-04 UI placement

---

## Area 1: Accept vs Always Trust

**Q: Difference between Accept and Always Trust buttons?**
Options: Both store permanently | Accept = session only / Always Trust = permanent
Selected: **Both store permanently** — simpler for a local tool; both buttons write to host_keys.

**Q: Fingerprint display format?**
Options: SHA256:Base64 | Hex string
Selected: **SHA256:Base64** — OpenSSH standard, network engineers recognize it.

**Q: Window X button behavior?**
Options: Treat as Reject | Re-show dialog
Selected: **Treat as Reject** — closing without choice defaults to safe (abort connection).

**Q: Dialog contents?**
Options: Hostname + key type + fingerprint | Hostname + fingerprint only
Selected: **Show all three** — key type (ECDSA/RSA/ED25519) is a quick security signal.

---

## Area 2: Changed Key Response

**Q: Changed key dialog options?**
Options: Connect Anyway + Update Key + Cancel | Connect Anyway + Cancel | Block only
Selected: **Connect Anyway + Update Key + Cancel** — one dialog handles the full workflow.

**Q: Dialog tone?**
Options: ⚠️ Warning — "Host Key Changed" | ℹ️ Neutral — "Host Key Updated"
Selected: **Warning tone** — shows both fingerprints (stored vs new) for comparison.

**Q: "Connect Anyway" without updating — silent or notice?**
Options: Status bar notice | Connect silently
Selected: **Status bar notice** — "Connected (host key mismatch not resolved)".

---

## Area 3: SSH-04 UI Placement

**Q: Where in device settings?**
Options: New "SSH" tab | Expandable section | Separate dialog via button
Selected: **New "SSH" tab inside DeviceManagerDialog** — natural fit alongside credential fields.

**Q: Table columns?**
Options: Key Type | Fingerprint | Added date | Fingerprint only
Selected: **Key Type | Fingerprint | Added** — uses make_table() pattern.

**Q: Re-verify button?**
Options: No — delete only | Yes — add Verify button
Selected: **No** — delete only; re-verification happens on next connect. Deferred.

---

## Deferred Ideas

- "Re-verify" / "Test Key" button in SSH tab — out of scope, deferred
- Global "Known Hosts" manager (app-level) — out of scope, deferred
