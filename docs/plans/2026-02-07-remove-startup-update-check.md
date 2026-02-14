# Remove Startup Auto-Update Check Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the automatic update check that runs on application startup, while preserving the update infrastructure (`AppUpdate`, `check_version`, `download_file`) for potential future use (e.g., a manual "Check for Updates" menu item).

**Architecture:** The `__update_overlay_build()` method in `overlay.py` currently does two things: (1) checks for updates via the GitHub API, and (2) calls `__arena_log_check()` and `__control_trace(True)` to start the normal application flow. We will replace the call to `__update_overlay_build()` with direct calls to `__arena_log_check()` and `__control_trace(True)`, removing the update check from the startup path entirely.

**Tech Stack:** Python 3.12, Tkinter, pytest

---

### Task 1: Write a test to verify startup no longer calls the update check

**Files:**
- Modify: `tests/test_overlay.py`

**Step 1: Write the failing test**

Add a test that patches `AppUpdate` and verifies it is NOT instantiated during overlay initialization. This test documents the intended behavior: startup should not trigger an update check.

```python
@pytest.mark.skipif(sys.platform == "darwin", reason="Test may fail on macOS CI")
def test_overlay_init_does_not_check_for_updates(mocker):
    """Verify that creating an Overlay does not trigger an auto-update check."""
    mock_app_update = mocker.patch("src.overlay.AppUpdate")
    mock_check_version = mocker.patch("src.overlay.check_version")

    # The existing test fixtures/setup for Overlay should be used here.
    # If no fixture exists, instantiate Overlay with minimal mocking.
    # The key assertion:
    mock_app_update.assert_not_called()
    mock_check_version.assert_not_called()
```

> **Note to implementer:** Check `tests/test_overlay.py` for existing fixtures or patterns for instantiating the Overlay. If the Overlay requires extensive mocking to instantiate, the test can instead directly verify that `__update_overlay_build` is not called by patching it and asserting it was not called. Adapt the test approach to match the existing test patterns in the file.

**Step 2: Run the test to verify it fails**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_overlay_init_does_not_check_for_updates -v`

Expected: FAIL — because `__update_overlay_build()` currently calls `AppUpdate()` and `check_version()` during `__init__`.

**Step 3: Commit the failing test**

```bash
git add tests/test_overlay.py
git commit -m "test: add test verifying startup does not call update check"
```

---

### Task 2: Remove the startup update check call

**Files:**
- Modify: `src/overlay.py` (line 565 and lines 3125-3127)

**Step 1: Replace `__update_overlay_build()` call with direct startup calls**

In `src/overlay.py`, find the `__init__` method around line 565:

```python
# BEFORE (line 565):
        self.__update_overlay_build()
```

Replace with:

```python
# AFTER:
        self.__arena_log_check()
        self.__control_trace(True)
```

**Why:** `__update_overlay_build()` ends by calling `__arena_log_check()` and `__control_trace(True)` (lines 3125-3127). These two calls are what actually start the application's normal operation (log monitoring and UI trace control). By calling them directly, we skip the update check but preserve normal startup behavior.

**Step 2: Run the test from Task 1 to verify it passes**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_overlay_init_does_not_check_for_updates -v`

Expected: PASS

**Step 3: Run the full test suite to verify no regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`

Expected: All tests pass.

**Step 4: Commit**

```bash
git add src/overlay.py
git commit -m "feat: remove auto-update check from application startup"
```

---

### Task 3: Verify preserved infrastructure still works

**Files:**
- No modifications — verification only

**Step 1: Confirm `AppUpdate` class is still importable and functional**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_app_update.py -v`

Expected: All `test_app_update.py` tests pass (these test `AppUpdate.retrieve_file_version()` and `AppUpdate.download_file()`).

**Step 2: Confirm `check_version()` function still exists in overlay.py**

Run a quick grep to verify:

```bash
grep -n "def check_version" src/overlay.py
```

Expected: `71:def check_version(update, version):` — the function is still present.

**Step 3: Confirm `__update_overlay_build()` method still exists in overlay.py**

```bash
grep -n "def __update_overlay_build" src/overlay.py
```

Expected: `3091:    def __update_overlay_build(self):` — the method is still present (just no longer called at startup).

---

## What's Preserved (Not Deleted)

| Component | Location | Status |
|-----------|----------|--------|
| `AppUpdate` class | `src/app_update.py` | Untouched |
| `check_version()` | `src/overlay.py:71-82` | Untouched |
| `__update_overlay_build()` | `src/overlay.py:3091-3127` | Untouched (just not called at startup) |
| `test_app_update.py` | `tests/test_app_update.py` | Untouched |
| `AppUpdate` import | `src/overlay.py:23` | Untouched |

## What Changes

| Change | Location | Description |
|--------|----------|-------------|
| Remove startup call | `src/overlay.py:565` | Replace `self.__update_overlay_build()` with `self.__arena_log_check()` and `self.__control_trace(True)` |
| New test | `tests/test_overlay.py` | Verifies startup does not trigger update check |
