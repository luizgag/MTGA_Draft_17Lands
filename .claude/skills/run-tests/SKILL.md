---
name: run-tests
description: Run pytest for the MTGA Draft 17Lands project, handling WSL/Xvfb setup automatically
user-invocable: true
---

# Run Tests

Run the project's pytest suite. Handles platform differences (WSL needs Xvfb + venv) automatically.

## Arguments

- `$ARGUMENTS` — Optional. A test target such as a file path (`tests/test_card_logic.py`), a specific test (`tests/test_card_logic.py::test_tier_results`), or pytest flags (`-k "test_otj" -v`). If omitted, runs all tests.

## Instructions

1. Detect the platform by checking if running under WSL (`uname -r` contains `microsoft` or `WSL`).

2. **If WSL/Linux:**
   - Start Xvfb if not already running: `Xvfb :99 -screen 0 1024x768x24 &>/dev/null &`
   - Export display: `export DISPLAY=:99`
   - Use the venv pytest: `.venv/bin/pytest`
   - If `.venv/` does not exist, tell the user to run the one-time setup from CLAUDE.md

3. **If Windows:**
   - Use `pytest` directly

4. Run the test command:
   ```bash
   # WSL — all tests
   Xvfb :99 -screen 0 1024x768x24 &>/dev/null & sleep 0.5; DISPLAY=:99 .venv/bin/pytest tests/ $ARGUMENTS

   # WSL — with specific target
   Xvfb :99 -screen 0 1024x768x24 &>/dev/null & sleep 0.5; DISPLAY=:99 .venv/bin/pytest $ARGUMENTS

   # Windows
   pytest tests/ $ARGUMENTS
   ```

5. Report the results: total passed, failed, skipped, and any failure details.
