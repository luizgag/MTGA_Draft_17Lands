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
        # (7-3)/3 * 0.9 = 1.2
        assert scores["BG Elves"]["score"] == pytest.approx(1.2, abs=0.01)

    def test_single_card_negative_signal(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=7.0)]
        tracker.record_pack(pack, pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        # (3-7)/7 * 0.9 = -0.5143
        assert scores["BG Elves"]["score"] == pytest.approx(-0.5143, abs=0.01)

    def test_multi_archetype_card(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Murder", ata=4.0)]
        tracker.record_pack(pack, pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        # (8-4)/4 = 1.0. BG: 1.0*0.2=0.2. UB: 1.0*0.7=0.7
        assert scores["BG Elves"]["score"] == pytest.approx(0.2, abs=0.01)
        assert scores["UB Control"]["score"] == pytest.approx(0.7, abs=0.01)

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
        # sig1=(7-3)/3*0.9=1.2, sig2=(9-5)/5*0.5=0.4. total=1.6
        assert scores["BG Elves"]["score"] == pytest.approx(1.6, abs=0.01)

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
        # (7-3)/3 * 0.9 * 0.5 = 0.6
        assert scores["BG Elves"]["score"] == pytest.approx(0.6, abs=0.01)

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
    """Tests for normalized scoring: signal = ((pick - ATA) / ATA) * pick_weight * card_weight * pack_weight."""

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
        # ((6-2)/2) * (5/13) * 0.9 = 2.0 * 0.3846 * 0.9 ≈ 0.6923
        assert scores["BG Elves"]["score"] == pytest.approx(0.6923, abs=0.01)

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
        # Early: ((6-2)/2) * (5/13) * 1.0 = 0.7692
        # Late: ((12-8)/8) * (11/13) * 1.0 = 0.4231
        assert scores["Test"]["score"] == pytest.approx(1.1923, abs=0.01)

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
        # ata=2.0: raw = ((13-2)/2) * 0.923 = 5.5 * 0.923 ≈ 5.077
        tracker.record_pack([_make_card("Card", ata=2.0)], pick_number=13, pack_number=0)
        scores = tracker.get_scores()
        expected = ((13 - 2) / 2.0) * (12.0 / 13.0) * 1.0
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

    def test_negative_signal_decreases_probability(self):
        """Card seen at/before ATA -> opportunity cost pushes P(open) < 0.5.

        pick=3, ata=7: not wheeling -> beta += 0.1 * 0.9 * 1.0 = 0.09
        alpha = 1.0, beta = 1.09 -> P = 1.0/2.09 ≈ 0.4785
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=7.0)], pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] < 0.5

    def test_exact_posterior_calculation(self):
        """Verify exact alpha/beta math for a known signal.

        Elf Lord: ata=3.0, pick=7, card_weight=0.9
        raw_signal = (7-3)/3 * 0.9 * 1.0 = 1.2 (positive)
        alpha = 1.0 + 1.2 = 2.2
        beta = 1.0
        P(open) = 2.2 / (2.2 + 1.0) = 0.6875
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(2.2 / 3.2, abs=0.001)

    def test_card_weight_affects_magnitude(self):
        """Higher card_weight -> stronger push on posterior.

        Murder in BG Elves has weight=0.2, in UB Control has weight=0.7.
        Same signal (pick=8, ata=4) should push UB Control more.
        raw = (8-4)/4 = 1.0
        BG: alpha = 1.0 + 1.0*0.2 = 1.2, beta = 1.0 -> P = 1.2/2.2 = 0.5455
        UB: alpha = 1.0 + 1.0*0.7 = 1.7, beta = 1.0 -> P = 1.7/2.7 = 0.6296
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Murder", ata=4.0)], pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(1.2 / 2.2, abs=0.001)
        assert scores["UB Control"]["score"] == pytest.approx(1.7 / 2.7, abs=0.001)

    def test_mixed_signals_intermediate(self):
        """Positive then opportunity-cost signals produce an intermediate value.

        Elf Lord pick=7 ata=3 -> wheeling, raw=(7-3)/3*0.9=1.2 -> alpha += 1.2
        Elf Lord pick=2 ata=5 -> not wheeling, opportunity cost=0.1*0.9*1.0=0.09 -> beta += 0.09
        alpha = 1.0 + 1.2 = 2.2, beta = 1.0 + 0.09 = 1.09
        P = 2.2 / 3.29 = 0.6687
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.record_pack([_make_card("Elf Lord", ata=5.0)], pick_number=2, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(2.2 / 3.29, abs=0.001)

    def test_pack_weight_scales_signal(self):
        """Pack weight multiplies the signal contribution.

        Same card/pick but pack_weight=0.5 halves the contribution.
        Elf Lord pick=7 ata=3 -> raw = (7-3)/3 * 0.9 * 0.5 = 0.6
        alpha = 1.0 + 0.6 = 1.6, beta = 1.0 -> P = 1.6/2.6 = 0.6154
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
        assert scores["BG Elves"]["score"] == pytest.approx(1.6 / 2.6, abs=0.001)

    def test_prior_parameter_effect(self):
        """Larger prior pulls P(open) closer to 0.5.

        prior=5.0, same signal as test_exact:
        raw = (7-3)/3 * 0.9 = 1.2
        alpha = 5.0 + 1.2 = 6.2, beta = 5.0
        P = 6.2 / 11.2 = 0.5536  (closer to 0.5 than with prior=1.0)
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
        assert scores["BG Elves"]["score"] == pytest.approx(6.2 / 11.2, abs=0.001)

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


    def test_opportunity_cost_decay_configurable(self):
        """Larger decay constant produces stronger downward pressure.

        Default decay=0.1: beta += 0.1 * 0.9 = 0.09 -> P = 1.0/2.09 ≈ 0.4785
        Custom decay=0.2: beta += 0.2 * 0.9 = 0.18 -> P = 1.0/2.18 ≈ 0.4587
        """
        # Default decay (0.1)
        tracker_default = OpennessTracker(BAYESIAN_CONFIG)
        tracker_default.record_pack([_make_card("Elf Lord", ata=7.0)], pick_number=3, pack_number=0)
        score_default = tracker_default.get_scores()["BG Elves"]["score"]

        # Higher decay (0.2)
        config_high_decay = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            bayesian_prior=1.0,
            opportunity_cost_decay=0.2,
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker_high = OpennessTracker(config_high_decay)
        tracker_high.record_pack([_make_card("Elf Lord", ata=7.0)], pick_number=3, pack_number=0)
        score_high = tracker_high.get_scores()["BG Elves"]["score"]

        # Higher decay -> lower P(open)
        assert score_high < score_default < 0.5

    def test_config_default_opportunity_cost_decay(self):
        """Config without opportunity_cost_decay field gets default 0.1."""
        data = {"set_code": "TST", "scoring_method": "bayesian_beta"}
        config = ArchetypeConfig.model_validate(data)
        assert config.opportunity_cost_decay == 0.1


class TestATANormalization:
    """Tests for ATA-normalized signal in Bayesian/Simple paths."""

    def test_low_ata_card_produces_stronger_signal(self):
        """ATA-3 card at pick 8 should produce stronger signal than ATA-8 card at pick 13."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        # ATA 3 at pick 8: (8-3)/3 * 0.9 = 1.5 -> alpha = 2.5
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=8, pack_number=0)
        score_low_ata = tracker.get_scores()["BG Elves"]["score"]

        tracker.reset()
        # ATA 8 at pick 13: (13-8)/8 * 0.9 = 0.5625 -> alpha = 1.5625
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
