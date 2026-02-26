import pytest
from src.archetype_openness import OpennessTracker, Archetype, ArchetypeConfig
from tests.test_archetype_openness.helpers import _make_card


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
        """Verify formula: -((pick + 1) / ata^2) * card_weight * passed_pack_weight * 100."""
        config = self._make_config(
            pack_weights=[1.0, 0.5, 1.0],
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=4.0)
        tracker.record_passed([card], pick_number=6, pack_number=0)
        # passed_pack_weights = [0.5, 1.0, 1.0], pack 0 weight = 0.5
        # -(6+1) / 4^2 * 1.0 * 0.5 * 100 = -7/16 * 50 = -21.875
        expected = -((6 + 1) / (4.0 ** 2)) * 1.0 * 0.5 * 100  # -21.875
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
        # -(1+1)/3^2 * 0.8 * 0.66 * 100 = -2/9 * 52.8 ≈ -11.733
        expected = -((1 + 1) / (3.0 ** 2)) * 0.8 * 0.66 * 100
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(expected, abs=0.01)

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

    def test_revert_with_current_pick_skips_same_pick(self):
        """When current_pick is provided, signals at that pick are not reverted."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=1, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0

        # Revert with current_pick=1: only reverts pick_number < 1 → nothing
        tracker.revert_returned(["Goblin Guide"], pack_number=0, current_pick=1)
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0

    def test_revert_with_current_pick_allows_earlier_pick(self):
        """When current_pick is provided, signals from earlier picks ARE reverted."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=1, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0

        # Revert with current_pick=9: pick_number 1 < 9 → reverted
        tracker.revert_returned(["Goblin Guide"], pack_number=0, current_pick=9)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_revert_without_current_pick_reverts_all(self):
        """Without current_pick (legacy behavior), all matching signals are reverted."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=1, pack_number=0)

        # No current_pick → legacy behavior, reverts everything
        tracker.revert_returned(["Goblin Guide"], pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)


class PassedCardsSimulator:
    """Simulates overlay's passed-cards detection loop for testing."""

    def __init__(self, tracker, number_of_players=8):
        self.tracker = tracker
        self._prev_pack_for_passed = []
        self._prev_pick_for_passed = 0
        self._prev_pack_number_for_passed = 0
        self._prev_taken_count = 0
        self._number_of_players = number_of_players
        self._initial_packs = {}

    def set_initial_pack(self, pick_number, cards):
        pack_index = max(pick_number - 1, 0) % self._number_of_players
        self._initial_packs[pack_index] = list(cards)

    def _retrieve_initial_pack(self, pick_number):
        pack_index = max(pick_number - 1, 0) % self._number_of_players
        return list(self._initial_packs.get(pack_index, []))

    def update(self, taken_cards, pack_cards, pick_in_pack, current_pack):
        current_taken_count = len(taken_cards)
        if current_taken_count > self._prev_taken_count:
            num_new_picks = current_taken_count - self._prev_taken_count
            new_picks = taken_cards[self._prev_taken_count:]
            picked_names = [c.get("name", "") for c in new_picks]
            if self._prev_pack_for_passed:
                passed = list(self._prev_pack_for_passed)
                for name in picked_names:
                    for j, c in enumerate(passed):
                        if c.get("name", "") == name:
                            passed.pop(j)
                            break
                if passed:
                    self.tracker.record_passed(
                        passed, self._prev_pick_for_passed,
                        self._prev_pack_number_for_passed)
            else:
                fallback_pick = max(pick_in_pack - num_new_picks, 1)
                initial = self._retrieve_initial_pack(fallback_pick)
                if initial:
                    passed = list(initial)
                    for name in picked_names:
                        for j, c in enumerate(passed):
                            if c.get("name", "") == name:
                                passed.pop(j)
                                break
                    if passed:
                        self.tracker.record_passed(
                            passed, fallback_pick, current_pack - 1)

        pack_card_names = [c.get("name", "") for c in pack_cards]
        self.tracker.revert_returned(pack_card_names, current_pack - 1,
                                     current_pick=pick_in_pack)

        self._prev_pack_for_passed = list(pack_cards)
        self._prev_pick_for_passed = pick_in_pack
        self._prev_pack_number_for_passed = current_pack - 1
        self._prev_taken_count = current_taken_count


class TestPassedCardsDetection:
    """Integration tests for the overlay's passed-cards detection timing."""

    DETECTION_CONFIG = ArchetypeConfig(
        set_code="TST",
        scoring_method="simple",
        pack_weights=[1.0, 1.0, 1.0],
        archetypes=[
            Archetype(
                name="Goblins",
                color_pair="RG",
                auto_weights=False,
                cards={
                    "Goblin Guide": 0.9,
                    "Raging Goblin": 0.7,
                    "Goblin Piker": 0.5,
                    "Shock": 0.3,
                    "Lightning Bolt": 0.4,
                    "Goblin Warchief": 0.8,
                    "Mogg Fanatic": 0.6,
                },
            ),
        ],
    )

    @staticmethod
    def _pack(*names_and_atas):
        return [_make_card(name, ata) for name, ata in names_and_atas]

    def test_single_pick_per_cycle(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        pack_a = self._pack(("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Shock", 4.0))
        sim.update(taken_cards=[], pack_cards=pack_a, pick_in_pack=1, current_pack=1)
        assert len(tracker.passed_signals) == 0

        taken = [_make_card("Goblin Guide", 2.0)]
        pack_b = self._pack(("Goblin Piker", 6.0), ("Lightning Bolt", 3.0))
        sim.update(taken_cards=taken, pack_cards=pack_b, pick_in_pack=2, current_pack=1)

        passed_cards = {s["card_name"] for s in tracker.passed_signals}
        assert "Raging Goblin" in passed_cards
        assert "Shock" in passed_cards
        assert all(s["pick_number"] == 1 for s in tracker.passed_signals)
        assert all(s["pack_number"] == 0 for s in tracker.passed_signals)

    def test_pick_without_prior_snapshot_uses_initial_pack(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        pack_pick1 = self._pack(
            ("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Shock", 4.0))
        sim.set_initial_pack(1, pack_pick1)
        pack_pick2 = self._pack(
            ("Lightning Bolt", 3.0), ("Goblin Piker", 6.0), ("Goblin Warchief", 4.0))
        sim.set_initial_pack(2, pack_pick2)

        taken = [
            _make_card("Goblin Guide", 2.0),
            _make_card("Lightning Bolt", 3.0),
        ]
        pack_pick3 = self._pack(("Mogg Fanatic", 7.0),)
        sim.update(taken_cards=taken, pack_cards=pack_pick3, pick_in_pack=3, current_pack=1)

        passed_cards = {s["card_name"] for s in tracker.passed_signals}
        assert "Raging Goblin" in passed_cards
        assert "Shock" in passed_cards

    def test_multiple_picks_in_single_cycle(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        pack_a = self._pack(
            ("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Shock", 4.0),
            ("Lightning Bolt", 3.0), ("Goblin Piker", 6.0),
        )
        sim.update(taken_cards=[], pack_cards=pack_a, pick_in_pack=1, current_pack=1)

        taken = [
            _make_card("Goblin Guide", 2.0),
            _make_card("Raging Goblin", 5.0),
            _make_card("Shock", 4.0),
        ]
        pack_d = self._pack(("Goblin Warchief", 4.0), ("Mogg Fanatic", 7.0))
        sim.update(taken_cards=taken, pack_cards=pack_d, pick_in_pack=4, current_pack=1)

        passed_cards = {s["card_name"] for s in tracker.passed_signals}
        assert "Lightning Bolt" in passed_cards
        assert "Goblin Piker" in passed_cards
        assert all(s["pick_number"] == 1 for s in tracker.passed_signals)

    def test_first_pick_of_draft_with_initial_pack(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        full_pack = self._pack(
            ("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Shock", 4.0))
        sim.set_initial_pack(1, full_pack)

        taken = [_make_card("Goblin Guide", 2.0)]
        sim.update(taken_cards=taken, pack_cards=full_pack, pick_in_pack=1, current_pack=1)

        passed_cards = {s["card_name"] for s in tracker.passed_signals}
        assert "Raging Goblin" in passed_cards
        assert "Shock" in passed_cards
        assert all(s["pick_number"] == 1 for s in tracker.passed_signals)

    def test_first_pick_no_initial_pack_skipped(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        taken = [_make_card("Goblin Guide", 2.0)]
        remaining = self._pack(("Raging Goblin", 5.0), ("Shock", 4.0))
        sim.update(taken_cards=taken, pack_cards=remaining, pick_in_pack=1, current_pack=1)

        assert len(tracker.passed_signals) == 0

    def test_fallback_uses_initial_pack_correctly(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        original_pack = self._pack(
            ("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Shock", 4.0))
        sim.set_initial_pack(1, original_pack)

        taken = [_make_card("Goblin Guide", 2.0)]
        pack_b = self._pack(("Goblin Warchief", 4.0), ("Mogg Fanatic", 7.0))
        sim.update(taken_cards=taken, pack_cards=pack_b,
                   pick_in_pack=2, current_pack=1)

        passed_names = {s["card_name"] for s in tracker.passed_signals}
        assert "Raging Goblin" in passed_names
        assert "Shock" in passed_names
        assert all(s["pick_number"] == 1 for s in tracker.passed_signals)

    def test_wheeling_still_reverts_correctly(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        pack_a = self._pack(("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Shock", 4.0))
        sim.update(taken_cards=[], pack_cards=pack_a, pick_in_pack=1, current_pack=1)

        taken = [_make_card("Goblin Guide", 2.0)]
        pack_b = self._pack(("Lightning Bolt", 3.0), ("Goblin Piker", 6.0))
        sim.update(taken_cards=taken, pack_cards=pack_b, pick_in_pack=2, current_pack=1)

        assert any(s["card_name"] == "Raging Goblin" for s in tracker.passed_signals)

        taken.append(_make_card("Lightning Bolt", 3.0))
        pack_c = self._pack(("Raging Goblin", 5.0), ("Mogg Fanatic", 7.0))
        sim.update(taken_cards=taken, pack_cards=pack_c, pick_in_pack=9, current_pack=1)

        rg_signals = [s for s in tracker.passed_signals if s["card_name"] == "Raging Goblin"]
        assert len(rg_signals) == 0
        assert any(s["card_name"] == "Shock" for s in tracker.passed_signals)

    def test_normal_flow_across_pack_boundary(self):
        tracker = OpennessTracker(self.DETECTION_CONFIG)
        sim = PassedCardsSimulator(tracker)

        pack_a = self._pack(
            ("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Goblin Piker", 6.0),
        )
        sim.update(taken_cards=[], pack_cards=pack_a, pick_in_pack=1, current_pack=1)

        taken = [_make_card("Goblin Guide", 2.0)]
        pack_b = self._pack(("Shock", 4.0), ("Lightning Bolt", 3.0))
        sim.update(taken_cards=taken, pack_cards=pack_b, pick_in_pack=2, current_pack=1)

        p1_passed = [s for s in tracker.passed_signals if s["pack_number"] == 0]
        p1_names = {s["card_name"] for s in p1_passed}
        assert "Raging Goblin" in p1_names
        assert "Goblin Piker" in p1_names

        taken.append(_make_card("Shock", 4.0))
        pack_c = self._pack(("Mogg Fanatic", 7.0), ("Goblin Warchief", 4.0))
        sim.update(taken_cards=taken, pack_cards=pack_c, pick_in_pack=3, current_pack=1)

        p1_pick2 = [s for s in tracker.passed_signals
                    if s["pack_number"] == 0 and s["pick_number"] == 2]
        assert any(s["card_name"] == "Lightning Bolt" for s in p1_pick2)

        pack_d = self._pack(
            ("Goblin Guide", 2.0), ("Raging Goblin", 5.0), ("Lightning Bolt", 3.0),
        )
        sim.update(taken_cards=taken, pack_cards=pack_d, pick_in_pack=1, current_pack=2)

        taken.append(_make_card("Goblin Guide", 2.0))
        pack_e = self._pack(("Goblin Piker", 6.0), ("Mogg Fanatic", 7.0))
        sim.update(taken_cards=taken, pack_cards=pack_e, pick_in_pack=2, current_pack=2)

        p2_passed = [s for s in tracker.passed_signals if s["pack_number"] == 1]
        p2_names = {s["card_name"] for s in p2_passed}
        assert "Raging Goblin" in p2_names
        assert "Lightning Bolt" in p2_names
        assert all(s["pick_number"] == 1 for s in p2_passed)
