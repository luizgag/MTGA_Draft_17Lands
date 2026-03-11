import os
import pytest
from src.archetype_openness import auto_detect_archetypes, calculate_card_weights


class TestAutoDetect:
    def test_auto_detect_finds_color_pairs_above_threshold(self, otj_dataset):
        """Auto-detect returns color pairs whose total games exceed threshold % of all games."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        assert len(archetypes) > 0
        assert len(archetypes) < 25
        for arch in archetypes:
            assert arch.name
            assert arch.color_pair

    def test_auto_detect_with_zero_threshold_returns_all(self, otj_dataset):
        """Threshold of 0 returns all color pairs that have any games."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=0.0)
        assert len(archetypes) > 10

    def test_auto_detect_with_100_threshold_returns_none(self, otj_dataset):
        """Threshold of 100 returns no archetypes."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=100.0)
        assert len(archetypes) == 0

    def test_calculate_card_weights(self, otj_dataset):
        """Card weights are ngp(color_pair) / ngp(All Decks), between 0 and 1."""
        weights = calculate_card_weights(otj_dataset, "BG")
        assert len(weights) > 0
        for card_name, weight in weights.items():
            assert 0.0 < weight <= 1.0

    def test_calculate_card_weights_excludes_zero_ngp(self, otj_dataset):
        """Cards with 0 games in the color pair are not included."""
        weights = calculate_card_weights(otj_dataset, "BG")
        for card_name, weight in weights.items():
            assert weight > 0.0

    def test_weight_threshold_filters_generic_cards(self, otj_dataset):
        """Cards below threshold are excluded from auto-detected archetypes."""
        weights = calculate_card_weights(otj_dataset, "BG", threshold=0.4)
        for name, w in weights.items():
            assert w >= 0.4

    def test_threshold_zero_includes_all(self, otj_dataset):
        """Threshold of 0.0 should include all cards with any weight."""
        weights_zero = calculate_card_weights(otj_dataset, "BG", threshold=0.0)
        weights_high = calculate_card_weights(otj_dataset, "BG", threshold=0.4)
        assert len(weights_zero) >= len(weights_high)
