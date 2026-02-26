# Card Data Column Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persist the Card Data window's 13 column visibility checkboxes across sessions by saving them to `config.json` when the window closes.

**Architecture:** Add a `CardDataSettings` Pydantic model to `configuration.py` and include it in `Configuration`. In `overlay.py`, initialize the 13 column `IntVar`s from saved config and write back on window close.

**Tech Stack:** Python, Pydantic v2, tkinter, pytest

---

### Task 1: Add `CardDataSettings` model to `configuration.py`

**Files:**
- Modify: `src/configuration.py:150-160`
- Test: `tests/test_configuration.py` (create if it doesn't exist)

**Step 1: Write the failing test**

Add to `tests/test_configuration.py`:

```python
from src.configuration import CardDataSettings, Configuration

def test_card_data_settings_defaults():
    s = CardDataSettings()
    assert s.col_rarity is True
    assert s.col_gihwr is True
    assert s.col_ohwr is False
    assert s.col_gpwr is False
    assert s.col_gnswr is False
    assert s.col_gdwr is False
    assert s.col_ata is True
    assert s.col_alsa is True
    assert s.col_iwd is False
    assert s.col_wheel is False
    assert s.col_colors is True
    assert s.col_ngp is False
    assert s.col_gih is False

def test_configuration_has_card_data_settings():
    config = Configuration()
    assert hasattr(config, "card_data_settings")
    assert isinstance(config.card_data_settings, CardDataSettings)
```

**Step 2: Run test to verify it fails**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_configuration.py::test_card_data_settings_defaults tests/test_configuration.py::test_configuration_has_card_data_settings -v
```

Expected: FAIL with `ImportError: cannot import name 'CardDataSettings'`

**Step 3: Write minimal implementation**

In `src/configuration.py`, insert after line 152 (the `CardData` class, before `Configuration`):

```python
class CardDataSettings(BaseModel):
    """Persisted column visibility state for the Card Data window."""
    col_rarity: bool = True
    col_gihwr: bool = True
    col_ohwr: bool = False
    col_gpwr: bool = False
    col_gnswr: bool = False
    col_gdwr: bool = False
    col_ata: bool = True
    col_alsa: bool = True
    col_iwd: bool = False
    col_wheel: bool = False
    col_colors: bool = True
    col_ngp: bool = False
    col_gih: bool = False
```

Then update the `Configuration` class (line 160) to add:

```python
card_data_settings: CardDataSettings = Field(default_factory=lambda: CardDataSettings())
```

**Step 4: Run test to verify it passes**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_configuration.py::test_card_data_settings_defaults tests/test_configuration.py::test_configuration_has_card_data_settings -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/configuration.py tests/test_configuration.py
git commit -m "feat: add CardDataSettings model for card data column persistence"
```

---

### Task 2: Initialize column `IntVar`s from saved config in `overlay.py`

**Files:**
- Modify: `src/overlay.py:412-424`
- Test: `tests/test_overlay.py`

**Step 1: Write the failing test**

The `IntVar`s are created during `Overlay.__init__`, which requires a live tkinter root. The existing test pattern uses `Overlay.__new__` to bypass `__init__`. Since testing tkinter `IntVar` initialization requires a root, test indirectly by verifying that a saved non-default config causes the expected `IntVar` initial value.

Add to `tests/test_overlay.py`:

```python
from src.configuration import Configuration, CardDataSettings

def test_card_data_intvars_initialized_from_config(mock_scanner):
    """Column IntVars should be initialized from saved CardDataSettings."""
    saved = CardDataSettings(
        col_gihwr=False,
        col_ata=False,
        col_alsa=False,
        col_ohwr=True,
    )
    config = Configuration()
    config.card_data_settings = saved

    with (
        patch("tkinter.Tk.mainloop", return_value=None),
        patch("tkinter.messagebox.showinfo", return_value=None),
        patch("src.overlay.stat", return_value=MagicMock(st_mtime=0)),
        patch("src.overlay.write_configuration", return_value=True),
        patch("src.overlay.read_configuration", return_value=(config, True)),
        patch("src.overlay.LimitedSets.retrieve_limited_sets", return_value=None),
        patch("src.overlay.AppUpdate.retrieve_file_version", return_value=("", "")),
        patch("src.overlay.ArenaScanner", return_value=mock_scanner),
        patch("src.overlay.FileExtractor", return_value=MagicMock()),
        patch("src.overlay.filter_options", return_value=["All Decks"]),
        patch("src.overlay.retrieve_arena_directory", return_value="fake_location"),
        patch("src.overlay.search_arena_log_locations", return_value="fake_location"),
    ):
        overlay = Overlay(step_through=True)

    assert overlay.card_data_gihwr_checkbox_value.get() == 0
    assert overlay.card_data_ata_checkbox_value.get() == 0
    assert overlay.card_data_alsa_checkbox_value.get() == 0
    assert overlay.card_data_ohwr_checkbox_value.get() == 1
```

**Step 2: Run test to verify it fails**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_card_data_intvars_initialized_from_config -v
```

Expected: FAIL (IntVars still show hardcoded defaults)

**Step 3: Write minimal implementation**

In `src/overlay.py`, replace lines 412–424 (the 13 column `IntVar` constructors) from:

```python
self.card_data_gihwr_checkbox_value = tkinter.IntVar(self.root, value=1)
self.card_data_ohwr_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_gpwr_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_gnswr_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_gdwr_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_ata_checkbox_value = tkinter.IntVar(self.root, value=1)
self.card_data_alsa_checkbox_value = tkinter.IntVar(self.root, value=1)
self.card_data_iwd_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_wheel_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_rarity_checkbox_value = tkinter.IntVar(self.root, value=1)
self.card_data_colors_checkbox_value = tkinter.IntVar(self.root, value=1)
self.card_data_ngp_checkbox_value = tkinter.IntVar(self.root, value=0)
self.card_data_gih_checkbox_value = tkinter.IntVar(self.root, value=0)
```

To:

```python
_cds = self.configuration.card_data_settings
self.card_data_gihwr_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_gihwr))
self.card_data_ohwr_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_ohwr))
self.card_data_gpwr_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_gpwr))
self.card_data_gnswr_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_gnswr))
self.card_data_gdwr_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_gdwr))
self.card_data_ata_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_ata))
self.card_data_alsa_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_alsa))
self.card_data_iwd_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_iwd))
self.card_data_wheel_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_wheel))
self.card_data_rarity_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_rarity))
self.card_data_colors_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_colors))
self.card_data_ngp_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_ngp))
self.card_data_gih_checkbox_value = tkinter.IntVar(self.root, value=int(_cds.col_gih))
```

Also add to the import in `overlay.py` (if not already present):

```python
from src.configuration import read_configuration, write_configuration, reset_configuration, DatasetSource
```

`CardDataSettings` does not need to be imported in `overlay.py` — it is accessed via `self.configuration.card_data_settings`.

**Step 4: Run test to verify it passes**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_card_data_intvars_initialized_from_config -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/overlay.py tests/test_overlay.py
git commit -m "feat: initialize card data column IntVars from saved CardDataSettings"
```

---

### Task 3: Save column state on window close in `overlay.py`

**Files:**
- Modify: `src/overlay.py:2787-2796`
- Test: `tests/test_overlay.py`

**Step 1: Write the failing test**

Add to `tests/test_overlay.py`:

```python
def test_close_card_data_window_saves_column_state():
    """Closing the Card Data window should persist column checkbox values to configuration."""
    overlay = Overlay.__new__(Overlay)
    overlay.configuration = MagicMock()
    overlay.configuration.card_data_settings = MagicMock()
    overlay._card_data_trace_ids = []
    overlay.card_data_table = MagicMock()

    # Set up IntVars (need a root for tkinter)
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    overlay.card_data_rarity_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gihwr_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_ohwr_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_gpwr_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gnswr_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gdwr_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_ata_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_alsa_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_iwd_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_wheel_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_colors_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_ngp_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gih_checkbox_value = tkinter.IntVar(root, value=0)

    popup = MagicMock()

    with patch("src.overlay.write_configuration") as mock_write:
        overlay._Overlay__close_card_data_window(popup)

    cds = overlay.configuration.card_data_settings
    assert cds.col_rarity is False
    assert cds.col_gihwr is True
    assert cds.col_ohwr is True
    assert cds.col_ata is False
    assert cds.col_alsa is False
    assert cds.col_iwd is True
    assert cds.col_colors is True
    mock_write.assert_called_once_with(overlay.configuration)

    root.destroy()
```

**Step 2: Run test to verify it fails**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_close_card_data_window_saves_column_state -v
```

Expected: FAIL (`mock_write` not called, attributes not set)

**Step 3: Write minimal implementation**

In `src/overlay.py`, replace `__close_card_data_window` (lines 2787–2796):

```python
def __close_card_data_window(self, popup):
    '''Clear card data table and remove active traces when the Card Data window is closed'''
    for var, tid in self._card_data_trace_ids:
        try:
            var.trace_remove("write", tid)
        except Exception:
            pass
    self._card_data_trace_ids = []
    self.card_data_table = None

    cds = self.configuration.card_data_settings
    cds.col_rarity = bool(self.card_data_rarity_checkbox_value.get())
    cds.col_gihwr = bool(self.card_data_gihwr_checkbox_value.get())
    cds.col_ohwr = bool(self.card_data_ohwr_checkbox_value.get())
    cds.col_gpwr = bool(self.card_data_gpwr_checkbox_value.get())
    cds.col_gnswr = bool(self.card_data_gnswr_checkbox_value.get())
    cds.col_gdwr = bool(self.card_data_gdwr_checkbox_value.get())
    cds.col_ata = bool(self.card_data_ata_checkbox_value.get())
    cds.col_alsa = bool(self.card_data_alsa_checkbox_value.get())
    cds.col_iwd = bool(self.card_data_iwd_checkbox_value.get())
    cds.col_wheel = bool(self.card_data_wheel_checkbox_value.get())
    cds.col_colors = bool(self.card_data_colors_checkbox_value.get())
    cds.col_ngp = bool(self.card_data_ngp_checkbox_value.get())
    cds.col_gih = bool(self.card_data_gih_checkbox_value.get())
    write_configuration(self.configuration)

    popup.destroy()
```

**Step 4: Run test to verify it passes**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_close_card_data_window_saves_column_state -v
```

Expected: PASS

**Step 5: Run full test suite**

```
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v
```

Expected: All tests pass

**Step 6: Commit**

```bash
git add src/overlay.py tests/test_overlay.py
git commit -m "feat: save card data column visibility to config on window close"
```
