import math
import pytest
from src.archetype_openness import (
    OpennessTracker, Archetype, ArchetypeConfig,
    load_archetype_config, save_archetype_config,
)
from tests.test_archetype_openness.helpers import _make_card


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

    def test_hmm_ata_clamp(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=1.0)], pick_number=5, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert 0.0 <= score <= 1.0
        assert score > 0.5

    def test_hmm_pick_1_still_no_signal(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Card", ata=3.0)], pick_number=1, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score == pytest.approx(0.5)

    def test_hmm_pick_ramp_dampens_early_picks(self):
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

        assert score_early > 0.5
        assert score_early < 0.55
        assert score_late > score_early

    def test_hmm_pick_ramp_full_weight_at_threshold(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            hmm_pick_ramp=5,
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        assert tracker._hmm_pick_ramp_factor(5) == pytest.approx(1.0)
        assert tracker._hmm_pick_ramp_factor(10) == pytest.approx(1.0)
        assert tracker._hmm_pick_ramp_factor(2) == pytest.approx(0.25)
        assert tracker._hmm_pick_ramp_factor(3) == pytest.approx(0.50)

    def test_hmm_interval_returned_after_signals(self):
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
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="hmm_hybrid",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        data = tracker.get_scores()["Test"]
        assert data["interval"] is None

    def test_hmm_interval_bounds_valid(self):
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
