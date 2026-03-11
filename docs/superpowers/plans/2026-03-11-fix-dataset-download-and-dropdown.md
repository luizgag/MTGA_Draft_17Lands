# Fix Dataset Download & Data Source Dropdown Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs: (1) Scryfall fallback broken because `scryfall` field is never populated, causing MTGO users to get incomplete card data; (2) Data Source dropdown only shows "Merged" instead of letting users select between downloaded sets.

**Architecture:** Populate the `scryfall` field during set configuration building so the Scryfall card-data fallback works. Modify `retrieve_data_sources()` in both scanners to show ALL downloaded datasets (not just current draft) with set-code labels. Add a new `retrieve_all_data_sources()` utility that queries the DB for all stored datasets.

**Tech Stack:** Python, SQLite, tkinter, pytest

---

## Chunk 1: Populate Scryfall codes in set configuration

### Task 1: Populate `scryfall` field in `__process_scryfall_sets`

**Files:**
- Modify: `src/limited_sets.py:335-338` (`__process_scryfall_sets`)
- Modify: `src/limited_sets.py:354-379` (`__process_scryfall_sets_alchemy`)
- Modify: `src/limited_sets.py:258-264` (`__append_limited_sets`)
- Test: `tests/test_limited_sets.py`

- [ ] **Step 1: Write failing test — scryfall codes populated for standard sets**

Add to `tests/test_limited_sets.py`:

```python
@patch("src.limited_sets.urllib.request.urlopen")
def test_scryfall_codes_populated_for_standard_sets(mock_urlopen, limited_sets):
    """Verify that standard sets have their Scryfall code populated after retrieve_limited_sets."""
    mock_urlopen.return_value.read.side_effect = [MOCK_URL_RESPONSE_17LANDS_FILTERS, MOCK_URL_RESPONSE_SCRYFALL_SETS]
    if os.path.exists(SETS_FILE_LOCATION):
        os.remove(SETS_FILE_LOCATION)

    output_sets = limited_sets.retrieve_limited_sets()

    # Standard sets (OTJ, WOE, MOM, etc.) should have scryfall codes from Scryfall API
    otj = output_sets.data["Outlaws of Thunder Junction"]
    assert otj.scryfall == ["otj"], f"Expected scryfall=['otj'], got {otj.scryfall}"

    woe = output_sets.data["Wilds of Eldraine"]
    assert woe.scryfall == ["woe"], f"Expected scryfall=['woe'], got {woe.scryfall}"

    one = output_sets.data["Phyrexia: All Will Be One"]
    assert one.scryfall == ["one"], f"Expected scryfall=['one'], got {one.scryfall}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_limited_sets.py::test_scryfall_codes_populated_for_standard_sets -v`
Expected: FAIL — scryfall is `[]` for all sets

- [ ] **Step 3: Write failing test — scryfall codes populated for alchemy sets**

Add to `tests/test_limited_sets.py`:

```python
@patch("src.limited_sets.urllib.request.urlopen")
def test_scryfall_codes_populated_for_alchemy_sets(mock_urlopen, limited_sets):
    """Verify that alchemy sets have their Scryfall code populated."""
    mock_urlopen.return_value.read.side_effect = [MOCK_URL_RESPONSE_17LANDS_FILTERS, MOCK_URL_RESPONSE_SCRYFALL_SETS]
    if os.path.exists(SETS_FILE_LOCATION):
        os.remove(SETS_FILE_LOCATION)

    output_sets = limited_sets.retrieve_limited_sets()

    alchemy_one = output_sets.data["Alchemy: Phyrexia"]
    assert alchemy_one.scryfall == ["yone"], f"Expected scryfall=['yone'], got {alchemy_one.scryfall}"

    alchemy_bro = output_sets.data["Alchemy: The Brothers' War"]
    assert alchemy_bro.scryfall == ["ybro"], f"Expected scryfall=['ybro'], got {alchemy_bro.scryfall}"
```

- [ ] **Step 4: Run test to verify it fails**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_limited_sets.py::test_scryfall_codes_populated_for_alchemy_sets -v`
Expected: FAIL — scryfall is `[]`

- [ ] **Step 5: Implement — populate scryfall in `__process_scryfall_sets`**

In `src/limited_sets.py:335-338`, change:

```python
# OLD (line 335-338)
                    else:
                        self.sets_scryfall.data[set_name] = SetInfo(
                            arena=[constants.SET_SELECTION_ALL],
                            seventeenlands=[set_code.upper()]
                        )
```

to:

```python
# NEW
                    else:
                        self.sets_scryfall.data[set_name] = SetInfo(
                            arena=[constants.SET_SELECTION_ALL],
                            scryfall=[set_code],
                            seventeenlands=[set_code.upper()]
                        )
```

- [ ] **Step 6: Implement — populate scryfall in `__process_scryfall_sets_alchemy`**

In `src/limited_sets.py`, update all SetInfo constructions in `__process_scryfall_sets_alchemy` to include `scryfall=[set_code]`.

For line 356-360 (first branch):
```python
        set_entry = SetInfo()
        if ("parent_set_code" in data) and ("block_code" in data):
            set_entry.arena = [constants.SET_SELECTION_ALL]
            set_entry.scryfall = [set_code]
            set_entry.seventeenlands = [
                f"{data['block_code'].upper()}{data['parent_set_code'].upper()}"]
```

For line 366-369 (second branch):
```python
            if parent_code:
                set_entry.arena = [constants.SET_SELECTION_ALL]
                set_entry.scryfall = [set_code]
                set_entry.seventeenlands = [
                    f"{data['block_code'].upper()}{parent_code[0].upper()}"]
```

For line 372-375 (else of second branch):
```python
            else:
                set_entry = SetInfo(
                    arena=[constants.SET_SELECTION_ALL],
                    scryfall=[set_code],
                    seventeenlands=[set_code.upper()]
                )
```

For line 377-378 (final else):
```python
        else:
            set_entry = SetInfo(
                arena=[constants.SET_SELECTION_ALL],
                scryfall=[set_code],
                seventeenlands=[set_code.upper()]
            )
```

- [ ] **Step 7: Implement — preserve scryfall codes during merge in `__append_limited_sets`**

In `src/limited_sets.py:258-264`, when a scryfall set matches a 17lands set, copy the scryfall codes from the scryfall SetInfo to the 17lands SetInfo before storing it.

Change lines 258-264:
```python
# OLD
            for set_name, set_fields in self.sets_scryfall.data.items():
                set_code = set_fields.seventeenlands[0]
                if set_code in self.sets_17lands.data:
                    if re.match(r"^Y\d{2}[A-Za-z]{3}$", set_code):
                        alchemy_sets[set_name] = self.sets_17lands.data[set_code]
                    else:
                        temp_dict.data[set_name] = self.sets_17lands.data[set_code]
                    set_codes_to_remove.append(set_code)
```

to:
```python
# NEW
            for set_name, set_fields in self.sets_scryfall.data.items():
                set_code = set_fields.seventeenlands[0]
                if set_code in self.sets_17lands.data:
                    merged_info = self.sets_17lands.data[set_code]
                    if set_fields.scryfall:
                        merged_info.scryfall = set_fields.scryfall
                    if re.match(r"^Y\d{2}[A-Za-z]{3}$", set_code):
                        alchemy_sets[set_name] = merged_info
                    else:
                        temp_dict.data[set_name] = merged_info
                    set_codes_to_remove.append(set_code)
```

- [ ] **Step 8: Run both new tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_limited_sets.py::test_scryfall_codes_populated_for_standard_sets tests/test_limited_sets.py::test_scryfall_codes_populated_for_alchemy_sets -v`
Expected: PASS

- [ ] **Step 9: Update existing test expectations**

Update `CHECKED_SETS_COMBINED` and `CHECKED_SETS_SCRYFALL` in `tests/test_limited_sets.py` to include the scryfall codes where appropriate. Standard sets that appear in the mock Scryfall response need `scryfall=["<lowercase_code>"]`. Sets that DON'T appear in the Scryfall response (like CORE, cube-only sets from 17Lands) keep `scryfall=[]`.

Sets that appear in `MOCK_URL_RESPONSE_SCRYFALL_SETS` and need scryfall codes in `CHECKED_SETS_COMBINED`:
- "Through the Omenpaths": `scryfall=["om1"]`
- "Outlaws of Thunder Junction": `scryfall=["otj"]`
- "Wilds of Eldraine": `scryfall=["woe"]`
- "March of the Machine": `scryfall=["mom"]`
- "March of the Machine: The Aftermath": `scryfall=["mat"]`
- "Shadows over Innistrad Remastered": `scryfall=["sir"]`
- "Phyrexia: All Will Be One": `scryfall=["one"]`
- "Alchemy: Phyrexia": `scryfall=["yone"]`
- "The Brothers' War": `scryfall=["bro"]`
- "Alchemy: The Brothers' War": `scryfall=["ybro"]`

Same updates for `CHECKED_SETS_SCRYFALL`.

CORE remains `scryfall=[]` because it's 17Lands-only (not in the Scryfall mock response).

- [ ] **Step 10: Run full limited_sets test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_limited_sets.py -v`
Expected: ALL PASS

- [ ] **Step 11: Commit**

```bash
git add src/limited_sets.py tests/test_limited_sets.py
git commit -m "fix: populate scryfall codes in set configuration for Scryfall fallback"
```

---

## Chunk 2: Show all downloaded sets in Data Source dropdown

### Task 2: Add `retrieve_all_local_sets` utility function

**Files:**
- Modify: `src/utils.py:69-121`
- Test: `tests/test_utils.py` (or wherever utils tests live)

- [ ] **Step 1: Write failing test for `retrieve_all_local_sets`**

Add to the appropriate test file (create `tests/test_utils_sets.py` if needed):

```python
import pytest
import src.database as database
from src.utils import retrieve_all_local_sets


@pytest.fixture
def db_with_two_sets(tmp_path):
    """Create a temp DB with two datasets."""
    db_path = str(tmp_path / "test.db")
    database.save_dataset("ECL", {
        "meta": {"collection_date": "2026-02-28", "start_date": "2026-01-20",
                 "end_date": "2026-02-28", "version": 3.0, "game_count": 100000},
        "color_ratings": {"WU": 55.0},
        "card_ratings": {
            "1001": {"name": "TestCard", "cmc": 2, "mana_cost": "{1}{W}",
                     "isprimarycard": 1, "linkedfacetype": 0, "rarity": "common",
                     "colors": ["W"], "types": ["Creature"], "image": [],
                     "deck_colors": {"All Decks": {"gihwr": 55.0, "ohwr": 54.0,
                                                    "gpwr": 53.0, "gnswr": 52.0,
                                                    "gdwr": 51.0, "alsa": 5.0,
                                                    "ata": 4.0, "iwd": 3.0,
                                                    "ngp": 100, "ngoh": 50,
                                                    "gih": 80, "ngnd": 30,
                                                    "ngd": 20}}}
        },
    }, db_path)
    database.save_dataset("TMT", {
        "meta": {"collection_date": "2026-03-11", "start_date": "2026-03-03",
                 "end_date": "2026-03-11", "version": 3.0, "game_count": 50000},
        "color_ratings": {"BR": 52.0},
        "card_ratings": {},
    }, db_path)
    return db_path


def test_retrieve_all_local_sets_returns_all(db_with_two_sets):
    """Should return entries for ALL sets in the DB, not filtered."""
    file_list, error_list = retrieve_all_local_sets(db_path=db_with_two_sets)
    assert len(error_list) == 0
    set_codes = [f[0] for f in file_list]
    assert "ECL" in set_codes
    assert "TMT" in set_codes


def test_retrieve_all_local_sets_tuple_structure(db_with_two_sets):
    """Each entry should be a 7-tuple matching retrieve_local_set_list format."""
    file_list, _ = retrieve_all_local_sets(db_path=db_with_two_sets)
    for entry in file_list:
        assert len(entry) == 7
        set_name, event_type, user_group, start_date, end_date, game_count, file_location = entry
        assert event_type == ""
        assert user_group == ""
        assert isinstance(game_count, int)
        assert file_location.endswith("_Data.json")


def test_retrieve_all_local_sets_empty_db(tmp_path):
    """Should return empty list for empty DB."""
    db_path = str(tmp_path / "empty.db")
    file_list, error_list = retrieve_all_local_sets(db_path=db_path)
    assert file_list == []
    assert error_list == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_utils_sets.py -v`
Expected: FAIL — `ImportError: cannot import name 'retrieve_all_local_sets'`

- [ ] **Step 3: Implement `retrieve_all_local_sets`**

Add to `src/utils.py` after the `retrieve_local_set_list` function (after line 121):

```python
def retrieve_all_local_sets(db_path=None):
    '''Returns a list of ALL datasets from the SQLite database (no filtering).

    Each entry is a tuple matching retrieve_local_set_list format:
        (set_name, event_type, user_group, start_date, end_date, game_count, file_location)
    '''
    import src.database as database

    file_list = []
    error_list = []

    try:
        all_meta = database.list_datasets_with_meta(db_path)
    except Exception as error:
        error_list.append(error)
        return file_list, error_list

    for row in all_meta:
        try:
            set_code = row["set_code"]
            start_date = row.get("start_date", "")
            end_date = row.get("end_date", "")
            game_count = int(row.get("game_count", 0) or 0)
            file_location = os.path.join(SETS_FOLDER, f"{set_code}_{SET_FILE_SUFFIX}")

            file_list.append((
                set_code,
                "",       # event_type — always empty for merged DB entries
                "",       # user_group — always empty for merged DB entries
                start_date,
                end_date,
                game_count,
                file_location,
            ))
        except Exception as error:
            error_list.append(error)

    return file_list, error_list
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_utils_sets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils.py tests/test_utils_sets.py
git commit -m "feat: add retrieve_all_local_sets to query all DB datasets unfiltered"
```

### Task 3: Update `retrieve_data_sources` in MtgoScanner to show all sets

**Files:**
- Modify: `src/mtgo_scanner.py:242-287`
- Test: `tests/test_mtgo_scanner.py`

- [ ] **Step 1: Write failing test — dropdown shows all downloaded sets with labels**

Add to `tests/test_mtgo_scanner.py`:

```python
import src.database as database


@pytest.fixture
def db_with_sets(tmp_path):
    """Create a temp DB with ECL and TMT datasets."""
    db_path = str(tmp_path / "test.db")
    database.save_dataset("ECL", {
        "meta": {"collection_date": "2026-02-28", "start_date": "2026-01-20",
                 "end_date": "2026-02-28", "version": 3.0, "game_count": 100000},
        "color_ratings": {},
        "card_ratings": {},
    }, db_path)
    database.save_dataset("TMT", {
        "meta": {"collection_date": "2026-03-11", "start_date": "2026-03-03",
                 "end_date": "2026-03-11", "version": 3.0, "game_count": 50000},
        "color_ratings": {},
        "card_ratings": {},
    }, db_path)
    return db_path


class TestRetrieveDataSourcesAllSets:
    """Test that retrieve_data_sources shows all downloaded sets."""

    def test_shows_all_sets_not_just_current_draft(self, scanner_with_folder, db_with_sets):
        """After downloading ECL and TMT, both should appear in data sources."""
        scanner_with_folder.draft_start_search()
        sources = scanner_with_folder.retrieve_data_sources(db_path=db_with_sets)
        assert isinstance(sources, dict)
        # Should have entries for both ECL and TMT
        labels = list(sources.keys())
        ecl_labels = [l for l in labels if "ECL" in l]
        tmt_labels = [l for l in labels if "TMT" in l]
        assert len(ecl_labels) >= 1, f"ECL not found in labels: {labels}"
        assert len(tmt_labels) >= 1, f"TMT not found in labels: {labels}"

    def test_current_draft_set_listed_first(self, scanner_with_folder, db_with_sets):
        """The current draft's set should be the first entry."""
        scanner_with_folder.draft_start_search()
        sources = scanner_with_folder.retrieve_data_sources(db_path=db_with_sets)
        first_label = next(iter(sources))
        assert "ECL" in first_label, f"Expected ECL first, got: {first_label}"

    def test_no_draft_still_shows_all_sets(self, db_with_sets):
        """Even without a detected draft, all downloaded sets should appear."""
        scanner = MtgoScanner(TEST_EXAMPLES_DIR, TEST_SETS)
        # Don't call draft_start_search — no draft detected
        sources = scanner.retrieve_data_sources(db_path=db_with_sets)
        labels = list(sources.keys())
        ecl_labels = [l for l in labels if "ECL" in l]
        tmt_labels = [l for l in labels if "TMT" in l]
        assert len(ecl_labels) >= 1, f"ECL not found in labels: {labels}"
        assert len(tmt_labels) >= 1, f"TMT not found in labels: {labels}"

    def test_empty_db_returns_none_source(self, tmp_path):
        """With no datasets in DB, should return DATA_SOURCES_NONE."""
        from src import constants
        db_path = str(tmp_path / "empty.db")
        scanner = MtgoScanner(TEST_EXAMPLES_DIR, TEST_SETS)
        sources = scanner.retrieve_data_sources(db_path=db_path)
        assert sources == constants.DATA_SOURCES_NONE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_mtgo_scanner.py::TestRetrieveDataSourcesAllSets -v`
Expected: FAIL — `TypeError: retrieve_data_sources() got an unexpected keyword argument 'db_path'`

- [ ] **Step 3: Implement — rewrite `retrieve_data_sources` in MtgoScanner**

Replace `src/mtgo_scanner.py:242-287` with:

```python
    def retrieve_data_sources(self, db_path=None):
        '''Return a dict of all downloaded datasets, with the current draft's set listed first.

        Label format is always "[SET_CODE] Merged" so users can distinguish
        between different downloaded sets in the dropdown.
        '''
        from src.utils import retrieve_all_local_sets

        data_sources = {}

        try:
            file_list, error_list = retrieve_all_local_sets(db_path=db_path)

            for error_string in error_list:
                logger.error(error_string)

            if file_list:
                # Two stable sorts: first by end_date descending, then current draft first
                current_sets = set(self.draft_sets) if self.draft_sets else set()
                file_list.sort(key=lambda x: x[4], reverse=True)
                file_list.sort(key=lambda x: x[0] not in current_sets)

            for file in file_list:
                set_code = file[0]
                location = file[6]
                type_string = f"[{set_code}] Merged"
                data_sources[type_string] = location

        except Exception as error:
            logger.error(error)

        if not data_sources:
            data_sources = constants.DATA_SOURCES_NONE

        return data_sources
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_mtgo_scanner.py::TestRetrieveDataSourcesAllSets -v`
Expected: PASS

- [ ] **Step 5: Run full MTGO scanner test suite to check for regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_mtgo_scanner.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/mtgo_scanner.py tests/test_mtgo_scanner.py
git commit -m "fix: show all downloaded sets in MTGO Data Source dropdown with set-code labels"
```

### Task 4: Update `retrieve_data_sources` in ArenaScanner (log_scanner.py)

**Files:**
- Modify: `src/log_scanner.py:995-1052`
- Test: `tests/test_log_scanner.py`

- [ ] **Step 1: Write failing tests — Arena scanner also shows all sets**

Add to `tests/test_log_scanner.py`:

```python
import src.database as database


@pytest.fixture
def db_with_sets(tmp_path):
    """Create a temp DB with two datasets."""
    db_path = str(tmp_path / "test.db")
    database.save_dataset("ECL", {
        "meta": {"collection_date": "2026-02-28", "start_date": "2026-01-20",
                 "end_date": "2026-02-28", "version": 3.0, "game_count": 100000},
        "color_ratings": {},
        "card_ratings": {},
    }, db_path)
    database.save_dataset("TMT", {
        "meta": {"collection_date": "2026-03-11", "start_date": "2026-03-03",
                 "end_date": "2026-03-11", "version": 3.0, "game_count": 50000},
        "color_ratings": {},
        "card_ratings": {},
    }, db_path)
    return db_path


class TestRetrieveDataSourcesAllSets:
    """Test that retrieve_data_sources shows all downloaded sets."""

    def test_shows_all_sets_when_no_draft(self, db_with_sets):
        """Without a draft, all downloaded sets should still appear."""
        from src import constants
        scanner = ArenaScanner(TEST_LOG_FILE_LOCATION, TEST_SETS, sets_location=TEST_SETS_DIRECTORY)
        sources = scanner.retrieve_data_sources(db_path=db_with_sets)
        labels = list(sources.keys())
        ecl_labels = [l for l in labels if "ECL" in l]
        tmt_labels = [l for l in labels if "TMT" in l]
        assert len(ecl_labels) >= 1, f"ECL not found in labels: {labels}"
        assert len(tmt_labels) >= 1, f"TMT not found in labels: {labels}"

    def test_empty_db_returns_none_source(self, tmp_path):
        """With no datasets in DB, should return DATA_SOURCES_NONE."""
        from src import constants
        db_path = str(tmp_path / "empty.db")
        scanner = ArenaScanner(TEST_LOG_FILE_LOCATION, TEST_SETS, sets_location=TEST_SETS_DIRECTORY)
        sources = scanner.retrieve_data_sources(db_path=db_path)
        assert sources == constants.DATA_SOURCES_NONE

    def test_labels_include_set_code(self, db_with_sets):
        """Each label should include the set code for identification."""
        scanner = ArenaScanner(TEST_LOG_FILE_LOCATION, TEST_SETS, sets_location=TEST_SETS_DIRECTORY)
        sources = scanner.retrieve_data_sources(db_path=db_with_sets)
        for label in sources:
            if label == "None":
                continue
            assert "[" in label and "]" in label, f"Label missing set code bracket format: {label}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_log_scanner.py::TestRetrieveDataSourcesAllSets -v`
Expected: FAIL

- [ ] **Step 3: Implement — rewrite `retrieve_data_sources` in ArenaScanner**

Replace `src/log_scanner.py:995-1052` with the same pattern as the MTGO scanner:

```python
    def retrieve_data_sources(self, db_path=None):
        '''Return a dict of all downloaded datasets, with the current draft's set listed first.'''
        from src.utils import retrieve_all_local_sets

        data_sources = {}

        try:
            file_list, error_list = retrieve_all_local_sets(db_path=db_path)

            for error_string in error_list:
                logger.error(error_string)

            if file_list:
                # Build set of current draft's cleaned set codes
                current_sets = set()
                if self.draft_type != constants.LIMITED_TYPE_UNKNOWN and self.draft_sets:
                    for s in self.draft_sets:
                        current_sets.add(s.upper())
                    for x in self.set_list.data.values():
                        if x.set_code in self.draft_sets:
                            current_sets.add(x.seventeenlands[0].upper())

                # Sort: current draft set first, then newest end_date
                file_list.sort(key=lambda x: x[4], reverse=True)
                file_list.sort(key=lambda x: x[0].upper() not in current_sets)

            for file in file_list:
                set_code = file[0]
                location = file[6]
                type_string = f"[{set_code}] Merged"
                data_sources[type_string] = location

        except Exception as error:
            logger.error(error)

        if not data_sources:
            data_sources = constants.DATA_SOURCES_NONE

        return data_sources
```

- [ ] **Step 4: Run test to verify it passes**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_log_scanner.py::TestRetrieveDataSourcesAllSets -v`
Expected: PASS

- [ ] **Step 5: Update callers — pass db_path=None at call sites**

The existing call sites in `overlay.py` (lines 261, 1437, 2161) call `self.draft.retrieve_data_sources()` with no args. Since `db_path` defaults to `None`, no changes needed at call sites.

- [ ] **Step 6: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/log_scanner.py tests/test_log_scanner.py
git commit -m "fix: show all downloaded sets in Arena Data Source dropdown with set-code labels"
```
