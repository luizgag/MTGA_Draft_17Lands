# Archetype Openness Detection — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect which draft archetypes are "open" by comparing when cards appear in packs versus their expected pick position (ATA), weighted by how strongly each card signals each archetype.

**Architecture:** New module `src/archetype_openness.py` contains the scoring engine (`OpennessTracker`). New module `src/archetype_editor.py` contains the Tkinter editor window. Archetype configs persist as JSON in `Archetypes/` directory per set. The overlay integrates the openness panel below the pack table and triggers scoring on each pack update. Configuration gets a new `archetype_openness_enabled` flag in `Features`.

**Tech Stack:** Python 3.12, Tkinter, Pydantic, pytest. No new dependencies.

---

### Task 1: Archetype Config Data Model — Load/Save/Auto-Detect

This task creates the core data structures and persistence for archetype configurations, plus the auto-detection logic that scans 17Lands data to find viable archetypes and calculate card weights.

**Files:**
- Create: `src/archetype_openness.py`
- Create: `tests/test_archetype_openness.py`
- Modify: `src/constants.py` (add `ARCHETYPES_FOLDER` constant near line 294)

**Step 1: Write failing tests for archetype config persistence**

In `tests/test_archetype_openness.py`:

```python
import pytest
import os
import json
from src.archetype_openness import (
    ArchetypeConfig,
    load_archetype_config,
    save_archetype_config,
)

VALID_CONFIG = {
    "set_code": "OTJ",
    "detection_threshold": 5.0,
    "scoring_method": "simple",
    "pack_weights": [1.0, 1.0, 1.0],
    "archetypes": [
        {
            "name": "Golgari",
            "color_pair": "BG",
            "auto_weights": True,
            "cards": {
                "Hardbristle Bandit": 0.85,
                "Shoot the Sheriff": 0.30,
            },
        }
    ],
}


def test_archetype_config_round_trip(tmp_path):
    """Save and reload archetype config, verify equality."""
    file_path = tmp_path / "OTJ_archetypes.json"
    config = ArchetypeConfig.model_validate(VALID_CONFIG)
    save_archetype_config(config, str(file_path))
    loaded = load_archetype_config(str(file_path))
    assert loaded is not None
    assert loaded.set_code == "OTJ"
    assert loaded.archetypes[0].name == "Golgari"
    assert loaded.archetypes[0].cards["Hardbristle Bandit"] == 0.85


def test_load_missing_file_returns_none(tmp_path):
    """Missing file returns None gracefully."""
    loaded = load_archetype_config(str(tmp_path / "nonexistent.json"))
    assert loaded is None


def test_load_malformed_json_returns_none(tmp_path):
    """Malformed JSON returns None gracefully."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{invalid json")
    loaded = load_archetype_config(str(bad_file))
    assert loaded is None


def test_archetype_config_defaults():
    """Config with minimal fields gets correct defaults."""
    config = ArchetypeConfig(set_code="TST")
    assert config.detection_threshold == 5.0
    assert config.scoring_method == "simple"
    assert config.pack_weights == [1.0, 1.0, 1.0]
    assert config.archetypes == []
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.archetype_openness'`

**Step 3: Write minimal implementation for config persistence**

In `src/archetype_openness.py`:

```python
"""Archetype openness detection for draft signal analysis."""

import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from src.logger import create_logger

logger = create_logger()


class Archetype(BaseModel):
    """A single draft archetype with card weights."""
    name: str
    color_pair: Optional[str] = None
    auto_weights: bool = True
    cards: Dict[str, float] = Field(default_factory=dict)


class ArchetypeConfig(BaseModel):
    """Full archetype configuration for a set."""
    set_code: str
    detection_threshold: float = 5.0
    scoring_method: str = "simple"
    pack_weights: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    archetypes: List[Archetype] = Field(default_factory=list)


def load_archetype_config(file_path: str) -> Optional[ArchetypeConfig]:
    """Load archetype config from JSON file. Returns None if file missing or invalid."""
    try:
        with open(file_path, "r", encoding="utf8", errors="replace") as f:
            data = json.loads(f.read())
        return ArchetypeConfig.model_validate(data)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as error:
        logger.error("Failed to load archetype config: %s", error)
        return None


def save_archetype_config(config: ArchetypeConfig, file_path: str) -> bool:
    """Save archetype config to JSON file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf8", errors="replace") as f:
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=4)
        return True
    except (OSError, TypeError) as error:
        logger.error("Failed to save archetype config: %s", error)
        return False
```

Add to `src/constants.py` near line 294 (after `SETS_FOLDER`):

```python
ARCHETYPES_FOLDER = os.path.join(os.getcwd(), "Archetypes")
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All 4 tests PASS

**Step 5: Write failing tests for auto-detection**

Append to `tests/test_archetype_openness.py`:

```python
from src.archetype_openness import auto_detect_archetypes, calculate_card_weights
from src.dataset import Dataset

OTJ_DATASET_FILE = os.path.join(os.getcwd(), "tests", "data", "OTJ_PremierDraft_Data_2024_5_3.json")


@pytest.fixture
def otj_dataset():
    dataset = Dataset()
    dataset.open_file(OTJ_DATASET_FILE)
    return dataset


def test_auto_detect_finds_color_pairs_above_threshold(otj_dataset):
    """Auto-detect returns color pairs whose total games exceed threshold % of all games."""
    archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
    # Should find some archetypes but not all 25 color combos
    assert len(archetypes) > 0
    assert len(archetypes) < 25
    # Each archetype should have a name and color_pair
    for arch in archetypes:
        assert arch.name
        assert arch.color_pair


def test_auto_detect_with_zero_threshold_returns_all(otj_dataset):
    """Threshold of 0 returns all color pairs that have any games."""
    archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=0.0)
    assert len(archetypes) > 10


def test_auto_detect_with_100_threshold_returns_none(otj_dataset):
    """Threshold of 100 returns no archetypes (no single color pair has 100% of games)."""
    archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=100.0)
    assert len(archetypes) == 0


def test_calculate_card_weights(otj_dataset):
    """Card weights are ngp(color_pair) / ngp(All Decks), between 0 and 1."""
    weights = calculate_card_weights(otj_dataset, "BG")
    assert len(weights) > 0
    for card_name, weight in weights.items():
        assert 0.0 < weight <= 1.0


def test_calculate_card_weights_excludes_zero_ngp(otj_dataset):
    """Cards with 0 games in the color pair are not included."""
    weights = calculate_card_weights(otj_dataset, "BG")
    for card_name, weight in weights.items():
        assert weight > 0.0
```

**Step 6: Run tests to verify new tests fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: 4 PASS, 5 FAIL (`ImportError` for new functions)

**Step 7: Implement auto-detection and weight calculation**

Append to `src/archetype_openness.py`:

```python
from src.constants import (
    DATA_FIELD_NAME,
    DATA_FIELD_NGP,
    DATA_FIELD_DECK_COLORS,
    DECK_COLORS,
    FILTER_OPTION_ALL_DECKS,
    COLOR_NAMES_DICT,
)


def _get_all_card_ratings(dataset) -> Dict:
    """Access the internal card_ratings dict from a Dataset."""
    return dataset._dataset.get("card_ratings", {}) if dataset._dataset else {}


def calculate_card_weights(dataset, color_pair: str) -> Dict[str, float]:
    """Calculate card weights for a color pair: ngp(color_pair) / ngp(All Decks).

    Returns dict of {card_name: weight} for cards with weight > 0.
    """
    card_ratings = _get_all_card_ratings(dataset)
    weights = {}

    for card_id, card in card_ratings.items():
        deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
        all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
        color_data = deck_colors.get(color_pair, {})

        total_ngp = all_decks.get(DATA_FIELD_NGP, 0)
        color_ngp = color_data.get(DATA_FIELD_NGP, 0)

        if total_ngp > 0 and color_ngp > 0:
            weight = color_ngp / total_ngp
            weights[card[DATA_FIELD_NAME]] = round(weight, 4)

    return weights


def auto_detect_archetypes(dataset, threshold_percent: float = 5.0) -> List[Archetype]:
    """Detect viable archetypes by finding color pairs with games above threshold.

    threshold_percent: minimum percentage of total games a color pair must have.
    """
    card_ratings = _get_all_card_ratings(dataset)
    if not card_ratings:
        return []

    # Sum ngp across all cards for each color pair
    color_totals = {}
    overall_total = 0

    for card_id, card in card_ratings.items():
        deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
        all_decks_ngp = deck_colors.get(FILTER_OPTION_ALL_DECKS, {}).get(DATA_FIELD_NGP, 0)
        overall_total += all_decks_ngp

        for color_pair in DECK_COLORS:
            if color_pair == FILTER_OPTION_ALL_DECKS:
                continue
            color_data = deck_colors.get(color_pair, {})
            ngp = color_data.get(DATA_FIELD_NGP, 0)
            color_totals[color_pair] = color_totals.get(color_pair, 0) + ngp

    if overall_total == 0:
        return []

    archetypes = []
    for color_pair, total_ngp in color_totals.items():
        percentage = (total_ngp / overall_total) * 100
        if percentage >= threshold_percent:
            name = COLOR_NAMES_DICT.get(color_pair, color_pair)
            cards = calculate_card_weights(dataset, color_pair)
            archetypes.append(Archetype(
                name=name,
                color_pair=color_pair,
                auto_weights=True,
                cards=cards,
            ))

    return archetypes
```

**Step 8: Run tests to verify all pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All 9 tests PASS

**Step 9: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py src/constants.py
git commit -m "feat: add archetype config data model with load/save and auto-detection"
```

---

### Task 2: Openness Scoring Engine (`OpennessTracker`)

This task implements the core scoring logic that computes archetype openness from draft signals.

**Files:**
- Modify: `src/archetype_openness.py`
- Modify: `tests/test_archetype_openness.py`

**Step 1: Write failing tests for `OpennessTracker`**

Append to `tests/test_archetype_openness.py`:

```python
from src.archetype_openness import OpennessTracker, ArchetypeConfig, Archetype

SIMPLE_CONFIG = ArchetypeConfig(
    set_code="TST",
    scoring_method="simple",
    pack_weights=[1.0, 1.0, 1.0],
    archetypes=[
        Archetype(
            name="BG Elves",
            color_pair="BG",
            auto_weights=False,
            cards={
                "Elf Lord": 0.9,
                "Llanowar Elves": 0.5,
                "Murder": 0.2,
            },
        ),
        Archetype(
            name="UB Control",
            color_pair="UB",
            auto_weights=False,
            cards={
                "Murder": 0.7,
                "Counterspell": 0.8,
            },
        ),
    ],
)


def _make_card(name, ata):
    """Helper to create a minimal card dict for testing."""
    return {
        "name": name,
        "deck_colors": {
            "All Decks": {"ata": ata, "ngp": 100},
        },
    }


class TestOpennessTrackerSimple:
    """Tests for simple scoring method: signal = (pick - ATA) * weight * pack_weight."""

    def test_single_card_positive_signal(self):
        """Card with ATA 3.0 seen at pick 7 -> signal = (7-3) * 0.9 = 3.6 for BG Elves."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=3.0)]
        tracker.record_pack(pack, pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(3.6, abs=0.01)

    def test_single_card_negative_signal(self):
        """Card with ATA 7.0 seen at pick 3 -> signal = (3-7) * 0.9 = -3.6 for BG Elves."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=7.0)]
        tracker.record_pack(pack, pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(-3.6, abs=0.01)

    def test_multi_archetype_card(self):
        """Murder belongs to both BG Elves (0.2) and UB Control (0.7)."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Murder", ata=4.0)]
        tracker.record_pack(pack, pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(0.8, abs=0.01)   # (8-4) * 0.2
        assert scores["UB Control"] == pytest.approx(2.8, abs=0.01)  # (8-4) * 0.7

    def test_card_not_in_any_archetype(self):
        """Cards not assigned to any archetype are silently skipped."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Random Card", ata=5.0)]
        tracker.record_pack(pack, pick_number=10, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == 0.0
        assert scores["UB Control"] == 0.0

    def test_accumulation_across_packs(self):
        """Signals accumulate across multiple record_pack calls."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.record_pack([_make_card("Llanowar Elves", ata=5.0)], pick_number=9, pack_number=0)
        scores = tracker.get_scores()
        # (7-3)*0.9 + (9-5)*0.5 = 3.6 + 2.0 = 5.6
        assert scores["BG Elves"] == pytest.approx(5.6, abs=0.01)

    def test_pack_weights_applied(self):
        """Pack weights multiply the signal."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="simple",
            pack_weights=[1.0, 0.5, 0.75],
            archetypes=[
                Archetype(name="BG Elves", cards={"Elf Lord": 0.9}),
            ],
        )
        tracker = OpennessTracker(config)
        # Pack 2 (index 1), weight 0.5
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=1)
        scores = tracker.get_scores()
        # (7-3) * 0.9 * 0.5 = 1.8
        assert scores["BG Elves"] == pytest.approx(1.8, abs=0.01)

    def test_reset_clears_signals(self):
        """Reset clears all accumulated signals."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.reset()
        scores = tracker.get_scores()
        assert scores["BG Elves"] == 0.0

    def test_empty_pack(self):
        """Empty pack list is a no-op."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == 0.0


class TestOpennessTrackerNormalized:
    """Tests for normalized scoring: signal = ((pick - ATA) / ATA) * weight * pack_weight."""

    def test_normalized_scoring(self):
        """Card with ATA 2.0 seen at pick 6 -> signal = ((6-2)/2) * 0.9 = 1.8."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=2.0)], pick_number=6, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(1.8, abs=0.01)

    def test_normalized_emphasizes_low_ata(self):
        """Normalized method gives proportionally higher signal for low-ATA cards."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            archetypes=[Archetype(name="Test", cards={"Early": 1.0, "Late": 1.0})],
        )
        tracker = OpennessTracker(config)
        # Early card: ATA 2.0, seen at pick 6 -> ((6-2)/2) * 1.0 = 2.0
        tracker.record_pack([_make_card("Early", ata=2.0)], pick_number=6, pack_number=0)
        # Late card: ATA 8.0, seen at pick 12 -> ((12-8)/8) * 1.0 = 0.5
        tracker.record_pack([_make_card("Late", ata=8.0)], pick_number=12, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"] == pytest.approx(2.5, abs=0.01)

    def test_normalized_zero_ata_skipped(self):
        """Cards with ATA of 0 are skipped to avoid division by zero."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            archetypes=[Archetype(name="Test", cards={"Bad Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Bad Card", ata=0.0)], pick_number=5, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"] == 0.0


class TestTopContributors:
    """Tests for get_top_contributors."""

    def test_returns_top_n_by_signal(self):
        """Returns the top N signals sorted by absolute signal value."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([
            _make_card("Elf Lord", ata=2.0),       # (7-2)*0.9 = 4.5
            _make_card("Llanowar Elves", ata=4.0),  # (7-4)*0.5 = 1.5
            _make_card("Murder", ata=3.0),           # (7-3)*0.2 = 0.8
        ], pick_number=7, pack_number=0)
        top = tracker.get_top_contributors("BG Elves", count=2)
        assert len(top) == 2
        assert top[0]["card_name"] == "Elf Lord"
        assert top[1]["card_name"] == "Llanowar Elves"

    def test_empty_archetype_returns_empty(self):
        """No signals for an archetype returns empty list."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        top = tracker.get_top_contributors("BG Elves", count=3)
        assert top == []
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestOpennessTrackerSimple -v`
Expected: FAIL — `ImportError: cannot import name 'OpennessTracker'`

**Step 3: Implement `OpennessTracker`**

Add to `src/archetype_openness.py`:

```python
from src.constants import DATA_FIELD_ATA


class OpennessTracker:
    """Tracks archetype openness signals during a draft."""

    def __init__(self, config: ArchetypeConfig):
        self.scoring_method = config.scoring_method
        self.pack_weights = config.pack_weights
        self.archetypes = config.archetypes
        self.signals: List[Dict] = []

    def record_pack(self, pack_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record signals from a pack of cards.

        Args:
            pack_cards: list of card dicts from the dataset
            pick_number: 1-based pick position within the pack
            pack_number: 0-indexed pack number (0=pack1, 1=pack2, 2=pack3)
        """
        pack_weight = self.pack_weights[pack_number] if pack_number < len(self.pack_weights) else 1.0

        for card in pack_cards:
            card_name = card.get(DATA_FIELD_NAME, "")
            deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
            all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
            ata = all_decks.get(DATA_FIELD_ATA, 0.0)

            for archetype in self.archetypes:
                if card_name not in archetype.cards:
                    continue

                card_weight = archetype.cards[card_name]

                if self.scoring_method == "normalized":
                    if ata == 0.0:
                        continue
                    raw_signal = (pick_number - ata) / ata
                else:
                    raw_signal = pick_number - ata

                signal = raw_signal * card_weight * pack_weight

                self.signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": signal,
                })

    def get_scores(self) -> Dict[str, float]:
        """Get aggregated openness scores for all archetypes.

        Returns dict of {archetype_name: total_score}.
        Archetypes with no signals return 0.0.
        """
        scores = {arch.name: 0.0 for arch in self.archetypes}
        for sig in self.signals:
            scores[sig["archetype"]] += sig["signal"]
        return scores

    def get_top_contributors(self, archetype_name: str, count: int = 3) -> List[Dict]:
        """Get the top N contributing signals for an archetype, sorted by absolute signal.

        Returns list of dicts: [{"card_name", "pick_number", "ata", "signal"}, ...]
        """
        arch_signals = [s for s in self.signals if s["archetype"] == archetype_name]
        arch_signals.sort(key=lambda s: abs(s["signal"]), reverse=True)
        return [
            {
                "card_name": s["card_name"],
                "pick_number": s["pick_number"],
                "ata": s["ata"],
                "signal": s["signal"],
            }
            for s in arch_signals[:count]
        ]

    def reset(self) -> None:
        """Clear all accumulated signals."""
        self.signals.clear()
```

**Step 4: Run all tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All tests PASS (9 from Task 1 + 13 from Task 2 = 22 total)

**Step 5: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add OpennessTracker scoring engine with simple and normalized methods"
```

---

### Task 3: Configuration Integration

Add the `archetype_openness_enabled` flag to the Features model so users can toggle the feature.

**Files:**
- Modify: `src/configuration.py:119-123` (add field to `Features`)
- Modify: `tests/test_configuration.py` (add test for new field)

**Step 1: Write failing test**

Add to `tests/test_configuration.py`:

```python
def test_features_archetype_openness_default():
    """archetype_openness_enabled defaults to False."""
    features = Features()
    assert features.archetype_openness_enabled is False
```

**Step 2: Run test to verify it fails**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_configuration.py::test_features_archetype_openness_default -v`
Expected: FAIL — `AttributeError`

**Step 3: Add the field to `Features`**

In `src/configuration.py`, modify the `Features` class (line 119-123):

```python
class Features(BaseModel):
    """This class represents a collection of features that can be enabled or disabled within the overlay"""
    override_scale_factor: float = 0.0
    hotkey_enabled: bool = True
    images_enabled: bool = True
    archetype_openness_enabled: bool = False
```

**Step 4: Run test to verify it passes**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_configuration.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/configuration.py tests/test_configuration.py
git commit -m "feat: add archetype_openness_enabled flag to Features config"
```

---

### Task 4: Overlay Integration — Openness Panel

Wire the `OpennessTracker` into the overlay's update loop and render the openness panel below the pack table.

**Files:**
- Modify: `src/overlay.py`
    - Import `OpennessTracker`, `load_archetype_config` (top of file)
    - Add panel widget creation in `__init__` (near line 535 where pack_table_frame is positioned)
    - Add `__update_openness_panel` method
    - Call `record_pack` and `__update_openness_panel` from `__update_overlay_callback` (after line 1598)
    - Initialize/reset tracker in draft start/reset flow

**Step 1: Add imports and tracker initialization in `__init__`**

At top of `src/overlay.py`, add import:

```python
from src.archetype_openness import OpennessTracker, load_archetype_config
```

In `__init__`, after the pack_table_frame grid placement (near line 535), add openness panel creation:

```python
# Openness panel (collapsible, below pack table)
self.openness_tracker = None
self.openness_frame = tkinter.LabelFrame(self.root, text="Archetype Openness")
self.openness_labels = {}
```

Position it in the grid after the pack table frame. The exact row number depends on the current layout — place it after the last existing widget row:

```python
self.openness_frame.grid(row=11, column=0, columnspan=2, sticky="ew")
self.openness_frame.grid_remove()  # Hidden by default until archetypes are loaded
```

**Step 2: Initialize tracker on draft start**

In the `__update_draft` method (around line 1340), after `draft_start_search()` detects a new draft:

```python
if self.draft.draft_start_search():
    update = True
    # ... existing code ...

    # Initialize openness tracker
    if self.configuration.features.archetype_openness_enabled:
        set_code = self.draft.draft_sets[0] if self.draft.draft_sets else ""
        config_path = os.path.join(constants.ARCHETYPES_FOLDER, f"{set_code}_archetypes.json")
        archetype_config = load_archetype_config(config_path)
        if archetype_config:
            self.openness_tracker = OpennessTracker(archetype_config)
            self.openness_frame.grid()
        else:
            self.openness_tracker = None
            self.openness_frame.grid_remove()
    else:
        self.openness_tracker = None
        self.openness_frame.grid_remove()
```

**Step 3: Record signals and update panel in `__update_overlay_callback`**

After the `__update_pack_table` call (line 1598), add:

```python
# Update openness scoring
if self.openness_tracker and pack_cards:
    self.openness_tracker.record_pack(pack_cards, current_pick, current_pack - 1)
    self.__update_openness_panel()
```

**Step 4: Implement `__update_openness_panel` method**

Add this method to the overlay class:

```python
def __update_openness_panel(self):
    """Update the archetype openness panel with current scores."""
    if not self.openness_tracker:
        return

    # Clear existing labels
    for widget in self.openness_frame.winfo_children():
        widget.destroy()

    scores = self.openness_tracker.get_scores()
    sorted_archetypes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    max_score = max(abs(s) for _, s in sorted_archetypes) if sorted_archetypes else 1.0
    if max_score == 0:
        max_score = 1.0

    for i, (name, score) in enumerate(sorted_archetypes):
        name_label = tkinter.Label(
            self.openness_frame,
            text=name,
            anchor=tkinter.W,
            width=15,
        )
        name_label.grid(row=i, column=0, sticky="w", padx=(4, 2))

        score_label = tkinter.Label(
            self.openness_frame,
            text=f"{score:+.1f}",
            anchor=tkinter.E,
            width=6,
        )
        score_label.grid(row=i, column=1, padx=2)

        # Visual bar
        bar_width = int(abs(score) / max_score * 80) if max_score else 0
        bar_color = "#4CAF50" if score > 0 else "#F44336" if score < 0 else "#888888"
        bar_canvas = tkinter.Canvas(
            self.openness_frame, width=80, height=12, highlightthickness=0
        )
        bar_canvas.create_rectangle(0, 0, bar_width, 12, fill=bar_color, outline="")
        bar_canvas.grid(row=i, column=2, padx=(2, 4))

        # Tooltip binding for top contributors
        self._bind_openness_tooltip(name_label, name)
        self._bind_openness_tooltip(score_label, name)
        self._bind_openness_tooltip(bar_canvas, name)


def _bind_openness_tooltip(self, widget, archetype_name):
    """Bind hover tooltip showing top contributing cards for an archetype."""
    def on_enter(event):
        if not self.openness_tracker:
            return
        contributors = self.openness_tracker.get_top_contributors(archetype_name, count=3)
        if not contributors:
            return
        lines = []
        for c in contributors:
            lines.append(f"{c['card_name']}: pick {c['pick_number']}, ATA {c['ata']:.1f} -> {c['signal']:+.1f}")
        tooltip_text = "\n".join(lines)
        self._show_openness_tooltip(event, tooltip_text)

    def on_leave(event):
        self._hide_openness_tooltip()

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


def _show_openness_tooltip(self, event, text):
    """Show a simple tooltip near the cursor."""
    self._openness_tooltip = tkinter.Toplevel()
    self._openness_tooltip.wm_overrideredirect(True)
    self._openness_tooltip.wm_geometry(f"+{event.x_root + 10}+{event.y_root + 10}")
    label = tkinter.Label(
        self._openness_tooltip, text=text, background="#333333",
        foreground="#ffffff", relief="solid", borderwidth=1,
        justify=tkinter.LEFT, padx=4, pady=2,
    )
    label.pack()


def _hide_openness_tooltip(self):
    """Hide the openness tooltip."""
    if hasattr(self, "_openness_tooltip") and self._openness_tooltip:
        self._openness_tooltip.destroy()
        self._openness_tooltip = None
```

**Step 5: Reset tracker on draft reset**

In `__reset_draft` (line 3088), add:

```python
def __reset_draft(self, full_reset):
    self.draft.clear_draft(full_reset)
    if full_reset:
        self.openness_tracker = None
        self.openness_frame.grid_remove()
```

**Step 6: Test manually by running the application**

Run: `python main.py` (on Windows) and verify:
- Panel is hidden when no archetype config exists
- Panel appears when archetype config is present and feature is enabled
- Scores update on each pick

**Step 7: Commit**

```bash
git add src/overlay.py
git commit -m "feat: integrate openness panel into overlay with live score updates"
```

---

### Task 5: Archetype Editor Window

Build the standalone Tkinter editor window for configuring archetypes.

**Files:**
- Create: `src/archetype_editor.py`
- Modify: `src/overlay.py` (add menu entry to open editor)

**Step 1: Create the editor window**

In `src/archetype_editor.py`:

```python
"""Standalone Archetype Editor window for configuring draft archetypes."""

import os
import tkinter
from tkinter import ttk, messagebox
from typing import Optional

from src.archetype_openness import (
    ArchetypeConfig,
    Archetype,
    auto_detect_archetypes,
    calculate_card_weights,
    load_archetype_config,
    save_archetype_config,
)
from src.constants import ARCHETYPES_FOLDER, COLOR_NAMES_DICT, DECK_COLORS, FILTER_OPTION_ALL_DECKS
from src.logger import create_logger

logger = create_logger()


class ArchetypeEditor:
    """Standalone window for editing archetype configurations."""

    def __init__(self, scale_factor, fonts_dict, dataset, set_code, on_save_callback=None):
        """
        Args:
            scale_factor: UI scaling factor
            fonts_dict: fonts dictionary from overlay
            dataset: current Dataset instance
            set_code: current set code (e.g., "OTJ")
            on_save_callback: called after saving, so overlay can reload config
        """
        self.dataset = dataset
        self.set_code = set_code
        self.on_save_callback = on_save_callback
        self.selected_archetype_index = None

        # Load existing config or create empty
        config_path = os.path.join(ARCHETYPES_FOLDER, f"{set_code}_archetypes.json")
        self.config = load_archetype_config(config_path) or ArchetypeConfig(set_code=set_code)

        # Build window
        self.window = tkinter.Toplevel()
        self.window.wm_title(f"Archetype Editor - {set_code}")
        self.window.attributes("-topmost", True)
        self.window.resizable(width=True, height=True)
        self.window.geometry("900x600")

        self._build_ui()
        self._refresh_archetype_list()

    def _build_ui(self):
        """Build the editor UI layout."""
        # Main horizontal panes
        paned = ttk.PanedWindow(self.window, orient=tkinter.HORIZONTAL)
        paned.pack(fill=tkinter.BOTH, expand=True, padx=4, pady=4)

        # --- Left panel: Archetype list ---
        left_frame = ttk.LabelFrame(paned, text="Archetypes")
        paned.add(left_frame, weight=1)

        # Auto-detect controls
        detect_frame = ttk.Frame(left_frame)
        detect_frame.pack(fill=tkinter.X, padx=4, pady=4)

        ttk.Label(detect_frame, text="Threshold %:").pack(side=tkinter.LEFT)
        self.threshold_var = tkinter.StringVar(value=str(self.config.detection_threshold))
        threshold_entry = ttk.Entry(detect_frame, textvariable=self.threshold_var, width=6)
        threshold_entry.pack(side=tkinter.LEFT, padx=4)

        ttk.Button(detect_frame, text="Auto-Detect", command=self._auto_detect).pack(side=tkinter.LEFT, padx=4)

        # Archetype listbox
        self.archetype_listbox = tkinter.Listbox(left_frame, width=25)
        self.archetype_listbox.pack(fill=tkinter.BOTH, expand=True, padx=4, pady=4)
        self.archetype_listbox.bind("<<ListboxSelect>>", self._on_archetype_select)

        # Add/Delete buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tkinter.X, padx=4, pady=4)
        ttk.Button(btn_frame, text="Add Custom", command=self._add_custom_archetype).pack(side=tkinter.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_archetype).pack(side=tkinter.LEFT, padx=2)

        # --- Right panel: Card editor ---
        right_frame = ttk.LabelFrame(paned, text="Cards")
        paned.add(right_frame, weight=3)

        # Archetype name and color pair
        top_frame = ttk.Frame(right_frame)
        top_frame.pack(fill=tkinter.X, padx=4, pady=4)

        ttk.Label(top_frame, text="Name:").pack(side=tkinter.LEFT)
        self.name_var = tkinter.StringVar()
        ttk.Entry(top_frame, textvariable=self.name_var, width=20).pack(side=tkinter.LEFT, padx=4)

        ttk.Label(top_frame, text="Color Pair:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.color_var = tkinter.StringVar()
        color_options = ["None"] + [c for c in DECK_COLORS if c != FILTER_OPTION_ALL_DECKS]
        self.color_combo = ttk.Combobox(top_frame, textvariable=self.color_var, values=color_options, width=8, state="readonly")
        self.color_combo.pack(side=tkinter.LEFT, padx=4)

        self.auto_weights_var = tkinter.BooleanVar(value=True)
        ttk.Checkbutton(top_frame, text="Auto Weights", variable=self.auto_weights_var).pack(side=tkinter.LEFT, padx=8)

        ttk.Button(top_frame, text="Recalculate", command=self._recalculate_weights).pack(side=tkinter.LEFT, padx=4)

        # Card table
        columns = ("card_name", "weight", "ata")
        self.card_tree = ttk.Treeview(right_frame, columns=columns, show="headings", height=20)
        self.card_tree.heading("card_name", text="Card Name")
        self.card_tree.heading("weight", text="Weight")
        self.card_tree.heading("ata", text="ATA")
        self.card_tree.column("card_name", width=250)
        self.card_tree.column("weight", width=80)
        self.card_tree.column("ata", width=80)
        self.card_tree.pack(fill=tkinter.BOTH, expand=True, padx=4, pady=4)

        # Card editing buttons
        card_btn_frame = ttk.Frame(right_frame)
        card_btn_frame.pack(fill=tkinter.X, padx=4, pady=4)

        ttk.Label(card_btn_frame, text="Add card:").pack(side=tkinter.LEFT)
        self.add_card_var = tkinter.StringVar()
        self.add_card_entry = ttk.Entry(card_btn_frame, textvariable=self.add_card_var, width=25)
        self.add_card_entry.pack(side=tkinter.LEFT, padx=4)
        ttk.Button(card_btn_frame, text="Add", command=self._add_card).pack(side=tkinter.LEFT, padx=2)
        ttk.Button(card_btn_frame, text="Remove Selected", command=self._remove_card).pack(side=tkinter.LEFT, padx=2)

        # Enable editing weight on double-click
        self.card_tree.bind("<Double-1>", self._on_card_double_click)

        # --- Bottom bar: Global settings ---
        bottom_frame = ttk.Frame(self.window)
        bottom_frame.pack(fill=tkinter.X, padx=4, pady=8)

        ttk.Label(bottom_frame, text="Scoring:").pack(side=tkinter.LEFT)
        self.scoring_var = tkinter.StringVar(value=self.config.scoring_method)
        scoring_combo = ttk.Combobox(bottom_frame, textvariable=self.scoring_var,
                                      values=["simple", "normalized"], width=12, state="readonly")
        scoring_combo.pack(side=tkinter.LEFT, padx=4)

        ttk.Label(bottom_frame, text="Pack Weights:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.pack_weight_vars = []
        for i, w in enumerate(self.config.pack_weights):
            ttk.Label(bottom_frame, text=f"P{i+1}:").pack(side=tkinter.LEFT, padx=(4, 0))
            var = tkinter.StringVar(value=str(w))
            self.pack_weight_vars.append(var)
            ttk.Entry(bottom_frame, textvariable=var, width=5).pack(side=tkinter.LEFT, padx=2)

        ttk.Button(bottom_frame, text="Save", command=self._save).pack(side=tkinter.RIGHT, padx=4)
        ttk.Button(bottom_frame, text="Reset to Auto", command=self._reset_to_auto).pack(side=tkinter.RIGHT, padx=4)

    def _refresh_archetype_list(self):
        """Refresh the archetype listbox from config."""
        self.archetype_listbox.delete(0, tkinter.END)
        for arch in self.config.archetypes:
            display = f"{arch.name} ({len(arch.cards)} cards)"
            self.archetype_listbox.insert(tkinter.END, display)

    def _on_archetype_select(self, event):
        """Load selected archetype into the card editor."""
        selection = self.archetype_listbox.curselection()
        if not selection:
            return
        self.selected_archetype_index = selection[0]
        arch = self.config.archetypes[self.selected_archetype_index]

        self.name_var.set(arch.name)
        self.color_var.set(arch.color_pair or "None")
        self.auto_weights_var.set(arch.auto_weights)

        self._refresh_card_table(arch)

    def _refresh_card_table(self, archetype):
        """Refresh the card table for the given archetype."""
        for row in self.card_tree.get_children():
            self.card_tree.delete(row)

        # Get ATA values from dataset
        from src.constants import DATA_FIELD_DECK_COLORS, DATA_FIELD_ATA, DATA_FIELD_NAME
        card_ratings = self.dataset._dataset.get("card_ratings", {}) if self.dataset._dataset else {}

        ata_lookup = {}
        for card_id, card in card_ratings.items():
            name = card.get(DATA_FIELD_NAME, "")
            all_decks = card.get(DATA_FIELD_DECK_COLORS, {}).get(FILTER_OPTION_ALL_DECKS, {})
            ata_lookup[name] = all_decks.get(DATA_FIELD_ATA, 0.0)

        sorted_cards = sorted(archetype.cards.items(), key=lambda x: x[1], reverse=True)
        for card_name, weight in sorted_cards:
            ata = ata_lookup.get(card_name, 0.0)
            self.card_tree.insert("", tkinter.END, values=(card_name, f"{weight:.2f}", f"{ata:.1f}"))

    def _auto_detect(self):
        """Run auto-detection and populate archetypes."""
        try:
            threshold = float(self.threshold_var.get())
        except ValueError:
            messagebox.showerror("Error", "Threshold must be a number")
            return

        archetypes = auto_detect_archetypes(self.dataset, threshold)
        self.config.archetypes = archetypes
        self.config.detection_threshold = threshold
        self._refresh_archetype_list()
        self.selected_archetype_index = None

    def _add_custom_archetype(self):
        """Add a new empty custom archetype."""
        name = f"Custom {len(self.config.archetypes) + 1}"
        arch = Archetype(name=name, auto_weights=False)
        self.config.archetypes.append(arch)
        self._refresh_archetype_list()
        self.archetype_listbox.selection_set(len(self.config.archetypes) - 1)
        self._on_archetype_select(None)

    def _delete_archetype(self):
        """Delete the selected archetype."""
        if self.selected_archetype_index is None:
            return
        del self.config.archetypes[self.selected_archetype_index]
        self.selected_archetype_index = None
        self._refresh_archetype_list()
        for row in self.card_tree.get_children():
            self.card_tree.delete(row)

    def _add_card(self):
        """Add a card to the selected archetype."""
        if self.selected_archetype_index is None:
            return
        card_name = self.add_card_var.get().strip()
        if not card_name:
            return
        arch = self.config.archetypes[self.selected_archetype_index]
        if card_name not in arch.cards:
            arch.cards[card_name] = 0.5
        self.add_card_var.set("")
        self._refresh_card_table(arch)
        self._refresh_archetype_list()

    def _remove_card(self):
        """Remove selected card from the archetype."""
        if self.selected_archetype_index is None:
            return
        selection = self.card_tree.selection()
        if not selection:
            return
        arch = self.config.archetypes[self.selected_archetype_index]
        for item in selection:
            card_name = self.card_tree.item(item)["values"][0]
            arch.cards.pop(str(card_name), None)
        self._refresh_card_table(arch)
        self._refresh_archetype_list()

    def _on_card_double_click(self, event):
        """Edit card weight on double-click."""
        if self.selected_archetype_index is None:
            return
        item = self.card_tree.identify_row(event.y)
        column = self.card_tree.identify_column(event.x)
        if not item or column != "#2":  # Only edit weight column
            return

        # Get current values
        values = self.card_tree.item(item)["values"]
        card_name = str(values[0])

        # Create inline edit
        bbox = self.card_tree.bbox(item, column)
        if not bbox:
            return
        entry = ttk.Entry(self.card_tree, width=8)
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.insert(0, str(values[1]))
        entry.select_range(0, tkinter.END)
        entry.focus()

        def on_confirm(e=None):
            try:
                new_weight = float(entry.get())
                new_weight = max(0.0, min(1.0, new_weight))
                arch = self.config.archetypes[self.selected_archetype_index]
                arch.cards[card_name] = round(new_weight, 4)
                self._refresh_card_table(arch)
            except ValueError:
                pass
            entry.destroy()

        entry.bind("<Return>", on_confirm)
        entry.bind("<FocusOut>", on_confirm)

    def _recalculate_weights(self):
        """Recalculate weights from 17Lands data for selected archetype."""
        if self.selected_archetype_index is None:
            return
        arch = self.config.archetypes[self.selected_archetype_index]
        if not arch.color_pair:
            messagebox.showinfo("Info", "Set a color pair to auto-calculate weights")
            return
        arch.cards = calculate_card_weights(self.dataset, arch.color_pair)
        arch.auto_weights = True
        self._refresh_card_table(arch)
        self._refresh_archetype_list()

    def _save(self):
        """Save current config to file and update archetype names/settings from UI."""
        # Update selected archetype from UI fields
        if self.selected_archetype_index is not None:
            arch = self.config.archetypes[self.selected_archetype_index]
            arch.name = self.name_var.get()
            color = self.color_var.get()
            arch.color_pair = None if color == "None" else color
            arch.auto_weights = self.auto_weights_var.get()

        # Update global settings
        self.config.scoring_method = self.scoring_var.get()
        try:
            self.config.pack_weights = [float(v.get()) for v in self.pack_weight_vars]
        except ValueError:
            messagebox.showerror("Error", "Pack weights must be numbers")
            return

        config_path = os.path.join(ARCHETYPES_FOLDER, f"{self.set_code}_archetypes.json")
        if save_archetype_config(self.config, config_path):
            self._refresh_archetype_list()
            if self.on_save_callback:
                self.on_save_callback()
        else:
            messagebox.showerror("Error", "Failed to save archetype config")

    def _reset_to_auto(self):
        """Reset everything to auto-detected archetypes."""
        self._auto_detect()
        self._save()
```

**Step 2: Add menu entry in `overlay.py`**

In the menu creation section (near line 316), add to the Cards menu:

```python
self.cardmenu.add_command(
    label="Archetype Editor", command=self.__open_archetype_editor)
```

Add the method to the overlay class:

```python
def __open_archetype_editor(self):
    """Open the Archetype Editor window."""
    set_code = ""
    if self.draft.draft_sets:
        set_code = self.draft.draft_sets[0]
    if not set_code:
        messagebox.showinfo("Info", "Start a draft first to configure archetypes for the current set.")
        return

    def on_save():
        """Reload archetype config after save."""
        if self.configuration.features.archetype_openness_enabled:
            config_path = os.path.join(constants.ARCHETYPES_FOLDER, f"{set_code}_archetypes.json")
            archetype_config = load_archetype_config(config_path)
            if archetype_config:
                self.openness_tracker = OpennessTracker(archetype_config)

    from src.archetype_editor import ArchetypeEditor
    ArchetypeEditor(
        self.scale_factor,
        self.fonts_dict,
        self.draft.set_data,
        set_code,
        on_save_callback=on_save,
    )
```

**Step 3: Test manually**

Run: `python main.py` (on Windows)
- Start a draft
- Open Cards -> Archetype Editor
- Click Auto-Detect — verify archetypes populate
- Select an archetype — verify cards and weights appear
- Edit a weight by double-clicking — verify it saves
- Click Save — verify JSON file created in `Archetypes/`
- Close and reopen editor — verify config persists

**Step 4: Commit**

```bash
git add src/archetype_editor.py src/overlay.py
git commit -m "feat: add Archetype Editor window with auto-detect and manual editing"
```

---

### Task 6: Add `Archetypes/` to `.gitignore`

Archetype configs are user-specific and set-specific — they shouldn't be committed.

**Files:**
- Modify: `.gitignore`

**Step 1: Add the directory**

Add to `.gitignore`:

```
Archetypes/
```

**Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add Archetypes/ to gitignore"
```

---

### Task 7: End-to-End Integration Test

Write a test that exercises the full flow: auto-detect -> create tracker -> record packs -> verify scores.

**Files:**
- Modify: `tests/test_archetype_openness.py`

**Step 1: Write the integration test**

Append to `tests/test_archetype_openness.py`:

```python
class TestEndToEnd:
    """Integration test using real OTJ dataset."""

    def test_full_flow_with_real_data(self, otj_dataset):
        """Auto-detect archetypes, create tracker, record a pack, verify scores."""
        # Auto-detect
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        assert len(archetypes) > 0

        # Create config and tracker
        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="simple",
            pack_weights=[1.0, 1.0, 1.0],
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        # Get some real cards from the dataset
        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        # Record pack at pick 5
        tracker.record_pack(pack_cards, pick_number=5, pack_number=0)

        # Verify scores exist for all archetypes
        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)
        # At least some archetypes should have non-zero scores
        assert any(s != 0.0 for s in scores.values())

    def test_normalized_with_real_data(self, otj_dataset):
        """Same flow with normalized scoring."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="normalized",
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        tracker.record_pack(pack_cards, pick_number=5, pack_number=0)

        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)
```

**Step 2: Run all tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All tests PASS

**Step 3: Run full test suite to check for regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add tests/test_archetype_openness.py
git commit -m "test: add end-to-end integration test with real OTJ dataset"
```
