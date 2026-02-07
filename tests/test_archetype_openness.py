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


from src.archetype_openness import auto_detect_archetypes, calculate_card_weights, OpennessTracker, Archetype
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
    assert len(archetypes) > 0
    assert len(archetypes) < 25
    for arch in archetypes:
        assert arch.name
        assert arch.color_pair


def test_auto_detect_with_zero_threshold_returns_all(otj_dataset):
    """Threshold of 0 returns all color pairs that have any games."""
    archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=0.0)
    assert len(archetypes) > 10


def test_auto_detect_with_100_threshold_returns_none(otj_dataset):
    """Threshold of 100 returns no archetypes."""
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


# --- Task 2: OpennessTracker tests ---

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
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=3.0)]
        tracker.record_pack(pack, pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(3.6, abs=0.01)

    def test_single_card_negative_signal(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=7.0)]
        tracker.record_pack(pack, pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(-3.6, abs=0.01)

    def test_multi_archetype_card(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Murder", ata=4.0)]
        tracker.record_pack(pack, pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(0.8, abs=0.01)
        assert scores["UB Control"] == pytest.approx(2.8, abs=0.01)

    def test_card_not_in_any_archetype(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Random Card", ata=5.0)]
        tracker.record_pack(pack, pick_number=10, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == 0.0
        assert scores["UB Control"] == 0.0

    def test_accumulation_across_packs(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.record_pack([_make_card("Llanowar Elves", ata=5.0)], pick_number=9, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(5.6, abs=0.01)

    def test_pack_weights_applied(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="simple",
            pack_weights=[1.0, 0.5, 0.75],
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=1)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == pytest.approx(1.8, abs=0.01)

    def test_reset_clears_signals(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.reset()
        scores = tracker.get_scores()
        assert scores["BG Elves"] == 0.0

    def test_empty_pack(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"] == 0.0


class TestOpennessTrackerNormalized:
    """Tests for normalized scoring: signal = ((pick - ATA) / ATA) * weight * pack_weight."""

    def test_normalized_scoring(self):
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
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            archetypes=[Archetype(name="Test", cards={"Early": 1.0, "Late": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Early", ata=2.0)], pick_number=6, pack_number=0)
        tracker.record_pack([_make_card("Late", ata=8.0)], pick_number=12, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"] == pytest.approx(2.5, abs=0.01)

    def test_normalized_zero_ata_skipped(self):
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
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([
            _make_card("Elf Lord", ata=2.0),
            _make_card("Llanowar Elves", ata=4.0),
            _make_card("Murder", ata=3.0),
        ], pick_number=7, pack_number=0)
        top = tracker.get_top_contributors("BG Elves", count=2)
        assert len(top) == 2
        assert top[0]["card_name"] == "Elf Lord"
        assert top[1]["card_name"] == "Llanowar Elves"

    def test_empty_archetype_returns_empty(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        top = tracker.get_top_contributors("BG Elves", count=3)
        assert top == []


# --- Task 7: End-to-end integration tests ---

class TestEndToEnd:
    """Integration test using real OTJ dataset."""

    def test_full_flow_with_real_data(self, otj_dataset):
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        assert len(archetypes) > 0

        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="simple",
            pack_weights=[1.0, 1.0, 1.0],
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        tracker.record_pack(pack_cards, pick_number=5, pack_number=0)

        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)
        assert any(s != 0.0 for s in scores.values())

    def test_normalized_with_real_data(self, otj_dataset):
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
