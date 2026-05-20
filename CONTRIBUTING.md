# Contributing to RemoteIn

Thanks for considering a contribution. This is a small tool built and maintained
by a network engineer — contributions that improve reliability, add vendor support,
or clean up the code are all welcome.

---

## Before you start

Read [CLAUDE.md](CLAUDE.md) fully. It documents the architecture, layering rules,
styling system, known bugs, and the roadmap. It will save you time.

---

## How to contribute

1. **Fork** the repo and create a branch off `main`
2. Make your changes (see rules below)
3. Test manually — run `python main.py` and exercise the affected panels
4. Open a **pull request** with a clear description of what changed and why

For larger changes (new panels, new vendor support, architectural changes), open
an **issue first** to discuss the approach before writing code.

---

## Rules

- **No whole-file rewrites** — targeted edits only
- **No inline `setStyleSheet()` calls** — all styles go in `styles.py` using
  `objectName` selectors; do not change existing colors or theme values
- **Layering must be respected:**
  - `panels/` → calls `connector.py` only, never `db.py`
  - `main.py` → calls `db.py` for data, passes dicts to panels
  - `connector.py` → no GUI imports, no knowledge of widgets
- **SQL placeholders only** — never build SQL strings with f-strings
- **Network calls off the main thread** — use `_start_worker()` from `BasePanel`
- **No new dependencies** without discussion — keep the install footprint small

---

## Adding a new panel

1. Create `panels/your_panel.py` — subclass `BasePanel` and implement:
   - `_build_content(layout)` — widget setup
   - `_run_fetch()` — which `connector.py` function to call
   - `_on_result(data)` — how to render the result
2. Add a fetch function to `connector.py` following the Genie-try / Netmiko-fallback pattern
3. Export the class from `panels/__init__.py`
4. Add a tab in `main.py`

---

## Adding a new vendor / platform

1. Add the platform key and Netmiko device type to `PLATFORM_MAP` in `connector.py`
2. Add the Genie `os` value to `os_map` inside `_genie_testbed()`
3. Add a row to the supported platforms table in `README.md`
4. Test with a real device or a mock if possible

---

## Reporting bugs

Open a GitHub issue with:
- What you did
- What you expected
- What actually happened (include any error from the terminal)
- Your OS and Python version
