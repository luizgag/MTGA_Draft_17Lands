import pytest
from src.archetype_openness import OpennessTracker, Archetype, ArchetypeConfig
from tests.test_archetype_openness.helpers import _make_card, SIMPLE_CONFIG


class TestOpennessTrackerSimple:
    """Tests for simple scoring method: signal = pick / ata^2 * card_weight * pack_weight * 100."""

    def test_single_card_positive_signal(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=3.0)]
        tracker.record_pack(pack, pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        # 7/3^2 * 0.9 * 1.0 * 100 = 7/9 * 90 = 70.0
        assert scores["BG Elves"]["score"] == pytest.approx(70.0, abs=0.01)

    def test_single_card_small_signal_when_pick_early(self):
        """When picked earlier than usual (pick < ata), signal is smaller than when picked late."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Elf Lord", ata=7.0)]
        tracker.record_pack(pack, pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        # 3/7^2 * 0.9 * 1.0 * 100 = 3/49 * 90 ≈ 5.51
        assert scores["BG Elves"]["score"] == pytest.approx(5.510, abs=0.01)

    def test_multi_archetype_card(self):
        tracker = OpennessTracker(SIMPLE_CONFIG)
        pack = [_make_card("Murder", ata=4.0)]
        tracker.record_pack(pack, pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        # raw=8/4^2=0.5. BG: 0.5*0.2*100=10.0. UB: 0.5*0.7*100=35.0
        assert scores["BG Elves"]["score"] == pytest.approx(10.0, abs=0.01)
        assert scores["UB Control"]["score"] == pytest.approx(35.0, abs=0.01)

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
        # sig1=7/9*0.9*100=70.0, sig2=9/25*0.5*100=18.0. total=88.0
        assert scores["BG Elves"]["score"] == pytest.approx(88.0, abs=0.01)

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
        # 7/9 * 0.9 * 0.5 * 100 = 35.0
        assert scores["BG Elves"]["score"] == pytest.approx(35.0, abs=0.01)

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
