## What does this PR do?

<!-- One or two sentences. What changed and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature (panel, vendor support, UI improvement)
- [ ] Refactor / code cleanup
- [ ] Docs / CLAUDE.md update

## Testing

- [ ] Ran `python main.py` and the app launches without errors
- [ ] Exercised the affected panel(s) or dialog(s) manually
- [ ] Tested on a real device, a lab device, or confirmed behaviour with raw Netmiko output

## Checklist

- [ ] No inline `setStyleSheet()` calls — styles added to `styles.py` only
- [ ] No network calls on the main thread — used `_start_worker()` from `BasePanel`
- [ ] SQL uses `?` placeholders — no f-strings in queries
- [ ] Panels only call `connector.py` — not `db.py` directly
- [ ] `CLAUDE.md` updated if architecture, structure, or known issues changed

## Screenshots (if UI changed)

<!-- Drag and drop a screenshot here, or delete this section -->
