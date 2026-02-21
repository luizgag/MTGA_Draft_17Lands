# Merge Datasets Game-Count Weighting — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `merge_datasets` so that win rates are weighted by actual game counts (not user weights), the meta `game_count` reflects all sources, and `iwd` is correctly derived as `GIHWR − GNSWR`.

**Architecture:** Pure logic fixes to `_merge_color_ratings`, `_merge_deck_colors`, and `merge_datasets`. Remove `weights` param from `merge_datasets`; callers filter by `source.enabled`. `DatasetSource.weight` → `enabled: bool` with backward-compat Pydantic validator.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, src/file_extractor.py, src/configuration.py, src/overlay.py, tests/test_file_extractor.py, tests/test_configuration.py

**Test runner (WSL):** `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest <test-path> -v`
If Xvfb is already running, the "Server is already active" error is harmless.

---

## Key Context

### Rate field → count field mapping (from `constants.py`)
```python
WIN_RATE_FIELDS_DICT = {
    "gihwr": "gih",    # Games in hand win rate  → weighted by gih
    "ohwr": "ngoh",    # Opening hand win rate   → weighted by ngoh
    "gpwr": "ngp",     # Games played win rate   → weighted by ngp
    "gnswr": "ngnd",   # Not-seen win rate        → weighted by ngnd
    "gdwr": "ngd",     # Drawn win rate           → weighted by ngd
}
# alsa, ata: weighted by ngp (fallback in code)
# iwd: NOT directly averaged — re-derived as merged_gihwr − merged_gnswr
```

### IWD correct definition (17Lands)
IWD (Improvement When Drawn) = GIHWR − GNSWR.
When merging, compute `merged_iwd = merged_gihwr − merged_gnswr` after computing each independently via game-count weighting. This is inherently "weighted by the number of games in each situation."

### `_make_dataset` test helper (already in test file)
```python
_make_dataset(card_ratings, color_ratings=None, game_count=10000)
# meta.game_count = game_count
```

### Existing `_stats()` helper
```python
_stats(gihwr=0.0, ohwr=0.0, gpwr=0.0, gnswr=0.0, gdwr=0.0,
       alsa=0.0, ata=0.0, iwd=0.0, ngp=0, ngoh=0, gih=0, ngnd=0, ngd=0)
```

---

## Task 1: Migrate `DatasetSource.weight` → `enabled`

**Files:**
- Modify: `src/configuration.py:23-28`
- Modify: `tests/test_configuration.py`

### Step 1: Write failing tests

In `tests/test_configuration.py`, **replace** `test_set_sources_roundtrip` and **add** three new tests:

```python
def test_datasetsource_default_enabled():
    """DatasetSource defaults to enabled=True."""
    source = DatasetSource()
    assert source.enabled is True


def test_datasetsource_enabled_roundtrip(tmp_path):
    """enabled field survives write/read cycle."""
    config = Configuration()
    config.settings.set_sources = {
        "ECL": [
            DatasetSource(format="PremierDraft", user_group="All", enabled=True),
            DatasetSource(format="TradDraft", user_group="Top", enabled=False),
        ],
    }
    file_location = str(tmp_path / "config.json")
    write_configuration(config, file_location)
    loaded, success = read_configuration(file_location)

    assert success is True
    assert loaded.settings.set_sources["ECL"][0].enabled is True
    assert loaded.settings.set_sources["ECL"][1].enabled is False


def test_datasetsource_weight_migrates_to_enabled(tmp_path):
    """Old config.json with weight field is migrated: weight>0 → enabled=True, weight=0 → enabled=False."""
    config_dict = Configuration().model_dump()
    config_dict["settings"]["set_sources"] = {
        "ECL": [
            {"format": "PremierDraft", "user_group": "All", "weight": 1.0},
            {"format": "TradDraft", "user_group": "Top", "weight": 0.0},
        ]
    }
    file_location = str(tmp_path / "config.json")
    with open(file_location, "w") as f:
        json.dump(config_dict, f)

    config, success = read_configuration(file_location)

    assert success is True
    assert config.settings.set_sources["ECL"][0].enabled is True
    assert config.settings.set_sources["ECL"][1].enabled is False
```

Also update `test_old_config_with_date_fields_in_sources` to assert `enabled` instead of `weight`:
```python
# Replace:
#   assert config.settings.set_sources["ECL"][0].weight == 1.0
# With:
    assert config.settings.set_sources["ECL"][0].enabled is True
```

Remove the weight assertions from the old `test_set_sources_roundtrip` and replace it with `test_datasetsource_enabled_roundtrip` above.

### Step 2: Run tests to verify they fail

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_configuration.py -v -k "enabled or weight"
```

Expected: FAIL — `DatasetSource` has no `enabled` field yet.

### Step 3: Implement in `src/configuration.py`

Replace the `DatasetSource` class:
```python
class DatasetSource(BaseModel):
    """A single 17Lands data source with filter configuration."""
    format: str = "PremierDraft"
    user_group: str = "All"
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def _migrate_weight(cls, data):
        """Backward-compat: old configs have 'weight' float instead of 'enabled' bool."""
        if isinstance(data, dict) and "weight" in data:
            if "enabled" not in data:
                data["enabled"] = float(data["weight"]) > 0
            data.pop("weight", None)
        return data
```

Add `model_validator` to imports at top of file:
```python
from pydantic import BaseModel, Field, field_validator, model_validator
```

### Step 4: Run tests to verify they pass

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_configuration.py -v
```

Expected: All configuration tests PASS.

### Step 5: Commit

```bash
git add src/configuration.py tests/test_configuration.py
git commit -m "feat: migrate DatasetSource.weight to enabled bool with backward-compat"
```

---

## Task 2: Remove `weights` param from `merge_datasets` — update signatures

**Files:**
- Modify: `src/file_extractor.py:44-73`
- Modify: `tests/test_file_extractor.py` (all `merge_datasets` call sites)

### Step 1: Update all test calls (remove second arg)

In `tests/test_file_extractor.py`, find every `merge_datasets(...)` call and remove the `weights` argument.
There are ~13 calls. Use search-and-replace carefully, since each call has different argument values. Here is the complete list of changes:

| Old call | New call |
|---|---|
| `merge_datasets([ds], [1.0])` | `merge_datasets([ds])` |
| `merge_datasets([ds_a, ds_b], [1.0, 1.0])` | `merge_datasets([ds_a, ds_b])` |
| `merge_datasets([ds_premier, ds_trad], [0.7, 0.3])` | `merge_datasets([ds_premier, ds_trad])` |
| `merge_datasets([ds_a, ds_b], [0.6, 0.4])` | `merge_datasets([ds_a, ds_b])` |
| `merge_datasets([ds_a, ds_b], [1.0, 0.0])` | `merge_datasets([ds_a])` ← only pass enabled source |
| `merge_datasets([ds_a, ds_b], [0.7, 0.3])` (color test) | `merge_datasets([ds_a, ds_b])` |

The `[1.0, 0.0]` case (`test_merge_zero_weight_source_excluded`) must become `merge_datasets([ds_a])` — the caller is now responsible for filtering out disabled sources.

### Step 2: Run tests — expect FAIL

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets -v
```

Expected: Multiple `TypeError: merge_datasets() takes 1 positional argument but 2 were given` failures.

### Step 3: Update `merge_datasets` signature in `src/file_extractor.py`

Change function signature from:
```python
def merge_datasets(datasets: List[dict], weights: List[float]) -> dict:
```
to:
```python
def merge_datasets(datasets: List[dict]) -> dict:
```

Update the docstring and body. Remove all references to `weights` and `active`. Replace the `active` variable with just `datasets` (all passed datasets are now included):

```python
def merge_datasets(datasets: List[dict]) -> dict:
    """Merge multiple 17Lands dataset JSON dicts into one using game-count weighted averages.

    For each card (by Arena ID), for each numeric field in deck_colors:
      - Count fields (ngp, ngoh, gih, ngnd, ngd): summed across all sources
      - Rate/average fields: weighted by actual game count for that field
      - iwd: re-derived as merged_gihwr − merged_gnswr

    color_ratings are weighted by each source's meta.game_count.
    meta.game_count in the result is the sum across all sources.

    All passed datasets are merged. Callers are responsible for filtering
    disabled sources before calling this function.
    """
    if len(datasets) == 1:
        return copy.deepcopy(datasets[0])

    # Start with meta from first source, then aggregate game_count
    result = {"meta": copy.deepcopy(datasets[0].get("meta", {}))}
    result["meta"]["game_count"] = sum(
        ds.get("meta", {}).get("game_count", 0) for ds in datasets
    )

    # Merge color_ratings
    result["color_ratings"] = _merge_color_ratings(datasets)

    # Merge card_ratings
    result["card_ratings"] = _merge_card_ratings(datasets)

    return result
```

Update `_merge_color_ratings` signature from `(active)` to `(datasets)`:
```python
def _merge_color_ratings(datasets):
```
And update the loop from `for ds, _ in active:` to `for ds in datasets:` (temporarily keep existing logic, we'll fix weighting in Task 4).

Update `_merge_card_ratings` signature from `(active)` to `(datasets)`:
```python
def _merge_card_ratings(datasets):
```
And update its internal loop from `for ds, w in active:` to `for ds in datasets:`, removing weight references.

Update `_merge_deck_colors` signature from `(sources)` where sources were `(card_data, weight)` tuples, to accept plain `card_data` list:
```python
def _merge_deck_colors(sources):
    # sources is now List[card_data dict] — no weights
```
Update all internal references from `for card_data, w in sources:` to `for card_data in sources:`.
Also update `for stats, w in color_sources:` to `for stats in color_sources:`.
Keep `w` in the `total_weighted += stats[field] * w` line as `1.0` temporarily:
```python
total_weighted += stats[field] * 1.0  # TODO: replace with game-count weight in Task 5
total_weight += 1.0
```

### Step 4: Run tests — expect most to pass

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets -v
```

Expected: Tests that relied on user-weight math will fail (e.g., `test_merge_two_datasets_unequal_weights`, `test_merge_rate_fields_are_weighted_averaged`, `test_merge_color_ratings_blended`, `test_merge_both_sources_nonzero_rates`). Tests that only needed the API change should PASS.

### Step 5: Commit (transitional state — weights param removed, rate logic not yet fixed)

```bash
git add src/file_extractor.py tests/test_file_extractor.py
git commit -m "refactor: remove weights param from merge_datasets, caller filters enabled sources"
```

---

## Task 3: Fix meta `game_count` aggregation

**Files:**
- Modify: `tests/test_file_extractor.py`
- The `merge_datasets` implementation already fixes this in Task 2's `result["meta"]["game_count"] = sum(...)` line.

### Step 1: Add failing test (write BEFORE Task 2 implementation if doing TDD strictly)

Add to `TestMergeDatasets`:
```python
def test_merge_meta_game_count_summed(self):
    """merged meta.game_count is the sum across all sources."""
    ds_a = _make_dataset({}, game_count=59529)
    ds_b = _make_dataset({}, game_count=12000)
    ds_c = _make_dataset({}, game_count=8500)
    ds_d = _make_dataset({}, game_count=3200)

    result = merge_datasets([ds_a, ds_b, ds_c, ds_d])

    assert result["meta"]["game_count"] == 59529 + 12000 + 8500 + 3200
```

### Step 2: Run test

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets::test_merge_meta_game_count_summed -v
```

Expected: PASS (implemented in Task 2).

### Step 3: Commit

```bash
git add tests/test_file_extractor.py
git commit -m "test: add test for meta game_count aggregation across merge sources"
```

---

## Task 4: Fix `_merge_color_ratings` — use `meta.game_count` as weight

**Files:**
- Modify: `tests/test_file_extractor.py` — update `test_merge_color_ratings_blended`
- Modify: `src/file_extractor.py` — fix `_merge_color_ratings`

### Step 1: Update test expectations

In `tests/test_file_extractor.py`, update `test_merge_color_ratings_blended`:

```python
def test_merge_color_ratings_blended(self):
    """color_ratings weighted by each source's meta.game_count."""
    ds_a = _make_dataset({}, color_ratings={"WU": 55.0, "BR": 50.0}, game_count=8000)
    ds_b = _make_dataset({}, color_ratings={"WU": 60.0, "BR": 52.0}, game_count=4000)

    result = merge_datasets([ds_a, ds_b])

    # Weighted by game_count: (55*8000 + 60*4000) / 12000 = 56.7
    expected_wu = round((55.0 * 8000 + 60.0 * 4000) / (8000 + 4000), 1)
    # (50*8000 + 52*4000) / 12000 = 50.7
    expected_br = round((50.0 * 8000 + 52.0 * 4000) / (8000 + 4000), 1)
    assert result["color_ratings"]["WU"] == pytest.approx(expected_wu)
    assert result["color_ratings"]["BR"] == pytest.approx(expected_br)
```

### Step 2: Run test to verify it fails

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets::test_merge_color_ratings_blended -v
```

Expected: FAIL — current implementation uses `1.0` not game_count.

### Step 3: Fix `_merge_color_ratings` in `src/file_extractor.py`

```python
def _merge_color_ratings(datasets):
    """Weighted-average the color_ratings section using meta.game_count as weight."""
    all_colors = set()
    for ds in datasets:
        if "color_ratings" in ds:
            all_colors.update(ds["color_ratings"].keys())

    merged = {}
    for color in all_colors:
        total_weighted = 0.0
        total_weight = 0.0
        for ds in datasets:
            cr = ds.get("color_ratings", {})
            game_count = ds.get("meta", {}).get("game_count", 0)
            if color in cr and game_count > 0:
                total_weighted += cr[color] * game_count
                total_weight += game_count
        if total_weight > 0:
            merged[color] = round(total_weighted / total_weight, 1)

    return merged
```

### Step 4: Run test to verify it passes

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets::test_merge_color_ratings_blended -v
```

Expected: PASS.

### Step 5: Commit

```bash
git add src/file_extractor.py tests/test_file_extractor.py
git commit -m "fix: weight color_ratings by meta.game_count instead of user weight"
```

---

## Task 5: Fix `_merge_deck_colors` — game-count weighted rates

**Files:**
- Modify: `tests/test_file_extractor.py` — update 5 test methods
- Modify: `src/file_extractor.py` — fix `_merge_deck_colors`

### Step 1: Update failing test expectations

Replace the expected values in these test methods. Formulas: `merged_field = Σ(field_i × count_i) / Σ(count_i)` where `count_i` is the count field for that rate field.

**`test_merge_two_datasets_equal_weights`** — rename to `test_merge_two_datasets_rate_weighted_by_game_count`:
```python
def test_merge_two_datasets_rate_weighted_by_game_count(self):
    """Rate fields weighted by actual game counts, not equal split."""
    stats_a = _stats(gihwr=50.0, ata=3.0, ngp=1000, gih=400)
    stats_b = _stats(gihwr=60.0, ata=5.0, ngp=2000, gih=600)
    ds_a = _make_dataset({"1": _make_card("CardA", ["W"], ["Creature"], "common", 2, "{1}{W}", [], _make_deck_colors(stats_a))})
    ds_b = _make_dataset({"1": _make_card("CardA", ["W"], ["Creature"], "common", 2, "{1}{W}", [], _make_deck_colors(stats_b))})

    result = merge_datasets([ds_a, ds_b])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

    # gihwr: (50*400 + 60*600) / 1000 = 56.0
    assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(56.0)
    # ata: (3.0*1000 + 5.0*2000) / 3000 = 4.3
    assert ad[constants.DATA_FIELD_ATA] == pytest.approx(4.3, abs=0.1)
    assert ad[constants.DATA_FIELD_NGP] == 3000
    assert ad[constants.DATA_FIELD_GIH] == 1000
```

**`test_merge_two_datasets_unequal_weights`** — rename to `test_merge_two_datasets_large_source_dominates`:
```python
def test_merge_two_datasets_large_source_dominates(self):
    """Large source (more games) contributes more to rates than small source."""
    stats_premier = _stats(gihwr=55.0, ata=4.0, ngp=5000, gih=2000)
    stats_trad = _stats(gihwr=58.0, ata=3.5, ngp=1000, gih=400)
    ds_premier = _make_dataset({"1": _make_card("CardA", ["R"], ["Creature"], "rare", 3, "{2}{R}", [], _make_deck_colors(stats_premier))})
    ds_trad = _make_dataset({"1": _make_card("CardA", ["R"], ["Creature"], "rare", 3, "{2}{R}", [], _make_deck_colors(stats_trad))})

    result = merge_datasets([ds_premier, ds_trad])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

    # gihwr: (55*2000 + 58*400) / 2400 = 55.5
    assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(55.5, abs=0.1)
    # ata: (4.0*5000 + 3.5*1000) / 6000 = 3.9
    assert ad[constants.DATA_FIELD_ATA] == pytest.approx(3.9, abs=0.1)
    assert ad[constants.DATA_FIELD_NGP] == 6000
    assert ad[constants.DATA_FIELD_GIH] == 2400
```

**`test_merge_rate_fields_are_weighted_averaged`** — rename to `test_merge_all_rate_fields_game_count_weighted`:
```python
def test_merge_all_rate_fields_game_count_weighted(self):
    """All rate fields use game-count weighting. iwd excluded (re-derived in Task 6)."""
    stats_a = _stats(gihwr=50.0, ohwr=48.0, gpwr=52.0, gnswr=46.0, gdwr=54.0, alsa=5.0, ata=3.0,
                     ngp=1000, ngoh=500, gih=800, ngnd=200, ngd=600)
    stats_b = _stats(gihwr=60.0, ohwr=58.0, gpwr=62.0, gnswr=56.0, gdwr=64.0, alsa=3.0, ata=2.0,
                     ngp=800, ngoh=400, gih=600, ngnd=150, ngd=500)
    ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
    ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

    result = merge_datasets([ds_a, ds_b])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

    # gihwr: (50*800 + 60*600) / 1400 = 54.3
    assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(54.3, abs=0.1)
    # ohwr: (48*500 + 58*400) / 900 = 52.4
    assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(52.4, abs=0.1)
    # gpwr: (52*1000 + 62*800) / 1800 = 56.4
    assert ad[constants.DATA_FIELD_GPWR] == pytest.approx(56.4, abs=0.1)
    # gnswr: (46*200 + 56*150) / 350 = 50.3
    assert ad[constants.DATA_FIELD_GNSWR] == pytest.approx(50.3, abs=0.1)
    # gdwr: (54*600 + 64*500) / 1100 = 58.5
    assert ad[constants.DATA_FIELD_GDWR] == pytest.approx(58.5, abs=0.1)
    # alsa: (5.0*1000 + 3.0*800) / 1800 = 4.1
    assert ad[constants.DATA_FIELD_ALSA] == pytest.approx(4.1, abs=0.1)
    # ata: (3.0*1000 + 2.0*800) / 1800 = 2.6
    assert ad[constants.DATA_FIELD_ATA] == pytest.approx(2.6, abs=0.1)
```

**`test_merge_partial_zero_count`**:
```python
def test_merge_partial_zero_count(self):
    """One source has OHWR data but not GIHWR — only the missing rate is excluded."""
    stats_a = _stats(gihwr=55.0, ohwr=50.0, ngp=1000, ngoh=500, gih=800)
    stats_b = _stats(gihwr=60.0, ohwr=0.0, ngp=500, ngoh=0, gih=300)
    ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
    ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

    result = merge_datasets([ds_a, ds_b])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

    # GIHWR: both have gih>0 → game-count weighted: (55*800 + 60*300) / 1100 = 56.4
    assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(56.4, abs=0.1)
    # OHWR: source B has ngoh=0 → only source A contributes → 50.0
    assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(50.0, abs=0.1)
```

**`test_merge_both_sources_nonzero_rates`**:
```python
def test_merge_both_sources_nonzero_rates(self):
    """Both sources have real win rate data — game-count weighted average."""
    stats_a = _stats(gihwr=50.0, ohwr=48.0, ngp=5000, ngoh=2000, gih=3000)
    stats_b = _stats(gihwr=60.0, ohwr=58.0, ngp=1000, ngoh=400, gih=600)
    ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
    ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

    result = merge_datasets([ds_a, ds_b])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

    # gihwr: (50*3000 + 60*600) / 3600 = 51.7
    assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(51.7, abs=0.1)
    # ohwr: (48*2000 + 58*400) / 2400 = 49.7
    assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(49.7, abs=0.1)
```

Also update `test_merge_zero_weight_source_excluded` to reflect new contract (caller filters):
```python
def test_merge_disabled_source_excluded_by_caller(self):
    """Disabled sources are filtered out by caller before merge_datasets is called.
    When only source A is passed, result reflects source A only."""
    stats_a = _stats(gihwr=55.0, ngp=1000, gih=500)
    stats_b_unused = _stats(gihwr=99.0, ngp=9999, gih=9999)
    ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))},
                         color_ratings={"WU": 52.0})
    # ds_b_unused not passed — caller excluded it
    result = merge_datasets([ds_a])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]
    assert ad[constants.DATA_FIELD_GIHWR] == 55.0
    assert ad[constants.DATA_FIELD_NGP] == 1000
    assert ad[constants.DATA_FIELD_GIH] == 500
    assert result["color_ratings"]["WU"] == pytest.approx(52.0)
```

### Step 2: Run tests to verify they fail

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets -v
```

Expected: The updated tests FAIL (still using `1.0` temporary weight).

### Step 3: Fix `_merge_card_ratings` and `_merge_deck_colors`

In `src/file_extractor.py`:

```python
def _merge_card_ratings(datasets):
    """Merge card_ratings across all datasets."""
    all_card_ids = set()
    for ds in datasets:
        all_card_ids.update(ds.get("card_ratings", {}).keys())

    merged_cards = {}
    for card_id in all_card_ids:
        sources = []
        for ds in datasets:
            card_ratings = ds.get("card_ratings", {})
            if card_id in card_ratings:
                sources.append(card_ratings[card_id])

        if not sources:
            continue

        first_card = sources[0]
        merged_card = {}
        for key, value in first_card.items():
            if key == constants.DATA_FIELD_DECK_COLORS:
                continue
            merged_card[key] = copy.deepcopy(value)

        merged_card[constants.DATA_FIELD_DECK_COLORS] = _merge_deck_colors(sources)
        merged_cards[card_id] = merged_card

    return merged_cards


def _merge_deck_colors(sources):
    """Merge the deck_colors section for a single card.

    sources: List[card_data dict] — no weights, all are included.
    Rate fields are weighted by their corresponding game-count field.
    iwd is re-derived as merged_gihwr − merged_gnswr after all rates are computed.
    """
    all_colors = set()
    for card_data in sources:
        if constants.DATA_FIELD_DECK_COLORS in card_data:
            all_colors.update(card_data[constants.DATA_FIELD_DECK_COLORS].keys())

    merged = {}
    for color in all_colors:
        color_sources = []
        for card_data in sources:
            dc = card_data.get(constants.DATA_FIELD_DECK_COLORS, {})
            if color in dc:
                color_sources.append(dc[color])

        if not color_sources:
            continue

        all_fields = set()
        for stats in color_sources:
            all_fields.update(stats.keys())

        merged_stats = {}

        for field in all_fields:
            if field in constants.COUNT_FIELDS:
                merged_stats[field] = sum(
                    stats.get(field, 0) for stats in color_sources
                )
            elif field == constants.DATA_FIELD_IWD:
                pass  # re-derived below after gihwr and gnswr are computed
            else:
                count_field = constants.WIN_RATE_FIELDS_DICT.get(field)
                # For alsa/ata (not in WIN_RATE_FIELDS_DICT): use ngp as weight
                check_field = count_field if count_field else constants.DATA_FIELD_NGP
                total_weighted = 0.0
                total_weight = 0.0
                for stats in color_sources:
                    if field not in stats:
                        continue
                    effective_weight = stats.get(check_field, 0)
                    if effective_weight == 0:
                        continue
                    # 0.0 rate with nonzero count = suppressed by 17Lands API, skip
                    if count_field is not None and stats[field] == 0.0:
                        continue
                    total_weighted += stats[field] * effective_weight
                    total_weight += effective_weight
                if total_weight > 0:
                    merged_stats[field] = round(total_weighted / total_weight, 1)
                else:
                    merged_stats[field] = 0.0

        # Re-derive iwd = gihwr − gnswr (17Lands definition, game-count weighted implicitly)
        if constants.DATA_FIELD_IWD in all_fields:
            gihwr = merged_stats.get(constants.DATA_FIELD_GIHWR, 0.0)
            gnswr = merged_stats.get(constants.DATA_FIELD_GNSWR, 0.0)
            if gihwr != 0.0 or gnswr != 0.0:
                merged_stats[constants.DATA_FIELD_IWD] = round(gihwr - gnswr, 1)
            else:
                merged_stats[constants.DATA_FIELD_IWD] = 0.0

        merged[color] = merged_stats

    return merged
```

### Step 4: Run tests to verify they pass

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets -v
```

Expected: All `TestMergeDatasets` tests PASS.

### Step 5: Commit

```bash
git add src/file_extractor.py tests/test_file_extractor.py
git commit -m "fix: weight rate fields by game count instead of user weight in merge_datasets"
```

---

## Task 6: Add `iwd` re-derivation test

**Files:**
- Modify: `tests/test_file_extractor.py`

### Step 1: Add test

```python
def test_merge_iwd_rederived_as_gihwr_minus_gnswr(self):
    """iwd is re-derived as merged_gihwr − merged_gnswr, not averaged directly.

    17Lands definition: IWD (Improvement When Drawn) = GIHWR − GNSWR.
    Because both components are already game-count weighted, the merged iwd
    naturally reflects game-count weighting.
    """
    # Source A: gihwr=55.0, gnswr=50.0 → iwd=5.0 (gih=1000, ngnd=500)
    # Source B: gihwr=65.0, gnswr=55.0 → iwd=10.0 (gih=200, ngnd=100)
    stats_a = _stats(gihwr=55.0, gnswr=50.0, iwd=5.0, ngp=1500, gih=1000, ngnd=500)
    stats_b = _stats(gihwr=65.0, gnswr=55.0, iwd=10.0, ngp=300, gih=200, ngnd=100)
    ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
    ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

    result = merge_datasets([ds_a, ds_b])
    ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

    # merged_gihwr: (55*1000 + 65*200) / 1200 = 56.7
    expected_gihwr = round((55.0 * 1000 + 65.0 * 200) / 1200, 1)
    # merged_gnswr: (50*500 + 55*100) / 600 = 50.8
    expected_gnswr = round((50.0 * 500 + 55.0 * 100) / 600, 1)
    # merged_iwd = 56.7 - 50.8 = 5.9 (NOT a simple average of 5.0 and 10.0)
    expected_iwd = round(expected_gihwr - expected_gnswr, 1)

    assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(expected_gihwr, abs=0.1)
    assert ad[constants.DATA_FIELD_GNSWR] == pytest.approx(expected_gnswr, abs=0.1)
    assert ad[constants.DATA_FIELD_IWD] == pytest.approx(expected_iwd, abs=0.1)
    # Sanity check: iwd != simple average of 5.0 and 10.0
    assert ad[constants.DATA_FIELD_IWD] != pytest.approx(7.5, abs=0.5)
```

### Step 2: Run test to verify it passes

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_file_extractor.py::TestMergeDatasets::test_merge_iwd_rederived_as_gihwr_minus_gnswr -v
```

Expected: PASS (iwd re-derivation already implemented in Task 5).

### Step 3: Commit

```bash
git add tests/test_file_extractor.py
git commit -m "test: verify iwd is re-derived as gihwr minus gnswr after merge"
```

---

## Task 7: Update `overlay.py` — filter by `source.enabled`, remove weights

**Files:**
- Modify: `src/overlay.py:3416-3450` (download + merge block)
- Modify: `src/overlay.py:3525-3553` (`_open_source_editor`)

No unit tests for these UI changes (Tkinter overlay is not unit-tested). Verify manually.

### Step 1: Fix the download and merge block (around line 3416)

Replace:
```python
all_datasets = [copy.deepcopy(self.extractor.combined_data)]
all_weights = [active_sources[0].weight]
# ...
all_datasets.append(copy.deepcopy(self.extractor.combined_data))
all_weights.append(source.weight)
# ...
merged = merge_datasets(all_datasets, all_weights)
```

With:
```python
all_datasets = [copy.deepcopy(self.extractor.combined_data)]
# ...
all_datasets.append(copy.deepcopy(self.extractor.combined_data))
# ...
merged = merge_datasets(all_datasets)
```

Remove the `all_weights` variable initialization, append, and usage entirely.

Also ensure that `active_sources` is filtered to `enabled=True` sources only. Find where `active_sources` is built (it comes from `self.configuration.settings.set_sources.get(set_code, [])`). Add the filter:
```python
# After loading sources:
active_sources = [s for s in sources if s.enabled]
```

### Step 2: Fix `_open_source_editor` (around line 3525)

Remove the "Weight" row:
```python
# DELETE these lines:
row += 1
tkinter.Label(dialog, text="Weight:").grid(row=row, column=0, sticky="e", padx=4, pady=2)
weight_entry = tkinter.Entry(dialog)
weight_entry.insert(0, str(source.weight))
weight_entry.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
```

Replace with an "Enabled" checkbox:
```python
row += 1
enabled_var = tkinter.BooleanVar(value=source.enabled)
tkinter.Checkbutton(dialog, text="Enabled", variable=enabled_var).grid(
    row=row, column=0, columnspan=2, sticky="w", padx=4, pady=2)
```

In the `_save` function, replace:
```python
# DELETE:
try:
    weight = float(weight_entry.get())
except ValueError:
    weight = 1.0
new_source = DatasetSource(
    format=format_var.get(),
    user_group=group_var.get(),
    weight=weight,
)
```

With:
```python
new_source = DatasetSource(
    format=format_var.get(),
    user_group=group_var.get(),
    enabled=enabled_var.get(),
)
```

### Step 3: Commit

```bash
git add src/overlay.py
git commit -m "feat: replace source weight with enabled flag in overlay UI"
```

---

## Task 8: Full test suite

### Step 1: Run all tests

```bash
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v
```

Expected: All ~355+ tests PASS. Any failures indicate regressions to investigate.

### Step 2: Commit if any fixes were needed

```bash
git add -p  # stage only what you fixed
git commit -m "fix: resolve test regressions from merge_datasets refactor"
```
