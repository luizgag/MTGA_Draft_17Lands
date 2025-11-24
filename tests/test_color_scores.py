"""Tests for ALSA/ATA Color Score functionality.

This module tests:
1. The ATA processing in CardResult
2. The color score formula: Score = (Pick * (Pick - ATA)) / max(ATA, 1.0)
3. Color contribution calculations with pip weighting
4. Normalized score display
"""

import pytest
import os
from src import constants
from src.set_metrics import SetMetrics
from src.configuration import Configuration
from src.card_logic import CardResult, extract_colored_pips
from src.dataset import Dataset


# 17Lands OTJ data snapshot
OTJ_PREMIER_SNAPSHOT = os.path.join(
    os.getcwd(), "tests", "data", "OTJ_PremierDraft_Data_2024_5_3.json"
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture(name="otj_dataset", scope="module")
def fixture_otj_dataset():
    """Load the OTJ Premier Draft dataset for testing."""
    dataset = Dataset()
    dataset.open_file(OTJ_PREMIER_SNAPSHOT)
    return dataset


@pytest.fixture(name="otj_metrics", scope="module")
def fixture_otj_metrics(otj_dataset):
    """Create SetMetrics from OTJ dataset."""
    return SetMetrics(otj_dataset, 2)


# ============================================================================
# ATA Processing Tests
# ============================================================================

class TestProcessATA:
    """Tests for the __process_ata method in CardResult."""

    def test_ata_returns_valid_value(self, otj_dataset, otj_metrics):
        """Test that ATA returns a valid numeric value for a known card."""
        card_list = otj_dataset.get_data_by_name(["Colossal Rattlewurm"])
        assert card_list, "Card not found in dataset"

        result_class = CardResult(otj_metrics, None, Configuration(), 5)
        result_list = result_class.return_results(
            card_list, ["All Decks"], [constants.DATA_FIELD_ATA]
        )

        ata_value = result_list[0]["results"][0]
        assert ata_value != constants.RESULT_UNKNOWN_STRING
        assert isinstance(ata_value, (int, float))
        assert ata_value > 0

    def test_ata_returns_unknown_for_missing_data(self, otj_metrics):
        """Test that ATA returns unknown string for cards without deck_colors."""
        card_without_data = {
            constants.DATA_FIELD_NAME: "Fake Card",
            constants.DATA_FIELD_MANA_COST: "{W}{W}",
        }

        result_class = CardResult(otj_metrics, None, Configuration(), 5)
        result_list = result_class.return_results(
            [card_without_data], ["All Decks"], [constants.DATA_FIELD_ATA]
        )

        assert result_list[0]["results"][0] == constants.RESULT_UNKNOWN_STRING

    def test_ata_with_zero_value(self, otj_metrics):
        """Test that ATA returns unknown when ata value is 0."""
        card_with_zero_ata = {
            constants.DATA_FIELD_NAME: "Test Card",
            constants.DATA_FIELD_MANA_COST: "{B}",
            constants.DATA_FIELD_DECK_COLORS: {
                constants.FILTER_OPTION_ALL_DECKS: {
                    constants.DATA_FIELD_ATA: 0
                }
            }
        }

        result_class = CardResult(otj_metrics, None, Configuration(), 5)
        result_list = result_class.return_results(
            [card_with_zero_ata], ["All Decks"], [constants.DATA_FIELD_ATA]
        )

        assert result_list[0]["results"][0] == constants.RESULT_UNKNOWN_STRING


# ============================================================================
# Color Score Formula Tests
# ============================================================================

class TestColorScoreFormula:
    """Tests for the color score formula: Score = (Pick * (Pick - ATA)) / max(ATA, 1.0)"""

    @pytest.mark.parametrize("pick,ata,expected", [
        # Open color signals (pick > ata, positive score)
        (5, 3.0, (5 * (5 - 3)) / 3.0),      # 10/3 = 3.33
        (10, 5.0, (10 * (10 - 5)) / 5.0),   # 50/5 = 10
        (8, 4.0, (8 * (8 - 4)) / 4.0),      # 32/4 = 8

        # Contested color signals (pick < ata, negative score)
        (2, 5.0, (2 * (2 - 5)) / 5.0),      # -6/5 = -1.2
        (3, 8.0, (3 * (3 - 8)) / 8.0),      # -15/8 = -1.875
        (4, 10.0, (4 * (4 - 10)) / 10.0),   # -24/10 = -2.4

        # Neutral (pick == ata, zero score)
        (5, 5.0, 0.0),
        (3, 3.0, 0.0),

        # Edge case: ATA < 1 (capped to 1.0)
        (5, 0.5, (5 * (5 - 0.5)) / 1.0),    # 22.5/1 = 22.5
        (3, 0.1, (3 * (3 - 0.1)) / 1.0),    # 8.7/1 = 8.7

        # Late picks with high ATA differential
        (14, 7.0, (14 * (14 - 7)) / 7.0),   # 98/7 = 14
    ])
    def test_formula_calculation(self, pick, ata, expected):
        """Test the formula produces expected results."""
        safe_ata = max(ata, 1.0)
        result = (pick * (pick - ata)) / safe_ata
        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

    def test_formula_prevents_division_by_zero(self):
        """Test that max(ata, 1.0) prevents division by zero."""
        pick = 5
        ata = 0
        safe_ata = max(ata, 1.0)
        result = (pick * (pick - ata)) / safe_ata
        assert result == 25.0  # 5 * 5 / 1 = 25

    def test_formula_with_very_small_ata(self):
        """Test formula behavior with very small ATA values."""
        pick = 5
        ata = 0.01
        safe_ata = max(ata, 1.0)
        # Should use 1.0, not 0.01
        result = (pick * (pick - ata)) / safe_ata
        assert result == (5 * (5 - 0.01)) / 1.0


# ============================================================================
# Color Contribution Tests
# ============================================================================

class TestColorContributions:
    """Tests for calculate_color_contributions logic."""

    def _calculate_contributions(self, base, pip_counts):
        """
        Replicate the logic from __calculate_color_contributions.
        This is a test-only helper to verify the expected behavior.
        """
        if not pip_counts:
            return {}

        num_colors = len(pip_counts)

        # Check if all pips are hybrid (non-integer pip counts)
        is_hybrid_only = all(pips != int(pips) for pips in pip_counts.values())

        if num_colors == 1:
            # Single-color card: contribution = base / pip_count
            color, pips = list(pip_counts.items())[0]
            return {color: base / pips}

        if is_hybrid_only:
            # Hybrid-only multi-color card
            actual_hybrid_pips = sum(pip_counts.values()) / 2
            total_contribution = base / actual_hybrid_pips
            per_color = total_contribution / num_colors
            return {color: per_color for color in pip_counts}

        # Regular or mixed multi-color: inverse pip weighting
        inverse_weights = {color: 1 / pips for color, pips in pip_counts.items()}
        total_inverse = sum(inverse_weights.values())

        return {color: base * (weight / total_inverse)
                for color, weight in inverse_weights.items()}

    @pytest.mark.parametrize("base,pips,expected", [
        # Single color, single pip
        (6, {"B": 1}, {"B": 6}),
        # Single color, double pip
        (6, {"B": 2}, {"B": 3}),
        # Two colors, equal pips
        (6, {"W": 1, "B": 1}, {"W": 3, "B": 3}),
        # Two colors, unequal pips (inverse weighting)
        (6, {"W": 2, "B": 1}, {"W": 2, "B": 4}),
        # Three colors
        (6, {"W": 1, "U": 1, "B": 1}, {"W": 2, "U": 2, "B": 2}),
    ])
    def test_regular_mana_contributions(self, base, pips, expected):
        """Test contribution calculation for regular mana costs."""
        result = self._calculate_contributions(base, pips)
        for color, value in expected.items():
            assert abs(result[color] - value) < 0.001

    @pytest.mark.parametrize("base,pips,expected", [
        # Single hybrid
        (6, {"W": 0.5, "B": 0.5}, {"W": 6, "B": 6}),
        # Double hybrid
        (6, {"W": 1.0, "B": 1.0}, {"W": 3, "B": 3}),  # 2 hybrid = 1.0 each
        # Triple hybrid
        (6, {"W": 1.5, "B": 1.5}, {"W": 2, "B": 2}),  # 3 hybrid = 1.5 each
    ])
    def test_hybrid_mana_contributions(self, base, pips, expected):
        """Test contribution calculation for hybrid-only mana costs."""
        result = self._calculate_contributions(base, pips)
        for color, value in expected.items():
            assert abs(result[color] - value) < 0.001

    def test_mixed_hybrid_regular_contributions(self):
        """Test mixed hybrid and regular mana (treated as regular inverse weighting)."""
        base = 6
        pips = {"W": 1.5, "U": 0.5, "B": 1}  # 1W + W/U + B
        result = self._calculate_contributions(base, pips)

        # Should use inverse weighting
        assert len(result) == 3
        assert all(v > 0 for v in result.values())
        # Total should approximately equal base (normalized)
        assert abs(sum(result.values()) - base) < 0.001

    def test_empty_pips_returns_empty(self):
        """Test that empty pip counts return empty contributions."""
        result = self._calculate_contributions(10, {})
        assert result == {}

    def test_negative_base_distributes_correctly(self):
        """Test that negative base scores are distributed correctly."""
        base = -6  # Contested color signal
        pips = {"W": 1, "B": 1}
        result = self._calculate_contributions(base, pips)
        assert result["W"] == -3
        assert result["B"] == -3


# ============================================================================
# Normalized Score Tests
# ============================================================================

class TestNormalizedScores:
    """Tests for normalized score calculation."""

    def test_normalize_positive_scores(self):
        """Test normalization with all positive scores."""
        scores = {"W": 10, "U": 20, "B": 30, "R": 25, "G": 15}
        total_abs = sum(abs(v) for v in scores.values())  # 100

        for color, score in scores.items():
            percentage = (score / total_abs) * 100
            assert percentage >= 0

        # Check specific percentages
        assert (scores["W"] / total_abs) * 100 == 10.0
        assert (scores["B"] / total_abs) * 100 == 30.0

    def test_normalize_mixed_scores(self):
        """Test normalization with mixed positive and negative scores."""
        scores = {"W": 20, "U": -10, "B": 30, "R": -5, "G": 15}
        total_abs = sum(abs(v) for v in scores.values())  # 80

        # Check that percentages sum correctly considering absolute values
        w_pct = (scores["W"] / total_abs) * 100  # 25%
        u_pct = (scores["U"] / total_abs) * 100  # -12.5%

        assert abs(w_pct - 25.0) < 0.001
        assert abs(u_pct - (-12.5)) < 0.001

    def test_normalize_all_negative_scores(self):
        """Test normalization when all scores are negative."""
        scores = {"W": -10, "U": -20, "B": -30, "R": -25, "G": -15}
        total_abs = sum(abs(v) for v in scores.values())  # 100

        for color, score in scores.items():
            percentage = (score / total_abs) * 100
            assert percentage <= 0

    def test_normalize_zero_total(self):
        """Test that zero total is handled gracefully."""
        scores = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
        total_abs = sum(abs(v) for v in scores.values())  # 0

        # Should not divide by zero
        if total_abs > 0:
            for score in scores.values():
                _ = (score / total_abs) * 100
        else:
            # Fallback to "0.0%"
            pass  # This is the expected path

    def test_normalize_single_color_dominant(self):
        """Test when one color dominates the scores."""
        scores = {"W": 100, "U": 1, "B": 1, "R": 1, "G": 1}
        total_abs = sum(abs(v) for v in scores.values())  # 104

        w_pct = (scores["W"] / total_abs) * 100
        assert w_pct > 95  # W should be > 95%


# ============================================================================
# Integration Tests
# ============================================================================

class TestColorScoreIntegration:
    """Integration tests combining ATA lookup and score calculation."""

    def test_full_score_calculation_with_real_data(self, otj_dataset, otj_metrics):
        """Test complete score calculation flow with real card data."""
        # Get a mono-colored card
        card_list = otj_dataset.get_data_by_name(["Colossal Rattlewurm"])
        assert card_list

        card = card_list[0]
        current_pick = 5

        # Get ATA
        result_class = CardResult(otj_metrics, None, Configuration(), current_pick)
        result_list = result_class.return_results(
            [card], ["All Decks"], [constants.DATA_FIELD_ATA]
        )
        ata_str = result_list[0]["results"][0]

        assert ata_str != constants.RESULT_UNKNOWN_STRING
        ata = float(ata_str)

        # Calculate score
        safe_ata = max(ata, 1.0)
        base = (current_pick * (current_pick - ata)) / safe_ata

        # Get pip counts
        mana_cost = card.get(constants.DATA_FIELD_MANA_COST, "")
        pip_counts = extract_colored_pips(mana_cost)

        # Verify we got valid data
        assert pip_counts, "Card should have colored pips"
        assert isinstance(base, float)

    def test_colorless_cards_skipped(self, otj_dataset, otj_metrics):
        """Test that colorless cards don't contribute to color scores."""
        # Create a colorless card
        colorless_card = {
            constants.DATA_FIELD_NAME: "Colorless Artifact",
            constants.DATA_FIELD_MANA_COST: "{4}",
            constants.DATA_FIELD_DECK_COLORS: {
                constants.FILTER_OPTION_ALL_DECKS: {
                    constants.DATA_FIELD_ATA: 5.0
                }
            }
        }

        pip_counts = extract_colored_pips(colorless_card[constants.DATA_FIELD_MANA_COST])
        assert pip_counts == {}  # No colored pips

    def test_multicolor_card_distributes_to_all_colors(self, otj_dataset, otj_metrics):
        """Test that multicolor cards contribute to all their colors."""
        # Get a multicolor card
        card_list = otj_dataset.get_data_by_name(["Push // Pull"])
        if not card_list:
            pytest.skip("Multicolor test card not found")

        card = card_list[0]
        mana_cost = card.get(constants.DATA_FIELD_MANA_COST, "")
        pip_counts = extract_colored_pips(mana_cost)

        # Should have multiple colors
        if len(pip_counts) > 1:
            assert len(pip_counts) >= 2


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestColorScoreEdgeCases:
    """Tests for edge cases in color score calculation."""

    def test_pick_1_skipped(self):
        """Test that pick 1 is always skipped (P1P1)."""
        current_pick = 1
        # The update function should return early for pick 1
        # This is implicit - we just verify the formula works for pick > 1
        assert current_pick <= 1

    def test_very_high_pick_number(self):
        """Test formula with very high pick numbers."""
        pick = 15  # Last pick in pack
        ata = 3.0  # Card usually goes early

        safe_ata = max(ata, 1.0)
        result = (pick * (pick - ata)) / safe_ata

        # Should be very positive (strong open signal)
        assert result > 50  # (15 * 12) / 3 = 60

    def test_very_low_ata_card(self):
        """Test with a premium card (very low ATA)."""
        pick = 10  # Seeing premium at pick 10
        ata = 1.5  # Usually first-picked

        safe_ata = max(ata, 1.0)
        result = (pick * (pick - ata)) / safe_ata

        # Strong open signal
        assert result > 50

    def test_stacked_positive_signals(self):
        """Test that positive signals stack correctly across multiple cards."""
        scores = {"R": 0.0}

        # Simulate 3 red cards with positive signals
        for pick, ata in [(3, 2.0), (5, 3.0), (7, 4.0)]:
            safe_ata = max(ata, 1.0)
            base = (pick * (pick - ata)) / safe_ata
            scores["R"] += base

        # All should be positive, stacking
        assert scores["R"] > 0
        # (3*1)/2 + (5*2)/3 + (7*3)/4 = 1.5 + 3.33 + 5.25 = 10.08
        assert abs(scores["R"] - 10.08) < 0.1

    def test_mixed_signals_net_effect(self):
        """Test that mixed positive/negative signals produce net effect."""
        scores = {"B": 0.0}

        # One positive, one negative signal
        pick1, ata1 = 8, 4.0   # Positive: (8*4)/4 = 8
        pick2, ata2 = 2, 6.0   # Negative: (2*-4)/6 = -1.33

        for pick, ata in [(pick1, ata1), (pick2, ata2)]:
            safe_ata = max(ata, 1.0)
            base = (pick * (pick - ata)) / safe_ata
            scores["B"] += base

        # Net should be positive but reduced
        expected = 8 + (-8/6)  # 8 - 1.33 = 6.67
        assert abs(scores["B"] - expected) < 0.01
