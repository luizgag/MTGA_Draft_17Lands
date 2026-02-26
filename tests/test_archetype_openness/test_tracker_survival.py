import math
import pytest
from src.archetype_openness import OpennessTracker, Archetype, ArchetypeConfig
from tests.test_archetype_openness.helpers import _make_card


def _bs_config(**kwargs):
    defaults = dict(
        set_code="TST",
        scoring_method="bayesian_survival",
        archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        absence_enabled=False,
    )
    defaults.update(kwargs)
    return ArchetypeConfig(**defaults)


class TestBayesianSurvivalConfig:
    def test_default_absence_enabled(self):
        assert ArchetypeConfig(set_code="TST").absence_enabled is True

    def test_default_slots_per_rarity(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.slots_per_rarity == {"common": 10, "uncommon": 3, "rare": 1, "mythic": 0}

    def test_old_config_gets_defaults(self):
        data = {"set_code": "TST", "scoring_method": "bayesian_survival"}
        config = ArchetypeConfig.model_validate(data)
        assert config.absence_enabled is True
        assert config.slots_per_rarity["common"] == 10


class TestBayesianSurvivalState:
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
        tracker.bs_log_odds["BG Elves"] = 1.5
        tracker.bs_sum_sq["BG Elves"] = 0.5
        tracker.bs_last_pick["BG Elves"] = 7
        tracker.bs_card_seen["BG Elves"]["Elf Lord"] = 3
        tracker.bs_packs_observed = 5
        tracker.reset()
        assert tracker.bs_log_odds == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_sum_sq == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_last_pick == {"BG Elves": 1, "UB Control": 1}
        assert tracker.bs_card_seen == {"BG Elves": {}, "UB Control": {}}
        assert tracker.bs_packs_observed == 0


class TestBayesianSurvivalWheeling:
    def test_card_past_ata_produces_positive_signal(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] > 0.0

    def test_exact_wheeling_formula(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)

        expected_lambda = 6 * math.log((5/6) / (2/3))
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(expected_lambda, abs=0.001)

    def test_later_pick_stronger_signal(self):
        t1 = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        t1.record_pack([card], pick_number=5, pack_number=0)

        t2 = OpennessTracker(_bs_config())
        t2.record_pack([card], pick_number=10, pack_number=0)

        assert t2.get_scores()["Test"]["score"] > t1.get_scores()["Test"]["score"]

    def test_card_weight_scales_signal(self):
        config_full = _bs_config(archetypes=[Archetype(name="Test", cards={"Card": 1.0})])
        config_half = _bs_config(archetypes=[Archetype(name="Test", cards={"Card": 0.5})])

        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"

        t1 = OpennessTracker(config_full)
        t1.record_pack([card], pick_number=7, pack_number=0)
        t2 = OpennessTracker(config_half)
        t2.record_pack([card], pick_number=7, pack_number=0)

        assert t1.get_scores()["Test"]["score"] == pytest.approx(t2.get_scores()["Test"]["score"] * 2, abs=0.001)

    def test_zero_ata_skipped(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=0.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_pick_1_no_signal(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=1, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_rarity_weight_applied(self):
        tracker_common = OpennessTracker(_bs_config())
        common = _make_card("Card", ata=5.0)
        common["rarity"] = "common"
        tracker_common.record_pack([common], pick_number=8, pack_number=0)

        tracker_rare = OpennessTracker(_bs_config())
        rare = _make_card("Card", ata=5.0)
        rare["rarity"] = "rare"
        tracker_rare.record_pack([rare], pick_number=8, pack_number=0)

        assert tracker_common.get_scores()["Test"]["score"] > tracker_rare.get_scores()["Test"]["score"]

    def test_decay_between_observations(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"

        tracker.record_pack([card], pick_number=5, pack_number=0)
        first_score = tracker.get_scores()["Test"]["score"]

        tracker.record_pack([card], pick_number=10, pack_number=0)
        second_score = tracker.get_scores()["Test"]["score"]

        decay = (1.0 - 0.15) ** 5
        new_lambda = 9 * math.log((5/6)/(2/3))
        expected = first_score * decay + new_lambda
        assert second_score == pytest.approx(expected, abs=0.01)

    def test_card_seen_count_incremented(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.bs_card_seen["Test"].get("Card", 0) == 1

    def test_packs_observed_incremented(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.bs_packs_observed == 1
        tracker.record_pack([card], pick_number=8, pack_number=0)
        assert tracker.bs_packs_observed == 2


class TestBayesianSurvivalMissing:
    def test_missing_high_ata_produces_negative_signal(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] < 0.0

    def test_missing_exact_formula(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)

        S_open = 0.95 ** 8
        S_closed = 0.9 ** 8
        expected = math.log((1 - S_open) / (1 - S_closed))
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(expected, abs=0.001)

    def test_missing_no_gate(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=12.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] < 0.0

    def test_missing_card_not_in_archetype_ignored(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Unknown Card", ata=5.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_zero_ata_skipped(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=0.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_noop_for_unsupported_methods(self):
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
    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_common_never_seen_negative_signal(self):
        tracker = OpennessTracker(self._make_config())
        other_card = _make_card("Other", ata=5.0)
        other_card["rarity"] = "common"
        for i in range(24):
            tracker.record_pack([other_card], pick_number=7, pack_number=0)
        assert tracker.bs_packs_observed == 24
        assert tracker.bs_card_seen["Test"].get("Card", 0) == 0
        assert tracker.get_scores()["Test"]["score"] < 0.0

    def test_absence_disabled(self):
        config = self._make_config(absence_enabled=False)
        tracker = OpennessTracker(config)
        other = _make_card("Other", ata=5.0)
        other["rarity"] = "common"
        for _ in range(24):
            tracker.record_pack([other], pick_number=7, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_no_packs_observed_no_absence(self):
        tracker = OpennessTracker(self._make_config())
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)


class TestBayesianSurvivalIntegration:
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
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=8, pack_number=0)
        score_after_wheeling = tracker.get_scores()["BG Elves"]["score"]
        assert score_after_wheeling > 0.0

        tracker.record_missing([card], pick_number=10, pack_number=1)
        assert tracker.get_scores()["BG Elves"]["score"] < score_after_wheeling

    def test_open_archetype_positive_score(self):
        tracker = OpennessTracker(self._make_config())
        for pick in [7, 8, 9, 10, 11]:
            card = _make_card("Elf Lord", ata=3.0)
            card["rarity"] = "common"
            tracker.record_pack([card], pick_number=pick, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] > 0.0
        assert scores["BG Elves"]["confidence"] in ("medium", "high")

    def test_closed_archetype_negative_score(self):
        tracker = OpennessTracker(self._make_config())
        for pick in [9, 10, 11, 12]:
            card = _make_card("Elf Lord", ata=10.0)
            card["rarity"] = "common"
            tracker.record_missing([card], pick_number=pick, pack_number=0)
        assert tracker.get_scores()["BG Elves"]["score"] < 0.0

    def test_reset_clears_everything(self):
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        tracker.reset()
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.0)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_interval_returned(self):
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=8, pack_number=0)
        data = tracker.get_scores()["BG Elves"]
        assert data["interval"] is not None
        assert len(data["interval"]) == 2
        assert data["interval"][0] < data["score"]
        assert data["interval"][1] > data["score"]

    def test_real_data_integration(self, otj_dataset):
        from src.archetype_openness import auto_detect_archetypes
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
    def test_empty_missing_cards(self):
        tracker = OpennessTracker(_bs_config())
        tracker.record_missing([], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_pack_number_out_of_range(self):
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=5)
        assert tracker.get_scores()["Test"]["score"] > 0.0

    def test_no_archetypes_empty_scores(self):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[],
        )
        tracker = OpennessTracker(config)
        assert tracker.get_scores() == {}

    def test_multiple_cards_in_one_pack(self):
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
        tracker = OpennessTracker(_bs_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        top = tracker.get_top_contributors("Test", count=3)
        assert len(top) == 1
        assert top[0]["card_name"] == "Card"

    def test_scoring_method_routing(self):
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
