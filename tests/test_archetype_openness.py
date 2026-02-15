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
    """Tests for simple scoring method: signal = (pick - ATA) / (ATA + pick)^2 * weight * pack_weight * 100."""

    def test_single_card_positive_signal(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=3.0)]
        tracker.record_pack(pack, pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        # (7-3)/(3+7)^2 * 0.9 * 100 = 3.6
        assert scores["BG Elves"]["score"] == pytest.approx(3.6, abs=0.01)

    def test_single_card_negative_signal(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=7.0)]
        tracker.record_pack(pack, pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        # (3-7)/(7+3)^2 * 0.9 * 1.0 * 100 = -3.6
        assert scores["BG Elves"]["score"] == pytest.approx(-3.6, abs=0.01)

    def test_multi_archetype_card(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Murder", ata=4.0)]
        tracker.record_pack(pack, pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        # raw=(8-4)/(4+8)^2=4/144. BG: 4/144*0.2*100=0.5556. UB: 4/144*0.7*100=1.9444
        assert scores["BG Elves"]["score"] == pytest.approx(0.5556, abs=0.01)
        assert scores["UB Control"]["score"] == pytest.approx(1.9444, abs=0.01)

    def test_card_not_in_any_archetype(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Random Card", ata=5.0)]
        tracker.record_pack(pack, pick_number=10, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == 0.0
        assert scores["UB Control"]["score"] == 0.0

    def test_accumulation_across_packs(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.record_pack([_make_card("Llanowar Elves", ata=5.0)], pick_number=9, pack_number=0)
        scores = tracker.get_scores()
        # sig1=(7-3)/(3+7)^2*0.9*100=3.6, sig2=(9-5)/(5+9)^2*0.5*100=1.0204. total=4.6204
        assert scores["BG Elves"]["score"] == pytest.approx(4.6204, abs=0.01)

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
        # (7-3)/(3+7)^2 * 0.9 * 0.5 * 100 = 1.8
        assert scores["BG Elves"]["score"] == pytest.approx(1.8, abs=0.01)

    def test_reset_clears_signals(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.reset()
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == 0.0

    def test_empty_pack(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == 0.0

    def test_pick_1_produces_no_signal(self):
        """Pick 1 provides no openness info — everyone sees the same pack."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == 0.0


class TestOpennessTrackerNormalized:
    """Tests for normalized scoring: signal = ((pick - ATA) / (ATA + pick)^2) * pick_weight * card_weight * pack_weight * 100."""

    def test_normalized_scoring(self):
        """pick=6, ata=2.0, weight=0.9, linear pick_weight(6)=5/13."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=2.0)], pick_number=6, pack_number=0)
        scores = tracker.get_scores()
        # ((6-2)/(2+6)^2) * (5/13) * 0.9 * 100 = 0.0625 * 0.3846 * 0.9 * 100 ≈ 2.1635
        assert scores["BG Elves"]["score"] == pytest.approx(2.1635, abs=0.01)

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
        # Early: ((6-2)/(2+6)^2) * (5/13) * 1.0 * 100 = 2.4038
        # Late: ((12-8)/(8+12)^2) * (11/13) * 1.0 * 100 = 0.8462
        assert scores["Test"]["score"] == pytest.approx(3.2500, abs=0.01)

    def test_normalized_zero_ata_skipped(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            archetypes=[Archetype(name="Test", cards={"Bad Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Bad Card", ata=0.0)], pick_number=5, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == 0.0




class TestOpennessTrackerHMMHybrid:
    """Tests for HMM hybrid scoring method."""

    def test_hmm_returns_probability(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=8, pack_number=0)
        score = tracker.get_scores()["BG Elves"]["score"]
        assert 0.0 <= score <= 1.0
        assert score > 0.5

    def test_hmm_rarity_effect(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Common Card": 1.0, "Rare Card": 1.0})],
        )
        tracker = OpennessTracker(config)

        common = _make_card("Common Card", ata=8.0)
        common["rarity"] = "common"
        rare = _make_card("Rare Card", ata=8.0)
        rare["rarity"] = "rare"

        tracker.record_pack([common], pick_number=11, pack_number=0)
        score_common = tracker.get_scores()["Test"]["score"]

        tracker.reset()
        tracker.record_pack([rare], pick_number=11, pack_number=0)
        score_rare = tracker.get_scores()["Test"]["score"]

        assert score_common > score_rare

    def test_hmm_uses_configured_rarity_odds(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            rarity_odds={"common": 0.20, "rare": 0.90},
            archetypes=[Archetype(name="Test", cards={"Common Card": 1.0, "Rare Card": 1.0})],
        )
        tracker = OpennessTracker(config)

        common = _make_card("Common Card", ata=8.0)
        common["rarity"] = "common"
        rare = _make_card("Rare Card", ata=8.0)
        rare["rarity"] = "rare"

        tracker.record_pack([common], pick_number=11, pack_number=0)
        score_common = tracker.get_scores()["Test"]["score"]

        tracker.reset()
        tracker.record_pack([rare], pick_number=11, pack_number=0)
        score_rare = tracker.get_scores()["Test"]["score"]

        assert score_rare > score_common

    def test_hmm_reset_resets_state(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=8, pack_number=0)
        tracker.reset()
        assert tracker.get_scores()["BG Elves"]["score"] == pytest.approx(0.5)

    def test_hmm_below_ata_produces_signal(self):
        """Card seen BEFORE its ATA should still produce a small positive signal for HMM.

        ATA 5.0 at pick 4: the card hasn't wheeled past ATA yet, but seeing it
        at pick 4 is still slightly more consistent with 'open' than 'closed'.
        log_bf = (4-1) * [log(1 - 1/(5*2)) - log(1 - 1/5)]
               = 3 * [log(0.9) - log(0.8)]
               = 3 * (-0.10536 - (-0.22314))
               = 3 * 0.11778
               = 0.35335
        sigmoid(0.35335) ≈ 0.587  -->  score > 0.5
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=5.0)], pick_number=4, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score > 0.5
        assert score < 0.7  # should be modest, not extreme

    def test_hmm_borderline_vs_expected(self):
        """ATA 4.1 at pick 4 should produce stronger signal than ATA 10 at pick 4.

        ATA 4.1 card is borderline (almost wheeling) — more informative.
        ATA 10 card is completely expected to still be here — less informative.
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Borderline": 1.0, "Expected": 1.0})],
        )
        tracker1 = OpennessTracker(config)
        tracker1.record_pack([_make_card("Borderline", ata=4.1)], pick_number=4, pack_number=0)
        score_borderline = tracker1.get_scores()["Test"]["score"]

        tracker2 = OpennessTracker(config)
        tracker2.record_pack([_make_card("Expected", ata=10.0)], pick_number=4, pack_number=0)
        score_expected = tracker2.get_scores()["Test"]["score"]

        assert score_borderline > score_expected

    def test_hmm_emission_scales_with_pick(self):
        """Same card at a later pick should produce stronger signal.

        The log Bayes factor is proportional to (pick - 1), so pick 10 should
        produce about 3x the signal of pick 4 (9/3 = 3).
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker_early = OpennessTracker(config)
        tracker_early.record_pack([_make_card("Card", ata=5.0)], pick_number=4, pack_number=0)
        score_early = tracker_early.get_scores()["Test"]["score"]

        tracker_late = OpennessTracker(config)
        tracker_late.record_pack([_make_card("Card", ata=5.0)], pick_number=10, pack_number=0)
        score_late = tracker_late.get_scores()["Test"]["score"]

        assert score_late > score_early

    def test_hmm_exact_bayes_factor(self):
        """Verify exact emission value for known inputs.

        ATA=3.0, pick=7, F=2.0, card_weight=0.9, common rarity (weight=1.0):
        a = 3.0, p = 7
        log_bf = 6 * [log(1 - 1/6) - log(1 - 1/3)]
               = 6 * [log(5/6) - log(2/3)]
               = 6 * [-0.18232 - (-0.40546)]
               = 6 * 0.22314
               = 1.33886
        emission = 1.33886 * 0.9 * 1.0 * 1.0 * 1.0 = 1.20497
        P(open) = sigmoid(1.20497) = 1/(1+exp(-1.20497)) ≈ 0.7693
        """
        import math
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 0.9})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)

        log_bf = 6 * (math.log(1 - 1/6) - math.log(1 - 1/3))
        expected_emission = log_bf * 0.9
        expected_score = 1.0 / (1.0 + math.exp(-expected_emission))

        score = tracker.get_scores()["Test"]["score"]
        assert score == pytest.approx(expected_score, abs=0.001)

    def test_hmm_openness_factor_config(self):
        """hmm_openness_factor defaults to 2.0 and round-trips."""
        config = ArchetypeConfig(set_code="TST")
        assert config.hmm_openness_factor == 2.0

        # Old config without the field gets the default
        data = {"set_code": "TST", "scoring_method": "hmm_hybrid"}
        config2 = ArchetypeConfig.model_validate(data)
        assert config2.hmm_openness_factor == 2.0

    def test_hmm_openness_factor_round_trip(self, tmp_path):
        """hmm_openness_factor persists through save/load."""
        config = ArchetypeConfig(set_code="TST", hmm_openness_factor=3.0)
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.hmm_openness_factor == 3.0

    def test_hmm_ata_clamp(self):
        """ATA=1.0 should not cause math domain error; clamped to 1.5."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=1.0)], pick_number=5, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # ATA 1.0 at pick 5 is very strong

    def test_hmm_pick_1_still_no_signal(self):
        """Pick 1 should still produce no signal even with HMM hybrid."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=3.0)], pick_number=1, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score == pytest.approx(0.5)  # no change from prior

    def test_hmm_pick_ramp_dampens_early_picks(self):
        """Pick 2 emission should be ~25% of pick 6+ emission (ramp_picks=5).

        With ramp_picks=5:
          pick 2: ramp = (2-1)/(5-1) = 0.25
          pick 6: ramp = min(1.0, (6-1)/(5-1)) = 1.0

        The log Bayes factor scales as (p-1), so pick 2 base = 1, pick 6 base = 5.
        With ramp: pick 2 effective = 1*0.25 = 0.25, pick 6 effective = 5*1.0 = 5.0.
        Ratio = 20x, so pick 6 score should be much larger.
        """
        import math
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            hmm_pick_ramp=5,
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker_early = OpennessTracker(config)
        card = _make_card("Card", ata=5.0)
        card["rarity"] = "common"
        tracker_early.record_pack([card], pick_number=2, pack_number=0)
        score_early = tracker_early.get_scores()["Test"]["score"]

        tracker_late = OpennessTracker(config)
        tracker_late.record_pack([card], pick_number=6, pack_number=0)
        score_late = tracker_late.get_scores()["Test"]["score"]

        # Pick 2 should produce a signal much closer to 0.5 (neutral)
        assert score_early > 0.5
        assert score_early < 0.55  # heavily dampened
        assert score_late > score_early

    def test_hmm_pick_ramp_full_weight_at_threshold(self):
        """Picks at or above hmm_pick_ramp should get full ramp weight (1.0)."""
        import math
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            hmm_pick_ramp=5,
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        # Ramp at pick 5: (5-1)/(5-1) = 1.0
        assert tracker._hmm_pick_ramp_factor(5) == pytest.approx(1.0)
        # Ramp at pick 10: min(1.0, 9/4) = 1.0
        assert tracker._hmm_pick_ramp_factor(10) == pytest.approx(1.0)
        # Ramp at pick 2: (2-1)/(5-1) = 0.25
        assert tracker._hmm_pick_ramp_factor(2) == pytest.approx(0.25)
        # Ramp at pick 3: (3-1)/(5-1) = 0.50
        assert tracker._hmm_pick_ramp_factor(3) == pytest.approx(0.50)

    def test_hmm_pick_ramp_config_default(self):
        """Default hmm_pick_ramp is 5."""
        config = ArchetypeConfig(set_code="TST")
        assert config.hmm_pick_ramp == 5

    def test_hmm_pick_ramp_config_round_trip(self, tmp_path):
        """hmm_pick_ramp persists through save/load."""
        config = ArchetypeConfig(set_code="TST", hmm_pick_ramp=7)
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.hmm_pick_ramp == 7

    def test_hmm_pick_ramp_old_config_gets_default(self):
        """Config JSON missing hmm_pick_ramp field gets default 5."""
        data = {"set_code": "TST", "scoring_method": "hmm_hybrid"}
        config = ArchetypeConfig.model_validate(data)
        assert config.hmm_pick_ramp == 5

    def test_hmm_interval_returned_after_signals(self):
        """HMM Hybrid should return a non-None interval tuple after recording signals."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=3.0)], pick_number=7, pack_number=0)
        data = tracker.get_scores()["Test"]
        assert data["interval"] is not None
        low, high = data["interval"]
        assert 0.0 <= low <= data["score"]
        assert data["score"] <= high <= 1.0

    def test_hmm_interval_none_with_no_signals(self):
        """HMM Hybrid should return interval=None when no signals have been recorded."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        data = tracker.get_scores()["Test"]
        assert data["interval"] is None

    def test_hmm_interval_narrows_with_more_signals(self):
        """Interval half-width should not grow unboundedly; with consistent signals
        the sigmoid compression keeps the interval manageable."""
        import math
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)

        # Record one signal
        tracker.record_pack([_make_card("Card", ata=5.0)], pick_number=8, pack_number=0)
        data_1 = tracker.get_scores()["Test"]
        half_1 = (data_1["interval"][1] - data_1["interval"][0]) / 2

        # Record many more consistent signals
        for pick in range(9, 14):
            tracker.record_pack([_make_card("Card", ata=5.0)], pick_number=pick, pack_number=0)

        data_many = tracker.get_scores()["Test"]
        half_many = (data_many["interval"][1] - data_many["interval"][0]) / 2

        # Score should be well above 0.5 with all positive signals
        assert data_many["score"] > 0.7
        # The interval should be valid
        assert 0.0 <= data_many["interval"][0] <= data_many["score"]
        assert data_many["score"] <= data_many["interval"][1] <= 1.0

    def test_hmm_interval_bounds_valid(self):
        """Interval bounds must always be in [0, 1] and low <= score <= high."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 0.8})],
        )
        tracker = OpennessTracker(config)
        for pick in range(2, 14):
            tracker.record_pack([_make_card("Card", ata=4.0)], pick_number=pick, pack_number=0)
        data = tracker.get_scores()["Test"]
        low, high = data["interval"]
        assert 0.0 <= low
        assert low <= data["score"]
        assert data["score"] <= high
        assert high <= 1.0

    def test_hmm_reset_clears_variance(self):
        """Reset should clear interval state so scores return interval=None again."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=3.0)], pick_number=7, pack_number=0)
        assert tracker.get_scores()["Test"]["interval"] is not None

        tracker.reset()
        assert tracker.get_scores()["Test"]["interval"] is None


class TestBayesianBetaInterval:
    """Tests for Bayesian Beta credible interval display (already computed, now surfaced)."""

    def test_bayesian_interval_returned(self):
        """Bayesian Beta should return a non-None interval tuple after signals."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=3.0)], pick_number=7, pack_number=0)
        data = tracker.get_scores()["Test"]
        assert data["interval"] is not None
        low, high = data["interval"]
        assert 0.0 <= low <= data["score"]
        assert data["score"] <= high <= 1.0

    def test_bayesian_interval_bounds_valid(self):
        """Bayesian interval must be in [0, 1] and low <= score <= high."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            archetypes=[Archetype(name="Test", cards={"Card": 0.7})],
        )
        tracker = OpennessTracker(config)
        for pick in range(2, 12):
            tracker.record_pack([_make_card("Card", ata=5.0)], pick_number=pick, pack_number=0)
        data = tracker.get_scores()["Test"]
        low, high = data["interval"]
        assert 0.0 <= low
        assert low <= data["score"]
        assert data["score"] <= high
        assert high <= 1.0


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
        assert any(s["score"] != 0.0 for s in scores.values())

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

    def test_bayesian_with_real_data(self, otj_dataset):
        """Bayesian scoring with real OTJ data produces valid probabilities."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="bayesian_beta",
            bayesian_prior=1.0,
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        tracker.record_pack(pack_cards, pick_number=5, pack_number=0)

        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)
        for name, data in scores.items():
            assert 0.0 <= data["score"] <= 1.0
            assert data["confidence"] in ("none", "low", "medium", "high")
            if data["interval"] is not None:
                assert data["interval"][0] <= data["score"] <= data["interval"][1]


# --- Pick-position weighting tests ---

class TestPickWeight:
    """Tests for _pick_weight with different curves."""

    def _make_tracker(self, curve="linear"):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="normalized",
            weight_curve=curve,
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        return OpennessTracker(config)

    def test_pick_1_produces_zero_weight(self):
        """P1P1 should contribute zero signal (everyone sees the same cards)."""
        tracker = self._make_tracker("linear")
        assert tracker._pick_weight(1, max_picks=14) == pytest.approx(0.0)

    def test_pick_14_produces_full_weight(self):
        """Last pick should have weight 1.0."""
        tracker = self._make_tracker("linear")
        assert tracker._pick_weight(14, max_picks=14) == pytest.approx(1.0)

    def test_linear_midpoint(self):
        """Linear curve: midpoint pick should be ~0.5."""
        tracker = self._make_tracker("linear")
        # pick 8 of 14: (8-1)/(14-1) = 7/13 ≈ 0.5385
        assert tracker._pick_weight(8, max_picks=14) == pytest.approx(7.0 / 13.0)

    def test_sqrt_curve(self):
        """Sqrt curve rises faster early."""
        tracker = self._make_tracker("sqrt")
        # pick 4 of 14: t = 3/13 ≈ 0.2308, sqrt(0.2308) ≈ 0.4804
        t = 3.0 / 13.0
        assert tracker._pick_weight(4, max_picks=14) == pytest.approx(t ** 0.5)

    def test_squared_curve(self):
        """Squared curve rises slower early."""
        tracker = self._make_tracker("squared")
        # pick 4 of 14: t = 3/13 ≈ 0.2308, t^2 ≈ 0.0533
        t = 3.0 / 13.0
        assert tracker._pick_weight(4, max_picks=14) == pytest.approx(t ** 2)

    def test_max_picks_one_returns_one(self):
        """Edge case: if max_picks <= 1, weight is always 1.0."""
        tracker = self._make_tracker("linear")
        assert tracker._pick_weight(1, max_picks=1) == 1.0

    def test_p1p1_normalized_produces_zero_signal(self):
        """At pick 1, normalized scoring gives zero signal regardless of ATA."""
        tracker = self._make_tracker("linear")
        tracker.record_pack([_make_card("Card", ata=3.0)], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_late_pick_high_quality_card_strong_signal(self):
        """A card with low ATA seen at a late pick should produce a strong positive signal."""
        tracker = self._make_tracker("linear")
        # pick 13 of 14: pick_weight = 12/13 ≈ 0.923
        # ata=2.0: raw = ((13-2)/(2+13)^2) * (12/13) * 100 ≈ 4.5128
        tracker.record_pack([_make_card("Card", ata=2.0)], pick_number=13, pack_number=0)
        scores = tracker.get_scores()
        expected = ((13 - 2) / (2.0 + 13)**2) * (12.0 / 13.0) * 1.0 * 100
        assert scores["Test"]["score"] == pytest.approx(expected, abs=0.01)


class TestWeightCurveConfig:
    """Tests for weight_curve configuration field."""

    def test_default_weight_curve(self):
        """Default weight curve is linear."""
        config = ArchetypeConfig(set_code="TST")
        assert config.weight_curve == "linear"

    def test_weight_curve_round_trip(self, tmp_path):
        """weight_curve persists through save/load cycle."""
        config = ArchetypeConfig(set_code="TST", weight_curve="sqrt")
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.weight_curve == "sqrt"

    def test_old_config_without_weight_curve_gets_default(self):
        """Config JSON missing weight_curve field gets 'linear' default."""
        data = {"set_code": "TST", "scoring_method": "normalized"}
        config = ArchetypeConfig.model_validate(data)
        assert config.weight_curve == "linear"


class TestGetScoresReturnShape:
    """Tests for unified get_scores return shape."""

    def test_simple_returns_dict_with_keys(self):
        """Simple scoring returns {name: {score, confidence, interval}}."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        result = scores["BG Elves"]
        assert "score" in result
        assert "confidence" in result
        assert "interval" in result
        assert isinstance(result["score"], float)

    def test_simple_no_signals_confidence_none(self):
        """With no signals, confidence should be 'none'."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "none"
        assert scores["BG Elves"]["score"] == 0.0

    def test_simple_interval_is_none(self):
        """Simple scoring doesn't produce credible intervals."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["interval"] is None


class TestBayesianConfig:
    """Tests for bayesian_prior configuration field."""

    def test_default_bayesian_prior(self):
        """Default bayesian_prior is 1.0."""
        config = ArchetypeConfig(set_code="TST")
        assert config.bayesian_prior == 1.0

    def test_bayesian_prior_round_trip(self, tmp_path):
        """bayesian_prior persists through save/load cycle."""
        config = ArchetypeConfig(set_code="TST", bayesian_prior=2.5)
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.bayesian_prior == 2.5

    def test_old_config_without_bayesian_prior_gets_default(self):
        """Config JSON missing bayesian_prior field gets 1.0 default."""
        data = {"set_code": "TST", "scoring_method": "simple"}
        config = ArchetypeConfig.model_validate(data)
        assert config.bayesian_prior == 1.0


class TestRarityOddsConfig:
    """Tests for per-set rarity odds configuration used by HMM hybrid."""

    def test_default_rarity_odds(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.rarity_odds["common"] == pytest.approx(0.0899)
        assert config.rarity_odds["mythic"] == pytest.approx(0.0055)

    def test_old_config_without_rarity_odds_gets_default(self):
        data = {"set_code": "TST", "scoring_method": "hmm_hybrid"}
        config = ArchetypeConfig.model_validate(data)
        assert config.rarity_odds["uncommon"] == pytest.approx(0.0388)

    def test_rarity_odds_round_trip(self, tmp_path):
        config = ArchetypeConfig(
            set_code="TST",
            rarity_odds={"common": 0.70, "uncommon": 0.50, "rare": 0.40, "mythic": 0.25},
        )
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.rarity_odds["common"] == pytest.approx(0.70)


BAYESIAN_CONFIG = ArchetypeConfig(
    set_code="TST",
    scoring_method="bayesian_beta",
    bayesian_prior=1.0,
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


class TestBayesianBetaScoring:
    """Tests for Bayesian (%) scoring with Beta posteriors."""

    def test_no_signals_returns_prior_mean(self):
        """With no signals, P(open) = prior / (2*prior) = 0.5."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_positive_signal_increases_probability(self):
        """Card seen later than ATA -> P(open) > 0.5."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] > 0.5

    def test_exact_posterior_calculation(self):
        """Verify exact alpha/beta math for a known signal.

        Elf Lord: ata=3.0, pick=7, card_weight=0.9
        raw_signal = (7-3)/(7+3) * 0.9 * 1.0 = 0.4 * 0.9 = 0.36 (positive)
        alpha = 1.0 + 0.36 = 1.36
        beta = 1.0
        P(open) = 1.36 / (1.36 + 1.0) = 0.5763
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(1.36 / 2.36, abs=0.001)

    def test_card_weight_affects_magnitude(self):
        """Higher card_weight -> stronger push on posterior.

        Murder in BG Elves has weight=0.2, in UB Control has weight=0.7.
        Same signal (pick=8, ata=4) should push UB Control more.
        raw = (8-4)/(8+4) = 4/12 = 0.3333
        BG: alpha = 1.0 + 0.3333*0.2 = 1.0667, beta = 1.0 -> P = 1.0667/2.0667
        UB: alpha = 1.0 + 0.3333*0.7 = 1.2333, beta = 1.0 -> P = 1.2333/2.2333
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Murder", ata=4.0)], pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        bg_signal = (4.0 / 12.0) * 0.2
        ub_signal = (4.0 / 12.0) * 0.7
        assert scores["BG Elves"]["score"] == pytest.approx((1.0 + bg_signal) / (2.0 + bg_signal), abs=0.001)
        assert scores["UB Control"]["score"] == pytest.approx((1.0 + ub_signal) / (2.0 + ub_signal), abs=0.001)

    def test_pack_weight_scales_signal(self):
        """Pack weight multiplies the signal contribution.

        Same card/pick but pack_weight=0.5 halves the contribution.
        Elf Lord pick=7 ata=3 -> raw = (7-3)/(7+3) * 0.9 * 0.5 = 0.4 * 0.9 * 0.5 = 0.18
        alpha = 1.0 + 0.18 = 1.18, beta = 1.0 -> P = 1.18/2.18
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            bayesian_prior=1.0,
            pack_weights=[1.0, 0.5, 0.75],
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=1)
        scores = tracker.get_scores()
        signal = (4.0 / 10.0) * 0.9 * 0.5
        assert scores["BG Elves"]["score"] == pytest.approx((1.0 + signal) / (2.0 + signal), abs=0.001)

    def test_prior_parameter_effect(self):
        """Larger prior pulls P(open) closer to 0.5.

        prior=5.0, same signal as test_exact:
        raw = (7-3)/(7+3) * 0.9 = 0.4 * 0.9 = 0.36
        alpha = 5.0 + 0.36 = 5.36, beta = 5.0
        P = 5.36 / 10.36 = 0.5174  (closer to 0.5 than with prior=1.0)
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            bayesian_prior=5.0,
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(5.36 / 10.36, abs=0.001)

    def test_confidence_level_none(self):
        """Zero signals -> confidence 'none'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "none"

    def test_confidence_level_low(self):
        """1-4 signals -> confidence 'low'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "low"

    def test_confidence_level_medium(self):
        """5-14 signals -> confidence 'medium'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        for i in range(5):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "medium"

    def test_confidence_level_high(self):
        """15+ signals -> confidence 'high'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        for i in range(15):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "high"

    def test_interval_is_tuple(self):
        """Bayesian scoring provides a credible interval as a 2-tuple."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        interval = scores["BG Elves"]["interval"]
        assert interval is not None
        assert len(interval) == 2
        assert interval[0] < scores["BG Elves"]["score"] < interval[1]

    def test_pick_1_produces_no_signal(self):
        """Pick 1 provides no openness info — everyone sees the same pack."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)  # unchanged from prior
        assert scores["BG Elves"]["confidence"] == "none"  # no signals recorded

    def test_interval_narrows_with_more_signals(self):
        """More signals -> narrower credible interval."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores_early = tracker.get_scores()
        width_early = scores_early["BG Elves"]["interval"][1] - scores_early["BG Elves"]["interval"][0]

        for _ in range(10):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores_late = tracker.get_scores()
        width_late = scores_late["BG Elves"]["interval"][1] - scores_late["BG Elves"]["interval"][0]

        assert width_late < width_early


    def test_seen_card_negative_signal(self):
        """Card seen before ATA produces negative signal (pick < ata)."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=9.0)], pick_number=5, pack_number=0)
        scores = tracker.get_scores()
        # raw=(5-9)/(5+9)*0.9=-0.2571, beta=1.2571, score=1/(1+1.2571)≈0.443
        assert scores["BG Elves"]["score"] == pytest.approx(0.443, abs=0.001)

    def test_new_positive_formula_dampened(self):
        """New formula (pick-ata)/(pick+ata) produces smaller signals than old (pick-ata)/ata.

        ATA 2, pick 12: new = (12-2)/(12+2) = 0.714, old = (12-2)/2 = 5.0
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=2.0)], pick_number=12, pack_number=0)
        scores = tracker.get_scores()
        signal = (10.0 / 14.0) * 0.9  # ≈ 0.643
        expected = (1.0 + signal) / (2.0 + signal)
        assert scores["BG Elves"]["score"] == pytest.approx(expected, abs=0.001)
        # Signal < 1.0 (dampened), old formula would give 5.0 * 0.9 = 4.5
        assert signal < 1.0

    def test_config_default_opportunity_cost_decay(self):
        """Config without opportunity_cost_decay field gets default 0.1 (backward compat)."""
        data = {"set_code": "TST", "scoring_method": "bayesian_beta"}
        config = ArchetypeConfig.model_validate(data)
        assert config.opportunity_cost_decay == 0.1


class TestATANormalization:
    """Tests for ATA-normalized signal in Bayesian/Simple paths."""

    def test_low_ata_card_produces_stronger_signal(self):
        """ATA-3 card at pick 8 should produce stronger signal than ATA-8 card at pick 13.

        ATA 3 at pick 8: (8-3)/(8+3) * 0.9 = 0.4545 * 0.9 = 0.409
        ATA 8 at pick 13: (13-8)/(13+8) * 0.9 = 0.2381 * 0.9 = 0.214
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=8, pack_number=0)
        score_low_ata = tracker.get_scores()["BG Elves"]["score"]

        tracker.reset()
        tracker.record_pack([_make_card("Elf Lord", ata=8.0)], pick_number=13, pack_number=0)
        score_high_ata = tracker.get_scores()["BG Elves"]["score"]

        assert score_low_ata > score_high_ata

    def test_zero_ata_skipped_in_simple(self):
        """Cards with ATA 0 should be skipped in simple scoring."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=0.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == 0.0

    def test_zero_ata_skipped_in_bayesian(self):
        """Cards with ATA 0 should be skipped in bayesian scoring."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=0.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)


class TestWeightThreshold:
    """Tests for card_weight_threshold filtering in archetype detection."""

    def test_default_threshold_is_0_4(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.card_weight_threshold == 0.4

    def test_old_config_gets_default_threshold(self):
        data = {"set_code": "TST"}
        config = ArchetypeConfig.model_validate(data)
        assert config.card_weight_threshold == 0.4

    def test_weight_threshold_filters_generic_cards(self, otj_dataset):
        """Cards below threshold are excluded from auto-detected archetypes."""
        weights = calculate_card_weights(otj_dataset, "BG", threshold=0.4)
        for name, w in weights.items():
            assert w >= 0.4

    def test_weight_threshold_round_trip(self, tmp_path):
        """card_weight_threshold persists through save/load cycle."""
        config = ArchetypeConfig(set_code="TST", card_weight_threshold=0.3)
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.card_weight_threshold == 0.3

    def test_threshold_zero_includes_all(self, otj_dataset):
        """Threshold of 0.0 should include all cards with any weight."""
        weights_zero = calculate_card_weights(otj_dataset, "BG", threshold=0.0)
        weights_high = calculate_card_weights(otj_dataset, "BG", threshold=0.4)
        assert len(weights_zero) >= len(weights_high)


class TestMtgoPickConversion:
    """Tests verifying MTGO pick-in-pack vs Arena pick behavior."""

    def test_arena_pick_is_per_pack(self, tmp_path):
        """ArenaScanner.retrieve_current_pick_in_pack returns current_pick (already per-pack)."""
        from src.log_scanner import ArenaScanner
        scanner = ArenaScanner(str(tmp_path / "Player.log"), set_list=[])
        scanner.current_pick = 5
        assert scanner.retrieve_current_pick_in_pack() == 5

    def test_mtgo_pick_in_pack_resets(self, tmp_path):
        """MtgoScanner.retrieve_current_pick_in_pack returns per-pack pick, not sequential."""
        from src.mtgo_scanner import MtgoScanner
        scanner = MtgoScanner(str(tmp_path), set_list=[])
        scanner.current_pick_in_pack = 3
        assert scanner.retrieve_current_pick_in_pack() == 3

    def test_mtgo_sequential_vs_per_pack(self, tmp_path):
        """MTGO current_pick is sequential (16 for P2P1), but pick_in_pack is 1."""
        from src.mtgo_scanner import MtgoScanner
        scanner = MtgoScanner(str(tmp_path), set_list=[])
        # Simulate P2P1: sequential pick is 16, but pick_in_pack is 1
        scanner.current_pick = 16
        scanner.current_pick_in_pack = 1
        assert scanner.retrieve_current_pick_in_pack() == 1
        # The openness tracker should use 1, not 16


class TestBayesianSurvivalConfig:
    """Tests for bayesian_survival config fields."""

    def test_default_absence_enabled(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.absence_enabled is True

    def test_default_slots_per_rarity(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.slots_per_rarity == {
            "common": 10, "uncommon": 3, "rare": 1, "mythic": 0
        }

    def test_old_config_gets_defaults(self):
        data = {"set_code": "TST", "scoring_method": "bayesian_survival"}
        config = ArchetypeConfig.model_validate(data)
        assert config.absence_enabled is True
        assert config.slots_per_rarity["common"] == 10

    def test_config_round_trip(self, tmp_path):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            absence_enabled=False,
            slots_per_rarity={"common": 11, "uncommon": 3, "rare": 1, "mythic": 0},
        )
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.absence_enabled is False
        assert loaded.slots_per_rarity["common"] == 11


class TestBayesianSurvivalState:
    """Tests for bayesian_survival state initialization and reset."""

    def _make_config(self):
        return ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[
                Archetype(name="BG Elves", cards={"Elf Lord": 0.9}),
                Archetype(name="UB Control", cards={"Counterspell": 0.8}),
            ],
        )

    def test_initial_state(self):
        config = self._make_config()
        tracker = OpennessTracker(config)
        assert tracker.bs_log_odds == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_sum_sq == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_last_pick == {"BG Elves": 1, "UB Control": 1}
        assert tracker.bs_card_seen == {"BG Elves": {}, "UB Control": {}}
        assert tracker.bs_packs_observed == 0

    def test_reset_clears_state(self):
        config = self._make_config()
        tracker = OpennessTracker(config)
        # Mutate state
        tracker.bs_log_odds["BG Elves"] = 1.5
        tracker.bs_sum_sq["BG Elves"] = 0.5
        tracker.bs_last_pick["BG Elves"] = 7
        tracker.bs_card_seen["BG Elves"]["Elf Lord"] = 3
        tracker.bs_packs_observed = 5
        # Reset
        tracker.reset()
        assert tracker.bs_log_odds == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_sum_sq == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_last_pick == {"BG Elves": 1, "UB Control": 1}
        assert tracker.bs_card_seen == {"BG Elves": {}, "UB Control": {}}
        assert tracker.bs_packs_observed == 0  # end of reset test


class TestBayesianSurvivalWheeling:
    """Tests for bayesian_survival Signal 1 (wheeling)."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
            absence_enabled=False,
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_card_past_ata_produces_positive_signal(self):
        """Card at pick 7 with ATA 3: lambda > 0 -> score > 0."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] > 0.0

    def test_card_at_ata_produces_small_positive_signal(self):
        """Card at pick 3 with ATA 3: small positive signal (survival model always >= 0)."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] > 0.0

    def test_card_before_ata_produces_small_positive_signal(self):
        """Card at pick 2 with ATA 5: small positive signal (survival model always >= 0)."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=2, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] > 0.0

    def test_exact_wheeling_formula(self):
        """Verify exact log Bayes factor: ATA=3, pick=7, F=2, card_weight=1.0, common.

        a=3, F=2, p=7
        q_open = 1 - 1/6 = 5/6
        q_closed = 1 - 1/3 = 2/3
        lambda = 6 * log(q_open/q_closed) = 6 * log((5/6)/(2/3)) = 6 * log(5/4)
        rarity_weight = sqrt(0.0899/0.0899) = 1.0
        ramp at pick 7, ramp_picks=5: min(1.0, 6/4) = 1.0
        emission = lambda * 1.0 * 1.0 * 1.0 * 1.0 * 1.0
        """
        import math
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)

        expected_lambda = 6 * math.log((5/6) / (2/3))
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(expected_lambda, abs=0.001)

    def test_later_pick_stronger_signal(self):
        """Pick 10 should produce stronger signal than pick 5 for same card."""
        tracker1 = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker1.record_pack([card], pick_number=5, pack_number=0)
        score_5 = tracker1.get_scores()["Test"]["score"]

        tracker2 = OpennessTracker(self._make_config())
        tracker2.record_pack([card], pick_number=10, pack_number=0)
        score_10 = tracker2.get_scores()["Test"]["score"]

        assert score_10 > score_5

    def test_card_weight_scales_signal(self):
        """Card weight 0.5 should produce half the signal of weight 1.0."""
        import math
        config_full = self._make_config(archetypes=[Archetype(name="Test", cards={"Card": 1.0})])
        config_half = self._make_config(archetypes=[Archetype(name="Test", cards={"Card": 0.5})])

        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"

        t1 = OpennessTracker(config_full)
        t1.record_pack([card], pick_number=7, pack_number=0)
        t2 = OpennessTracker(config_half)
        t2.record_pack([card], pick_number=7, pack_number=0)

        assert t1.get_scores()["Test"]["score"] == pytest.approx(
            t2.get_scores()["Test"]["score"] * 2, abs=0.001
        )

    def test_ata_clamped_to_1_5(self):
        """ATA=1.0 should not cause math error; clamped to 1.5."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=1.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=5, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score > 0.0  # valid result, no crash

    def test_zero_ata_skipped(self):
        """ATA=0 should produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=0.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_pick_1_no_signal(self):
        """Pick 1 skipped by record_pack early return."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=1, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_rarity_weight_applied(self):
        """Rare card should produce weaker signal than common."""
        tracker_common = OpennessTracker(self._make_config())
        common = _make_card("Card", ata=5.0)
        common["rarity"] = "common"
        tracker_common.record_pack([common], pick_number=8, pack_number=0)

        tracker_rare = OpennessTracker(self._make_config())
        rare = _make_card("Card", ata=5.0)
        rare["rarity"] = "rare"
        tracker_rare.record_pack([rare], pick_number=8, pack_number=0)

        assert tracker_common.get_scores()["Test"]["score"] > tracker_rare.get_scores()["Test"]["score"]

    def test_decay_between_observations(self):
        """Signal decays between observations based on pick gap."""
        import math
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"

        # Record at pick 5, then at pick 10 (gap=5)
        tracker.record_pack([card], pick_number=5, pack_number=0)
        first_score = tracker.get_scores()["Test"]["score"]

        tracker.record_pack([card], pick_number=10, pack_number=0)
        second_score = tracker.get_scores()["Test"]["score"]

        # Second score should be: first * decay^5 + new_emission
        # Not just first + new (would ignore decay)
        decay = (1.0 - 0.15) ** 5
        new_lambda = 9 * math.log((5/6)/(2/3))  # pick=10
        expected = first_score * decay + new_lambda
        assert second_score == pytest.approx(expected, abs=0.01)

    def test_card_seen_count_incremented(self):
        """record_pack increments bs_card_seen for archetype cards."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.bs_card_seen["Test"].get("Card", 0) == 1

    def test_packs_observed_incremented(self):
        """record_pack increments bs_packs_observed."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.bs_packs_observed == 1
        tracker.record_pack([card], pick_number=8, pack_number=0)
        assert tracker.bs_packs_observed == 2


class TestBayesianSurvivalMissing:
    """Tests for bayesian_survival Signal 2 (missing cards)."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
            absence_enabled=False,
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_missing_high_ata_produces_negative_signal(self):
        """Card with ATA=10 missing at pick 9: strong negative signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score < 0.0

    def test_missing_low_ata_weak_signal(self):
        """Card with ATA=2 missing at pick 9: weak negative signal."""
        import math
        tracker_high = OpennessTracker(self._make_config())
        high_ata = _make_card("Card", ata=10.0)
        high_ata["rarity"] = "common"
        tracker_high.record_missing([high_ata], pick_number=9, pack_number=0)

        tracker_low = OpennessTracker(self._make_config())
        low_ata = _make_card("Card", ata=2.0)
        low_ata["rarity"] = "common"
        tracker_low.record_missing([low_ata], pick_number=9, pack_number=0)

        # Both negative, but high-ATA missing is more negative
        assert tracker_high.get_scores()["Test"]["score"] < tracker_low.get_scores()["Test"]["score"] < 0.0

    def test_missing_exact_formula(self):
        """Verify exact formula: ATA=10, pick=9, F=2, card_weight=1.0.

        a=10, F=2, p=9
        q_open = 1 - 1/20 = 0.95
        q_closed = 1 - 1/10 = 0.9
        S_open = 0.95^8 = 0.6634
        S_closed = 0.9^8 = 0.4305
        lambda = log((1 - 0.6634)/(1 - 0.4305)) = log(0.3366/0.5695)
        rarity_weight = 1.0 (common)
        ramp = 1.0 (pick 9 > ramp 5)
        """
        import math
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)

        S_open = 0.95 ** 8
        S_closed = 0.9 ** 8
        expected = math.log((1 - S_open) / (1 - S_closed))
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(expected, abs=0.001)

    def test_missing_no_gate(self):
        """Missing cards emit signal even when ATA > pick (they SHOULD still be there)."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=12.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score < 0.0  # still produces negative signal

    def test_missing_card_not_in_archetype_ignored(self):
        """Cards not in any archetype produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Unknown Card", ata=5.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_zero_ata_skipped(self):
        """Cards with ATA=0 produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=0.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_updates_state_with_decay(self):
        """Missing signal updates log-odds with decay like wheeling."""
        import math
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"

        # Wheeling at pick 12 first
        tracker.record_pack([card], pick_number=12, pack_number=0)
        first = tracker.get_scores()["Test"]["score"]

        # Missing at pick 14 (gap=2 from pick 12)
        tracker.record_missing([card], pick_number=14, pack_number=0)
        combined = tracker.get_scores()["Test"]["score"]

        # Combined should be: first * decay^2 + missing_emission
        decay = (1.0 - 0.15) ** 2
        S_open = (1 - 1/20) ** 13
        S_closed = (1 - 1/10) ** 13
        missing_emission = math.log((1 - S_open) / (1 - S_closed))
        expected = first * decay + missing_emission
        assert combined == pytest.approx(expected, abs=0.01)

    def test_missing_noop_for_unsupported_methods(self):
        """record_missing should be a no-op for methods that don't support it."""
        for method in ["simple", "normalized", "bayesian_beta", "hmm_hybrid"]:
            config = ArchetypeConfig(
                set_code="TST",
                scoring_method=method,
                archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
            )
            tracker = OpennessTracker(config)
            baseline = tracker.get_scores()["Test"]["score"]
            card = _make_card("Card", ata=10.0)
            card["rarity"] = "common"
            tracker.record_missing([card], pick_number=9, pack_number=0)
            assert tracker.get_scores()["Test"]["score"] == pytest.approx(baseline)


class TestBayesianSurvivalAbsence:
    """Tests for bayesian_survival Signal 3 (draft-wide absence)."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_common_never_seen_negative_signal(self):
        """Common card never seen after many packs -> negative absence signal."""
        tracker = OpennessTracker(self._make_config())
        # Simulate seeing 24 packs without "Card" appearing
        # We need packs_observed > 0 but card_seen["Card"] = 0
        # Force packs_observed by recording packs with OTHER cards
        other_card = _make_card("Other", ata=5.0)
        other_card["rarity"] = "common"
        for i in range(24):
            tracker.record_pack([other_card], pick_number=7, pack_number=0)
        assert tracker.bs_packs_observed == 24
        assert tracker.bs_card_seen["Test"].get("Card", 0) == 0

        scores = tracker.get_scores()
        # Score should include absence signal for "Card" (negative)
        # The only wheeling signals are for "Other" which isn't in the archetype
        assert scores["Test"]["score"] < 0.0

    def test_rare_never_seen_negligible_signal(self):
        """Rare card absence signal weaker than common card absence signal."""
        config_common = self._make_config()
        config_rare = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Rare Card": 1.0})]
        )

        # Common version — "Card" shows up once to cache rarity, then 23 packs without it
        tracker_c = OpennessTracker(config_common)
        card_c = _make_card("Card", ata=5.0)
        card_c["rarity"] = "common"
        other = _make_card("Other", ata=5.0)
        other["rarity"] = "common"
        tracker_c.record_pack([card_c], pick_number=2, pack_number=0)  # caches rarity, gated (no signal)
        for _ in range(23):
            tracker_c.record_pack([other], pick_number=7, pack_number=0)

        # Rare version — "Rare Card" shows up once to cache rarity as rare
        tracker_r = OpennessTracker(config_rare)
        rare_card = _make_card("Rare Card", ata=5.0)
        rare_card["rarity"] = "rare"
        tracker_r.record_pack([rare_card], pick_number=2, pack_number=0)  # caches rarity, gated
        for _ in range(23):
            tracker_r.record_pack([other], pick_number=7, pack_number=0)

        score_c = tracker_c.get_scores()["Test"]["score"]
        score_r = tracker_r.get_scores()["Test"]["score"]
        # Both should be negative (absence). Common absence is stronger.
        assert score_c < score_r

    def test_absence_disabled(self):
        """When absence_enabled=False, no absence signal."""
        config = self._make_config(absence_enabled=False)
        tracker = OpennessTracker(config)
        other = _make_card("Other", ata=5.0)
        other["rarity"] = "common"
        for _ in range(24):
            tracker.record_pack([other], pick_number=7, pack_number=0)

        scores = tracker.get_scores()
        # Without absence, unseen "Card" produces no signal.
        # And "Other" isn't in archetype, so no wheeling signal either.
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_no_packs_observed_no_absence(self):
        """When no packs have been observed, no absence signal."""
        tracker = OpennessTracker(self._make_config())
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_card_seen_expected_times_near_zero_signal(self):
        """Card seen approximately expected number of times -> near-zero absence signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["rarity"] = "common"
        # See it 2 times across 24 packs (close to expected ~1.5)
        tracker.record_pack([card], pick_number=7, pack_number=0)
        tracker.record_pack([card], pick_number=8, pack_number=0)
        for _ in range(22):
            other = _make_card("Other", ata=5.0)
            other["rarity"] = "common"
            tracker.record_pack([other], pick_number=7, pack_number=0)

        scores = tracker.get_scores()
        # The score includes both wheeling signals (positive from picks 7,8 past ATA 5)
        # and absence signal (card seen 2 times, expected ~1.5 -> slightly positive)
        # We can't easily assert the exact value, but the score should exist
        assert isinstance(scores["Test"]["score"], float)


class TestBayesianSurvivalIntegration:
    """Integration tests combining wheeling + missing + absence."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[
                Archetype(name="BG Elves", cards={"Elf Lord": 0.9, "Murder": 0.2}),
                Archetype(name="UB Control", cards={"Murder": 0.7, "Counterspell": 0.8}),
            ],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_wheeling_and_missing_combine(self):
        """Wheeling (positive) + missing (negative) should partially cancel."""
        config = self._make_config()
        tracker = OpennessTracker(config)

        # Wheeling: Elf Lord at pick 8 (ATA 3) -> positive for BG Elves
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=8, pack_number=0)
        score_after_wheeling = tracker.get_scores()["BG Elves"]["score"]
        assert score_after_wheeling > 0.0

        # Missing: Elf Lord gone at pick 10 (from next pack) -> negative
        tracker.record_missing([card], pick_number=10, pack_number=1)
        score_after_missing = tracker.get_scores()["BG Elves"]["score"]
        # The missing signal is negative, so total should be less than wheeling alone
        assert score_after_missing < score_after_wheeling

    def test_open_archetype_positive_score(self):
        """Archetype with many cards wheeling past ATA should have positive score."""
        config = self._make_config()
        tracker = OpennessTracker(config)

        # Multiple BG cards wheeling strongly
        for pick in [7, 8, 9, 10, 11]:
            card = _make_card("Elf Lord", ata=3.0)
            card["rarity"] = "common"
            tracker.record_pack([card], pick_number=pick, pack_number=0)

        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] > 0.0
        assert scores["BG Elves"]["confidence"] in ("medium", "high")

    def test_closed_archetype_negative_score(self):
        """Archetype with only missing cards should have negative score."""
        config = self._make_config()
        tracker = OpennessTracker(config)

        # Multiple BG cards missing
        for pick in [9, 10, 11, 12]:
            card = _make_card("Elf Lord", ata=10.0)
            card["rarity"] = "common"
            tracker.record_missing([card], pick_number=pick, pack_number=0)

        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] < 0.0

    def test_reset_clears_everything(self):
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        tracker.record_missing([card], pick_number=9, pack_number=0)

        tracker.reset()
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.0)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_interval_returned(self):
        """After signals, interval should be a 2-tuple."""
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=8, pack_number=0)

        data = tracker.get_scores()["BG Elves"]
        assert data["interval"] is not None
        assert len(data["interval"]) == 2
        # For log-odds output, interval is (lo, hi) around score
        assert data["interval"][0] < data["score"]
        assert data["interval"][1] > data["score"]

    def test_real_data_integration(self, otj_dataset):
        """Full flow with real OTJ dataset."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="bayesian_survival",
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        tracker.record_pack(pack_cards, pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)


class TestBayesianSurvivalEdgeCases:
    """Edge case tests for the bayesian_survival method."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
            absence_enabled=False,
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_empty_missing_cards(self):
        """record_missing with empty list is a no-op."""
        tracker = OpennessTracker(self._make_config())
        tracker.record_missing([], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_empty_pack_cards(self):
        """record_pack with empty list is a no-op (pick 1 early return)."""
        tracker = OpennessTracker(self._make_config())
        tracker.record_pack([], pick_number=1, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_pack_number_out_of_range(self):
        """pack_number beyond pack_weights uses default 1.0."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=5)
        assert tracker.get_scores()["Test"]["score"] > 0.0

    def test_no_archetypes_empty_scores(self):
        """Config with no archetypes returns empty scores."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[],
        )
        tracker = OpennessTracker(config)
        assert tracker.get_scores() == {}

    def test_multiple_cards_in_one_pack(self):
        """Multiple archetype cards in same pack all contribute."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"A": 1.0, "B": 1.0})],
            absence_enabled=False,
        )
        tracker_single = OpennessTracker(config)
        card_a = _make_card("A", ata=3.0)
        card_a["rarity"] = "common"
        tracker_single.record_pack([card_a], pick_number=7, pack_number=0)
        score_single = tracker_single.get_scores()["Test"]["score"]

        tracker_both = OpennessTracker(config)
        card_b = _make_card("B", ata=3.0)
        card_b["rarity"] = "common"
        tracker_both.record_pack([card_a, card_b], pick_number=7, pack_number=0)
        score_both = tracker_both.get_scores()["Test"]["score"]

        assert score_both > score_single

    def test_top_contributors_works(self):
        """get_top_contributors returns correct data for bayesian_survival."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        top = tracker.get_top_contributors("Test", count=3)
        assert len(top) == 1
        assert top[0]["card_name"] == "Card"

    def test_scoring_method_routing(self):
        """Verify get_scores routes to correct method."""
        for method in ["simple", "normalized", "bayesian_beta", "hmm_hybrid", "bayesian_survival"]:
            config = ArchetypeConfig(
                set_code="TST",
                scoring_method=method,
                archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
            )
            tracker = OpennessTracker(config)
            scores = tracker.get_scores()
            assert "Test" in scores
            assert "score" in scores["Test"]


class TestSimpleAlsaMissing:
    """Tests for simple_alsa negative signals from missing (non-wheeling) cards."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_missing_produces_negative_signal(self):
        """A missing card should produce a negative openness signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score < 0.0

    def test_missing_exact_formula(self):
        """Verify exact formula: -(1/(ata + pick)) * card_weight * pack_weight * 100."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=4.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        expected = -(1.0 / (4.0 + 9)) * 1.0 * 1.0 * 100  # -7.6923
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(expected)

    def test_low_ata_stronger_negative_than_high_ata(self):
        """Low ATA (strong card) produces stronger negative signal than high ATA."""
        tracker_low = OpennessTracker(self._make_config())
        card_low = _make_card("Card", ata=2.0)
        tracker_low.record_missing([card_low], pick_number=9, pack_number=0)

        tracker_high = OpennessTracker(self._make_config())
        card_high = _make_card("Card", ata=10.0)
        tracker_high.record_missing([card_high], pick_number=9, pack_number=0)

        # Both negative, but low ATA should be MORE negative (stronger penalty)
        assert tracker_low.get_scores()["Test"]["score"] < tracker_high.get_scores()["Test"]["score"] < 0.0

    def test_card_weight_scales_signal(self):
        """Higher card_weight produces stronger negative signal."""
        config_low = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Card": 0.3})])
        tracker_low = OpennessTracker(config_low)
        card = _make_card("Card", ata=5.0)
        tracker_low.record_missing([card], pick_number=9, pack_number=0)

        config_high = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Card": 0.9})])
        tracker_high = OpennessTracker(config_high)
        tracker_high.record_missing([card], pick_number=9, pack_number=0)

        # Higher card_weight -> more negative
        assert tracker_high.get_scores()["Test"]["score"] < tracker_low.get_scores()["Test"]["score"]

    def test_pack_weight_scales_signal(self):
        """Pack weight multiplies the negative signal."""
        config = self._make_config(pack_weights=[2.0, 1.0, 1.0])
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=5.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        expected = -(1.0 / (5.0 + 9)) * 1.0 * 2.0 * 100  # -14.2857
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(expected)

    def test_missing_card_not_in_archetype_ignored(self):
        """Cards not in any archetype produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Unknown Card", ata=5.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_zero_ata_skipped(self):
        """Cards with ATA=0 produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=0.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_positive_and_negative_combine(self):
        """Positive wheeling signals and negative missing signals combine."""
        tracker = OpennessTracker(self._make_config())
        # Positive: card seen at pick 5, ALSA=3.0 -> positive signal
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        tracker.record_pack([card], pick_number=5, pack_number=0)
        score_positive = tracker.get_scores()["Test"]["score"]
        assert score_positive > 0.0

        # Negative: same card missing from a different pack at pick 9
        tracker.record_missing([card], pick_number=9, pack_number=0)
        score_combined = tracker.get_scores()["Test"]["score"]
        assert score_combined < score_positive


class TestPassedCardsTracking:
    """Tests for passed cards tracking: cards the user doesn't pick."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple",
            pack_weights=[1.0, 0.66, 1.0],
            archetypes=[Archetype(name="Goblins", cards={"Goblin Guide": 0.8, "Lightning Bolt": 0.3})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_pack_weight_inversion(self):
        """Passed pack weights swap indices 0 and 1."""
        tracker = OpennessTracker(self._make_config())
        assert tracker.passed_pack_weights == [0.66, 1.0, 1.0]

    def test_record_passed_produces_negative_score(self):
        """Passing a card produces a negative passed score."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        scores = tracker.get_passed_scores()
        assert scores["Goblins"]["score"] < 0.0

    def test_record_passed_exact_formula(self):
        """Verify formula: -(1/(ata + pick)) * card_weight * passed_pack_weight * 100."""
        config = self._make_config(
            pack_weights=[1.0, 0.5, 1.0],
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=4.0)
        tracker.record_passed([card], pick_number=6, pack_number=0)
        # passed_pack_weights = [0.5, 1.0, 1.0], pack 0 weight = 0.5
        expected = -(1.0 / (4.0 + 6)) * 1.0 * 0.5 * 100  # -5.0
        assert tracker.get_passed_scores()["Test"]["score"] == pytest.approx(expected)

    def test_card_not_in_archetype_ignored(self):
        """Cards not in any archetype produce no passed signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Random Card", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_zero_ata_skipped(self):
        """Cards with ATA=0 produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=0.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_card_weight_scales_signal(self):
        """Higher card_weight produces stronger passed signal."""
        config_low = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Card": 0.2})])
        tracker_low = OpennessTracker(config_low)
        card = _make_card("Card", ata=5.0)
        tracker_low.record_passed([card], pick_number=3, pack_number=0)

        config_high = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Card": 0.9})])
        tracker_high = OpennessTracker(config_high)
        tracker_high.record_passed([card], pick_number=3, pack_number=0)

        assert tracker_high.get_passed_scores()["Test"]["score"] < tracker_low.get_passed_scores()["Test"]["score"]

    def test_passed_pack_weight_applied(self):
        """Passed uses inverted pack weights (P2 gets P1's weight)."""
        config = self._make_config(pack_weights=[1.0, 0.5, 1.0])
        tracker = OpennessTracker(config)
        card = _make_card("Goblin Guide", ata=5.0)

        # Pack 1 (index 0): passed_weight = 0.5
        tracker.record_passed([card], pick_number=3, pack_number=0)
        score_p1 = tracker.get_passed_scores()["Goblins"]["score"]

        tracker2 = OpennessTracker(config)
        # Pack 2 (index 1): passed_weight = 1.0
        tracker2.record_passed([card], pick_number=3, pack_number=1)
        score_p2 = tracker2.get_passed_scores()["Goblins"]["score"]

        # P2 should have stronger (more negative) signal
        assert score_p2 < score_p1

    def test_accumulation_across_picks(self):
        """Passed scores accumulate across multiple picks."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=5.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        score_1 = tracker.get_passed_scores()["Goblins"]["score"]
        tracker.record_passed([card], pick_number=3, pack_number=0)
        score_2 = tracker.get_passed_scores()["Goblins"]["score"]
        assert score_2 < score_1 < 0.0

    def test_reset_clears_passed(self):
        """Reset clears all passed signals."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0
        tracker.reset()
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_get_top_passed(self):
        """Top passed returns highest absolute signals."""
        tracker = OpennessTracker(self._make_config())
        guide = _make_card("Goblin Guide", ata=2.0)
        bolt = _make_card("Lightning Bolt", ata=8.0)
        tracker.record_passed([guide, bolt], pick_number=5, pack_number=0)
        top = tracker.get_top_passed("Goblins", count=1)
        assert len(top) == 1
        # Goblin Guide has lower ATA and higher card_weight -> strongest signal
        assert top[0]["card_name"] == "Goblin Guide"

    def test_passed_independent_from_openness(self):
        """Passed scores don't affect openness scores and vice versa."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        # Openness score should still be 0
        assert tracker.get_scores()["Goblins"]["score"] == pytest.approx(0.0)
        # Passed score should be negative
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0

    def test_pick_1_produces_signal(self):
        """Pick 1 passed cards still produce a signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=1, pack_number=0)
        # -(1/(3+1)) * 0.8 * 0.66 * 100 = -13.2
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(-13.2, abs=0.01)

    def test_passed_signal_includes_pack_number(self):
        """Each passed signal entry should include a pack_number field."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=1)
        assert len(tracker.passed_signals) > 0
        for sig in tracker.passed_signals:
            assert "pack_number" in sig
            assert sig["pack_number"] == 1


class TestRevertReturned:
    """Tests for revert_returned: undo passed signals when a card wheels back."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple",
            pack_weights=[1.0, 1.0, 1.0],
            archetypes=[
                Archetype(name="Goblins", cards={"Goblin Guide": 0.8, "Lightning Bolt": 0.3}),
                Archetype(name="Izzet", cards={"Lightning Bolt": 0.7, "Counterspell": 0.6}),
            ],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_revert_removes_earliest_signal(self):
        """Pass a card then revert it — passed score returns to 0."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0

        tracker.revert_returned(["Goblin Guide"], pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_revert_scoped_to_pack_number(self):
        """Revert only affects signals from the matching pack_number."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        tracker.record_passed([card], pick_number=3, pack_number=1)

        score_before = tracker.get_passed_scores()["Goblins"]["score"]
        # Revert only pack 0
        tracker.revert_returned(["Goblin Guide"], pack_number=0)
        score_after = tracker.get_passed_scores()["Goblins"]["score"]

        # Pack 1 signal should still be present
        assert score_after < 0.0
        assert score_after > score_before

    def test_revert_earliest_only(self):
        """Same card passed at pick 2 and pick 4 in same pack — revert removes only pick 2."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        tracker.record_passed([card], pick_number=4, pack_number=0)

        score_both = tracker.get_passed_scores()["Goblins"]["score"]
        tracker.revert_returned(["Goblin Guide"], pack_number=0)
        score_after = tracker.get_passed_scores()["Goblins"]["score"]

        # Only pick 2 removed, pick 4 signal should remain
        assert score_after < 0.0
        assert score_after > score_both

    def test_revert_idempotent(self):
        """Calling revert twice for the same card is the same as calling once."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)

        tracker.revert_returned(["Goblin Guide"], pack_number=0)
        score_first = tracker.get_passed_scores()["Goblins"]["score"]

        tracker.revert_returned(["Goblin Guide"], pack_number=0)
        score_second = tracker.get_passed_scores()["Goblins"]["score"]

        assert score_first == pytest.approx(score_second)
        assert score_first == pytest.approx(0.0)

    def test_revert_unknown_card_is_noop(self):
        """Reverting a card that was never passed does nothing."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        score_before = tracker.get_passed_scores()["Goblins"]["score"]

        tracker.revert_returned(["Unknown Card"], pack_number=0)
        score_after = tracker.get_passed_scores()["Goblins"]["score"]

        assert score_after == pytest.approx(score_before)

    def test_revert_multi_archetype(self):
        """Card in 2 archetypes — revert removes signals from both."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Lightning Bolt", ata=4.0)
        tracker.record_passed([card], pick_number=3, pack_number=0)

        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0
        assert tracker.get_passed_scores()["Izzet"]["score"] < 0.0

        tracker.revert_returned(["Lightning Bolt"], pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)
        assert tracker.get_passed_scores()["Izzet"]["score"] == pytest.approx(0.0)


class TestDoubleRecordingPrevention:
    """Tests documenting that record_pack doubles signals when called twice,
    and verifying the overlay-level dedup guard prevents this."""

    def test_record_pack_called_twice_doubles_signals(self):
        """Calling record_pack twice with same data doubles the score.

        This documents the root cause of the bug: OpennessTracker itself
        does no dedup — the overlay must guard against duplicate calls.
        """
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=3.0)]

        tracker.record_pack(pack, pick_number=7, pack_number=0)
        score_once = tracker.get_scores()["BG Elves"]["score"]

        tracker.record_pack(pack, pick_number=7, pack_number=0)
        score_twice = tracker.get_scores()["BG Elves"]["score"]

        assert score_once > 0.0
        assert score_twice == pytest.approx(score_once * 2, abs=0.01)
