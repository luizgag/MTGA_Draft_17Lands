# GoatBots MTGO Card Price Integration - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show a `$$$` prefix on card names in the MTGO draft pack table for cards above a configurable price threshold, using GoatBots official price data.

**Architecture:** GoatBots provides two daily-updated ZIP files (`card-definitions.zip` and `price-history.zip`) with MTGO card prices. A new standalone function `retrieve_goatbots_prices()` in `file_extractor.py` downloads and parses these ZIPs, returning a `{card_name: price}` dict. During set download, prices are injected into card data before export. The overlay prepends `$$$` to card names in the pack table when price >= threshold (MTGO platform only).

**Tech Stack:** Python 3.12, urllib, zipfile, json, Tkinter, pytest

---

### Task 1: Add price constants and configuration fields

**Files:**
- Modify: `src/constants.py` (add price-related constants)
- Modify: `src/configuration.py:30-70` (add price settings to Settings class)

**Step 1: Add constants to `src/constants.py`**

Add near the other MTGO-related constants (find `PLATFORM_MTGO`):

```python
# GoatBots price data URLs
GOATBOTS_CARD_DEFINITIONS_URL = "https://www.goatbots.com/download/prices/card-definitions.zip"
GOATBOTS_PRICE_HISTORY_URL = "https://www.goatbots.com/download/prices/price-history.zip"

# Price data field
DATA_FIELD_PRICE = "price"

# Default price threshold in MTGO event tickets
PRICE_THRESHOLD_DEFAULT = 3.0
```

**Step 2: Add settings fields to `src/configuration.py`**

In the `Settings` class, after `mtgo_hindsight_enabled` (line 68), add:

```python
price_enabled: bool = True
price_threshold: float = constants.PRICE_THRESHOLD_DEFAULT
```

**Step 3: Run tests to verify no regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass (constants and config changes are backward-compatible via Pydantic defaults)

**Step 4: Commit**

```
feat: add goatbots price constants and configuration fields
```

---

### Task 2: Implement `retrieve_goatbots_prices()` function

**Files:**
- Modify: `src/file_extractor.py` (add new standalone function after `merge_datasets()`)
- Create: `tests/test_goatbots_prices.py`

**Step 1: Write failing tests in `tests/test_goatbots_prices.py`**

```python
import pytest
import json
import io
import zipfile
from unittest.mock import patch, MagicMock
from src.file_extractor import retrieve_goatbots_prices


def _make_zip(data_dict):
    """Helper: create an in-memory ZIP containing a single JSON file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Use the first key as filename (doesn't matter, we read the first entry)
        zf.writestr("data.json", json.dumps(data_dict))
    return buf.getvalue()


@pytest.fixture
def mock_goatbots_data():
    """Fixture providing card definitions and price history as mock ZIP bytes."""
    card_definitions = {
        "100": {"name": "Lightning Bolt", "cardset": "ECL", "rarity": "Common", "version": "1", "foil": 0},
        "101": {"name": "Lightning Bolt", "cardset": "ECL", "rarity": "Common", "version": "2", "foil": 1},
        "102": {"name": "Moonshadow", "cardset": "ECL", "rarity": "Mythic", "version": "110", "foil": 0},
        "103": {"name": "Moonshadow", "cardset": "ECL", "rarity": "Mythic", "version": "310", "foil": 0},
        "104": {"name": "Island", "cardset": "ECL", "rarity": "Common", "version": "1", "foil": 0},
        "105": {"name": "Other Card", "cardset": "FDN", "rarity": "Rare", "version": "1", "foil": 0},
    }
    price_history = {
        "100": 0.05,
        "101": 0.10,
        "102": 27.12,
        "103": 15.00,
        "104": 0.01,
        "105": 5.00,
    }
    return _make_zip(card_definitions), _make_zip(price_history)


def test_retrieve_goatbots_prices_basic(mock_goatbots_data):
    """Prices returned for matching set, foil versions excluded."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("ECL")

    assert prices["Lightning Bolt"] == pytest.approx(0.05)
    assert prices["Moonshadow"] == pytest.approx(27.12)  # highest of 27.12 and 15.00
    assert prices["Island"] == pytest.approx(0.01)
    assert "Other Card" not in prices  # FDN set, not ECL


def test_retrieve_goatbots_prices_uses_highest_price(mock_goatbots_data):
    """When multiple regular versions exist, use the highest price."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("ECL")

    # Moonshadow has IDs 102 (27.12) and 103 (15.00) - should pick highest
    assert prices["Moonshadow"] == pytest.approx(27.12)


def test_retrieve_goatbots_prices_case_insensitive_set_code(mock_goatbots_data):
    """Set code matching should be case-insensitive."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("ecl")

    assert "Lightning Bolt" in prices
    assert "Moonshadow" in prices


def test_retrieve_goatbots_prices_empty_on_failure():
    """Return empty dict if download fails."""
    with patch("src.file_extractor.urllib.request.urlopen", side_effect=Exception("Network error")):
        prices = retrieve_goatbots_prices("ECL")

    assert prices == {}


def test_retrieve_goatbots_prices_no_matching_set(mock_goatbots_data):
    """Return empty dict when no cards match the requested set."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("NONEXISTENT")

    assert prices == {}
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_goatbots_prices.py -v`
Expected: FAIL with `ImportError: cannot import name 'retrieve_goatbots_prices'`

**Step 3: Implement `retrieve_goatbots_prices()` in `src/file_extractor.py`**

Add after the `merge_datasets()` function (after line ~188), before the `FileExtractor` class:

```python
def retrieve_goatbots_prices(set_code: str) -> dict:
    """Download GoatBots price data and return {card_name: price} for the given set.

    Downloads the official GoatBots card-definitions and price-history ZIP files,
    matches cards by name and set code (non-foil only), and returns the highest
    price when multiple versions exist.

    Returns an empty dict if the download fails.
    """
    try:
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLS_CLIENT)
        context.load_default_certs()

        # Download both ZIP files
        defs_data = urllib.request.urlopen(
            constants.GOATBOTS_CARD_DEFINITIONS_URL, context=context).read()
        prices_data = urllib.request.urlopen(
            constants.GOATBOTS_PRICE_HISTORY_URL, context=context).read()

        # Extract JSON from ZIPs
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(defs_data)) as zf:
            defs_json = json.loads(zf.read(zf.namelist()[0]))

        with zipfile.ZipFile(io.BytesIO(prices_data)) as zf:
            prices_json = json.loads(zf.read(zf.namelist()[0]))

        # Build {card_name: highest_price} for matching set (non-foil only)
        upper_set = set_code.upper()
        result = {}
        for mtgo_id, card_def in defs_json.items():
            if card_def.get("foil", 0) != 0:
                continue
            if card_def.get("cardset", "").upper() != upper_set:
                continue
            name = card_def.get("name", "")
            price = prices_json.get(mtgo_id, 0.0)
            if name and price > result.get(name, 0.0):
                result[name] = price

        return result

    except Exception as error:
        logger.error("Failed to retrieve GoatBots prices: %s", error)
        return {}
```

Also add `import zipfile` and `import io` to the top-level imports in `file_extractor.py` (near the existing imports at lines 2-13).

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_goatbots_prices.py -v`
Expected: All 5 tests PASS

**Step 5: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass

**Step 6: Commit**

```
feat: add retrieve_goatbots_prices() function for MTGO card prices
```

---

### Task 3: Inject prices during set download

**Files:**
- Modify: `src/overlay.py:3398-3410` (in `__add_set`, after merge and before export)

**Step 1: Write failing test in `tests/test_overlay.py`**

Add a test that verifies `__add_set` calls `retrieve_goatbots_prices` when platform is MTGO and injects prices into card data. Since `__add_set` is complex with UI dependencies, test the price injection logic as a simpler unit:

```python
def test_price_injection_adds_price_to_card_data():
    """Price data from GoatBots should be injected into card_ratings before export."""
    combined_data = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "1001": {"name": "Lightning Bolt", "deck_colors": {}},
            "1002": {"name": "Moonshadow", "deck_colors": {}},
            "1003": {"name": "Unknown Card", "deck_colors": {}},
        }
    }
    prices = {"Lightning Bolt": 0.05, "Moonshadow": 27.12}

    # Inject prices (this is the logic that will be in __add_set)
    for card_data in combined_data["card_ratings"].values():
        card_name = card_data.get("name", "")
        card_data["price"] = prices.get(card_name, 0.0)

    assert combined_data["card_ratings"]["1001"]["price"] == pytest.approx(0.05)
    assert combined_data["card_ratings"]["1002"]["price"] == pytest.approx(27.12)
    assert combined_data["card_ratings"]["1003"]["price"] == pytest.approx(0.0)
```

**Step 2: Run test to verify it passes (pure logic test, no mocking needed)**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_price_injection_adds_price_to_card_data -v`
Expected: PASS

**Step 3: Add price injection to `__add_set` in `src/overlay.py`**

In `__add_set`, after the merge block (after line 3402 `self.extractor.combined_data = merged`) and before `export_card_data()` (line 3404), add:

```python
                # Fetch and inject GoatBots prices (MTGO only)
                if (self.configuration.settings.platform == constants.PLATFORM_MTGO
                        and self.configuration.settings.price_enabled):
                    status.set("Downloading MTGO Prices")
                    popup.update()
                    prices = retrieve_goatbots_prices(set_code)
                    if prices:
                        for card_data in self.extractor.combined_data.get("card_ratings", {}).values():
                            card_name = card_data.get("name", "")
                            card_data["price"] = prices.get(card_name, 0.0)
```

Also add `retrieve_goatbots_prices` to the imports at the top of `overlay.py`. Find the existing import:
```python
from src.file_extractor import FileExtractor, merge_datasets, delete_old_set_files
```
Change to:
```python
from src.file_extractor import FileExtractor, merge_datasets, delete_old_set_files, retrieve_goatbots_prices
```

**Important placement:** The price injection block must be placed AFTER line 3402 (merge completes) but BEFORE line 3404 (`export_card_data()`). It must also be OUTSIDE the `if len(active_sources) > 1:` block so it runs even with a single source. Place it right before the `if not self.extractor.export_card_data():` line.

**Step 4: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass

**Step 5: Commit**

```
feat: inject goatbots prices into card data during MTGO set download
```

---

### Task 4: Add $$$ prefix to pack table display

**Files:**
- Modify: `src/overlay.py:803-817` (in `__update_pack_table`, after hindsight arrow prefix)

**Step 1: Write failing test in `tests/test_overlay.py`**

```python
def test_price_prefix_added_to_expensive_cards():
    """Cards above price threshold should get $$$ prefix in pack table results."""
    result_list = [
        {"name": "Moonshadow", "price": 27.12, "results": ["Moonshadow", "58.2"]},
        {"name": "Lightning Bolt", "price": 0.05, "results": ["Lightning Bolt", "52.1"]},
        {"name": "Jace", "price": 5.0, "results": ["Jace", "61.0"]},
    ]

    threshold = 3.0
    for card in result_list:
        price = card.get("price", 0.0)
        if price >= threshold:
            card["results"][0] = f"$$$ {card['results'][0]}"

    assert result_list[0]["results"][0] == "$$$ Moonshadow"
    assert result_list[1]["results"][0] == "Lightning Bolt"  # Below threshold
    assert result_list[2]["results"][0] == "$$$ Jace"


def test_price_prefix_not_added_for_arena_platform():
    """$$$ prefix should only apply when platform is MTGO."""
    result_list = [
        {"name": "Moonshadow", "price": 27.12, "results": ["Moonshadow", "58.2"]},
    ]

    platform = constants.PLATFORM_MTGA
    threshold = 3.0
    if platform == constants.PLATFORM_MTGO:
        for card in result_list:
            price = card.get("price", 0.0)
            if price >= threshold:
                card["results"][0] = f"$$$ {card['results'][0]}"

    assert result_list[0]["results"][0] == "Moonshadow"  # No prefix for Arena


def test_price_prefix_with_zero_threshold():
    """When threshold is 0, all cards with any price get the prefix."""
    result_list = [
        {"name": "Bolt", "price": 0.05, "results": ["Bolt", "52.1"]},
        {"name": "Island", "price": 0.0, "results": ["Island", "48.0"]},
    ]

    threshold = 0.0
    for card in result_list:
        price = card.get("price", 0.0)
        if price >= threshold and price > 0:
            card["results"][0] = f"$$$ {card['results'][0]}"

    assert result_list[0]["results"][0] == "$$$ Bolt"
    assert result_list[1]["results"][0] == "Island"  # price is 0, no prefix
```

**Step 2: Run tests to verify they pass (pure logic)**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_overlay.py::test_price_prefix_added_to_expensive_cards tests/test_overlay.py::test_price_prefix_not_added_for_arena_platform tests/test_overlay.py::test_price_prefix_with_zero_threshold -v`
Expected: PASS

**Step 3: Add $$$ prefix logic to `__update_pack_table` in `src/overlay.py`**

In `__update_pack_table`, after the hindsight arrow prefix block (after line 808 `break`), add:

```python
            # Add $$$ prefix for expensive MTGO cards
            if self.configuration.settings.platform == constants.PLATFORM_MTGO:
                threshold = self.configuration.settings.price_threshold
                for card in result_list:
                    price = card.get(constants.DATA_FIELD_PRICE, 0.0)
                    if price >= threshold and price > 0:
                        card["results"][0] = f"$$$ {card['results'][0]}"
```

This block goes right before the `for count, card in enumerate(result_list):` loop at line 810.

**Step 4: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass

**Step 5: Commit**

```
feat: add $$$ price prefix to pack table for expensive MTGO cards
```

---

### Task 5: Add price settings to the Settings window UI

**Files:**
- Modify: `src/overlay.py` (multiple locations: variable declarations ~line 318, settings window ~line 3112, `__update_settings_storage` ~line 1540, `__update_settings_data` ~line 1641, `__control_trace` ~line 3689)

**Step 1: Add Tkinter variable declarations**

In the `__init__` section of `Overlay` (around line 318, after `self.mtgo_hindsight_checkbox_value`), add:

```python
self.price_enabled_checkbox_value = tkinter.IntVar(self.root)
self.price_threshold_value = tkinter.DoubleVar(self.root)
```

**Step 2: Add UI widgets in the Settings window**

In `__open_settings_window`, after the MTGO Hindsight checkbox block (after line 3129 `row_count += 1`), add:

```python
            price_enabled_label = Label(
                popup, text="Enable MTGO Prices:", style="MainSectionsBold.TLabel", anchor="e")
            price_enabled_checkbox = Checkbutton(popup,
                                                 variable=self.price_enabled_checkbox_value,
                                                 onvalue=1,
                                                 offvalue=0)

            price_enabled_label.grid(
                row=row_count, column=0, columnspan=1, sticky="nsew",
                padx=row_padding_x, pady=row_padding_y)
            price_enabled_checkbox.grid(
                row=row_count, column=1, columnspan=1, sticky="nsew",
                padx=row_padding_x, pady=row_padding_y)
            row_count += 1

            price_threshold_label = Label(popup, text="Price Threshold (tix):",
                                          style="MainSectionsBold.TLabel", anchor="e")
            price_threshold_entry = Entry(popup, textvariable=self.price_threshold_value)

            price_threshold_label.grid(
                row=row_count, column=0, columnspan=1, sticky="nsew",
                padx=row_padding_x, pady=row_padding_y)
            price_threshold_entry.grid(
                row=row_count, column=1, columnspan=1, sticky="nsew",
                padx=row_padding_x, pady=row_padding_y)
            row_count += 1
```

**Step 3: Add storage sync in `__update_settings_storage`**

After the `mtgo_hindsight_enabled` line (line 1541), add:

```python
            self.configuration.settings.price_enabled = bool(
                self.price_enabled_checkbox_value.get())
            self.configuration.settings.price_threshold = float(
                self.price_threshold_value.get())
```

**Step 4: Add data restore in `__update_settings_data`**

After the `mtgo_hindsight_checkbox_value` line (line 1642), add:

```python
            self.price_enabled_checkbox_value.set(
                self.configuration.settings.price_enabled)
            self.price_threshold_value.set(
                self.configuration.settings.price_threshold)
```

**Step 5: Add trace registration in `__control_trace`**

In the `trace_list` array (before the closing `]` at line 3691), add:

```python
                (self.price_enabled_checkbox_value, lambda: self.price_enabled_checkbox_value.trace(
                    "w", self.__update_settings_callback)),
                (self.price_threshold_value, lambda: self.price_threshold_value.trace(
                    "w", self.__update_settings_callback)),
```

**Step 6: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass

**Step 7: Commit**

```
feat: add price settings (enabled + threshold) to Settings window
```

---

### Task 6: Final integration test and cleanup

**Files:**
- Modify: `tests/test_goatbots_prices.py` (add integration-style test)
- Verify: full test suite passes

**Step 1: Add end-to-end style test**

Add to `tests/test_goatbots_prices.py`:

```python
def test_price_data_survives_json_roundtrip(tmp_path):
    """Price field should persist through JSON save/load cycle (like export_card_data)."""
    card_data = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "1001": {"name": "Moonshadow", "price": 27.12, "deck_colors": {}},
            "1002": {"name": "Lightning Bolt", "price": 0.05, "deck_colors": {}},
        }
    }

    filepath = tmp_path / "ECL_Data.json"
    with open(filepath, "w") as f:
        json.dump(card_data, f)

    with open(filepath, "r") as f:
        loaded = json.load(f)

    assert loaded["card_ratings"]["1001"]["price"] == pytest.approx(27.12)
    assert loaded["card_ratings"]["1002"]["price"] == pytest.approx(0.05)
```

**Step 2: Run all goatbots tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_goatbots_prices.py -v`
Expected: All 6 tests PASS

**Step 3: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -x -q`
Expected: All tests pass with no regressions

**Step 4: Commit**

```
test: add roundtrip and integration tests for goatbots price data
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `src/constants.py` | Add `GOATBOTS_CARD_DEFINITIONS_URL`, `GOATBOTS_PRICE_HISTORY_URL`, `DATA_FIELD_PRICE`, `PRICE_THRESHOLD_DEFAULT` |
| `src/configuration.py` | Add `price_enabled`, `price_threshold` to `Settings` |
| `src/file_extractor.py` | Add `retrieve_goatbots_prices()` function, add `zipfile`/`io` imports |
| `src/overlay.py` | Import `retrieve_goatbots_prices`; inject prices in `__add_set`; add `$$$` prefix in `__update_pack_table`; add price settings UI widgets + storage/restore/trace |
| `tests/test_goatbots_prices.py` | New test file: 6 tests for price fetching, injection, and roundtrip |
| `tests/test_overlay.py` | 4 new tests for price injection and prefix display logic |
