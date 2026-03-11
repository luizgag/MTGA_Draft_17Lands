import pytest
from src.archetype_openness import OpennessTracker, Archetype, ArchetypeConfig
from tests.test_archetype_openness.helpers import _make_card


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
