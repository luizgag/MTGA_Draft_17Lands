import pytest
from src.archetype_openness import OpennessTracker, Archetype, ArchetypeConfig
from tests.test_archetype_openness.helpers import _make_card, BAYESIAN_CONFIG


class TestBayesianBetaInterval:
    """Tests for Bayesian Beta credible interval display."""

    def test_bayesian_interval_returned(self):
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


class TestBayesianBetaScoring:
    """Tests for Bayesian (%) scoring with Beta posteriors."""

    def test_no_signals_returns_prior_mean(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_positive_signal_increases_probability(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] > 0.5

    def test_exact_posterior_calculation(self):
        """Elf Lord: ata=3.0, pick=7, card_weight=0.9
        raw_signal = (7-3)/(7+3) * 0.9 * 1.0 = 0.4 * 0.9 = 0.36 (positive)
        alpha = 1.0 + 0.36 = 1.36; beta = 1.0
        P(open) = 1.36 / (1.36 + 1.0) = 0.5763
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(1.36 / 2.36, abs=0.001)

    def test_card_weight_affects_magnitude(self):
        """Murder in BG Elves has weight=0.2, in UB Control has weight=0.7."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Murder", ata=4.0)], pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        bg_signal = (4.0 / 12.0) * 0.2
        ub_signal = (4.0 / 12.0) * 0.7
        assert scores["BG Elves"]["score"] == pytest.approx((1.0 + bg_signal) / (2.0 + bg_signal), abs=0.001)
        assert scores["UB Control"]["score"] == pytest.approx((1.0 + ub_signal) / (2.0 + ub_signal), abs=0.001)

    def test_pack_weight_scales_signal(self):
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
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "none"

    def test_confidence_level_low(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "low"

    def test_confidence_level_medium(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        for i in range(5):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "medium"

    def test_confidence_level_high(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        for i in range(15):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "high"

    def test_interval_is_tuple(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        interval = scores["BG Elves"]["interval"]
        assert interval is not None
        assert len(interval) == 2
        assert interval[0] < scores["BG Elves"]["score"] < interval[1]

    def test_pick_1_produces_no_signal(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=1, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_interval_narrows_with_more_signals(self):
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
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=9.0)], pick_number=5, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.443, abs=0.001)

    def test_new_positive_formula_dampened(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=2.0)], pick_number=12, pack_number=0)
        scores = tracker.get_scores()
        signal = (10.0 / 14.0) * 0.9
        expected = (1.0 + signal) / (2.0 + signal)
        assert scores["BG Elves"]["score"] == pytest.approx(expected, abs=0.001)
        assert signal < 1.0


class TestATANormalization:
    """Tests for ATA-normalized signal in Bayesian/Simple paths."""

    def test_low_ata_card_produces_stronger_signal(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=8, pack_number=0)
        score_low_ata = tracker.get_scores()["BG Elves"]["score"]

        tracker.reset()
        tracker.record_pack([_make_card("Elf Lord", ata=8.0)], pick_number=13, pack_number=0)
        score_high_ata = tracker.get_scores()["BG Elves"]["score"]

        assert score_low_ata > score_high_ata

    def test_zero_ata_skipped_in_simple(self):
        from tests.test_archetype_openness.helpers import SIMPLE_CONFIG
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=0.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == 0.0

    def test_zero_ata_skipped_in_bayesian(self):
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=0.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)
