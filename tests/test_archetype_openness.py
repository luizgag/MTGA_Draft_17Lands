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


from src.archetype_openness import auto_detect_archetypes, calculate_card_weights
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
