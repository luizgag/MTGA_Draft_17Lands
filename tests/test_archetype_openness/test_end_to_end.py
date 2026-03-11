import pytest
from src.archetype_openness import (
    OpennessTracker, Archetype, ArchetypeConfig, auto_detect_archetypes,
)


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
