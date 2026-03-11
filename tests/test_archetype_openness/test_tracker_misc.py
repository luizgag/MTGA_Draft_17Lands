import pytest
from src.archetype_openness import (
    OpennessTracker, Archetype, ArchetypeConfig,
    load_archetype_config, save_archetype_config, calculate_card_weights,
)
from tests.test_archetype_openness.helpers import _make_card, SIMPLE_CONFIG, BAYESIAN_CONFIG


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


class TestDoubleRecordingPrevention:
    """Tests documenting that record_pack doubles signals when called twice."""

    def test_record_pack_called_twice_doubles_signals(self):
        """Calling record_pack twice with same data doubles the score."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=3.0)]

        tracker.record_pack(pack, pick_number=7, pack_number=0)
        score_once = tracker.get_scores()["BG Elves"]["score"]

        tracker.record_pack(pack, pick_number=7, pack_number=0)
        score_twice = tracker.get_scores()["BG Elves"]["score"]

        assert score_once > 0.0
        assert score_twice == pytest.approx(score_once * 2, abs=0.01)


class TestSimpleAlsaMissingRemoved:
    """Verify record_missing no longer fires for simple_alsa."""

    def test_record_missing_noop_for_simple_alsa(self):
        """record_missing should produce no signals for simple_alsa scoring."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=5.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)
        assert len(tracker.signals) == 0


class TestGetPositiveScores:
    """Tests for get_positive_scores() — returns only positive wheeling signals."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_positive_signals_only(self):
        """get_positive_scores returns sum of positive signals, ignores negative."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        # pick 5 > alsa 3.0 -> positive signal
        tracker.record_pack([card], pick_number=5, pack_number=0)
        positive = tracker.get_positive_scores()
        assert positive["Test"]["score"] > 0.0

    def test_no_signals_returns_zero(self):
        """No signals means zero positive score."""
        tracker = OpennessTracker(self._make_config())
        positive = tracker.get_positive_scores()
        assert positive["Test"]["score"] == pytest.approx(0.0)

    def test_passed_signals_not_included(self):
        """Passed signals should not appear in positive scores."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        positive = tracker.get_positive_scores()
        assert positive["Test"]["score"] == pytest.approx(0.0)


class TestGetCombinedScores:
    """Tests for get_combined_scores() — positive + passed signals."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_combined_equals_positive_plus_passed(self):
        """Combined score = positive wheeling + passed card signals."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        tracker.record_pack([card], pick_number=5, pack_number=0)
        tracker.record_passed([card], pick_number=2, pack_number=0)

        positive = tracker.get_positive_scores()["Test"]["score"]
        passed = tracker.get_passed_scores()["Test"]["score"]
        combined = tracker.get_combined_scores()["Test"]["score"]
        assert combined == pytest.approx(positive + passed)

    def test_no_signals_returns_zero(self):
        """No signals means zero combined score."""
        tracker = OpennessTracker(self._make_config())
        combined = tracker.get_combined_scores()
        assert combined["Test"]["score"] == pytest.approx(0.0)

    def test_positive_only_equals_positive(self):
        """With no passed signals, combined == positive."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        tracker.record_pack([card], pick_number=5, pack_number=0)
        positive = tracker.get_positive_scores()["Test"]["score"]
        combined = tracker.get_combined_scores()["Test"]["score"]
        assert combined == pytest.approx(positive)


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
        assert tracker._pick_weight(8, max_picks=14) == pytest.approx(7.0 / 13.0)

    def test_sqrt_curve(self):
        """Sqrt curve rises faster early."""
        tracker = self._make_tracker("sqrt")
        t = 3.0 / 13.0
        assert tracker._pick_weight(4, max_picks=14) == pytest.approx(t ** 0.5)

    def test_squared_curve(self):
        """Squared curve rises slower early."""
        tracker = self._make_tracker("squared")
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
        db_path = str(tmp_path / "test.db")
        config = ArchetypeConfig(set_code="TST", weight_curve="sqrt")
        file_path = str(tmp_path / "TST_archetypes.json")
        save_archetype_config(config, file_path, db_path=db_path)
        loaded = load_archetype_config(file_path, db_path=db_path)
        assert loaded.weight_curve == "sqrt"

    def test_old_config_without_weight_curve_gets_default(self):
        """Config JSON missing weight_curve field gets 'linear' default."""
        data = {"set_code": "TST", "scoring_method": "normalized"}
        config = ArchetypeConfig.model_validate(data)
        assert config.weight_curve == "linear"


class TestBayesianConfig:
    """Tests for bayesian_prior configuration field."""

    def test_default_bayesian_prior(self):
        """Default bayesian_prior is 1.0."""
        config = ArchetypeConfig(set_code="TST")
        assert config.bayesian_prior == 1.0

    def test_bayesian_prior_round_trip(self, tmp_path):
        """bayesian_prior persists through save/load cycle."""
        db_path = str(tmp_path / "test.db")
        config = ArchetypeConfig(set_code="TST", bayesian_prior=2.5)
        file_path = str(tmp_path / "TST_archetypes.json")
        save_archetype_config(config, file_path, db_path=db_path)
        loaded = load_archetype_config(file_path, db_path=db_path)
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
        db_path = str(tmp_path / "test.db")
        config = ArchetypeConfig(
            set_code="TST",
            rarity_odds={"common": 0.70, "uncommon": 0.50, "rare": 0.40, "mythic": 0.25},
        )
        file_path = str(tmp_path / "TST_archetypes.json")
        save_archetype_config(config, file_path, db_path=db_path)
        loaded = load_archetype_config(file_path, db_path=db_path)
        assert loaded.rarity_odds["common"] == pytest.approx(0.70)


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
        db_path = str(tmp_path / "test.db")
        config = ArchetypeConfig(set_code="TST", card_weight_threshold=0.3)
        file_path = str(tmp_path / "TST_archetypes.json")
        save_archetype_config(config, file_path, db_path=db_path)
        loaded = load_archetype_config(file_path, db_path=db_path)
        assert loaded.card_weight_threshold == 0.3

    def test_threshold_zero_includes_all(self, otj_dataset):
        """Threshold of 0.0 should include all cards with any weight."""
        weights_zero = calculate_card_weights(otj_dataset, "BG", threshold=0.0)
        weights_high = calculate_card_weights(otj_dataset, "BG", threshold=0.4)
        assert len(weights_zero) >= len(weights_high)
