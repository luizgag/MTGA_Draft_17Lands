import pytest
import json
from typing import Tuple
from dataclasses import asdict

# Import the functions to be tested
from src.configuration import (
    read_configuration,
    write_configuration,
    reset_configuration,
    Configuration,
    DatasetSource,
    Features,
    Settings,
)


@pytest.fixture
def example_configuration():
    # Create an example Configuration object for testing
    config = Configuration()
    config.features.override_scale_factor = 1.5
    config.features.hotkey_enabled = True
    config.features.images_enabled = False
    return config


def test_read_configuration_existing_file(tmp_path, example_configuration):
    # Create a temporary file for testing
    file_location = tmp_path / "config.json"

    # Write the example configuration to the temporary file
    with open(file_location, "w") as f:
        json.dump(example_configuration.model_dump(), f)

    # Test reading the configuration from an existing file
    config, success = read_configuration(file_location)

    # Assert that the configuration was successfully read
    assert success is True

    # Assert that the returned configuration matches the example configuration
    assert config == example_configuration


def test_read_configuration_nonexistent_file(tmp_path):
    # Create a temporary file location for testing (nonexistent file)
    file_location = tmp_path / "nonexistent.json"

    # Test reading the configuration from a nonexistent file
    config, success = read_configuration(file_location)

    # Assert that the configuration was not successfully read
    assert success is False

    # Assert that the returned configuration is a new Configuration object
    assert isinstance(config, Configuration)
    assert config == Configuration()


def test_write_configuration(tmp_path, example_configuration):
    # Create a temporary file for testing
    file_location = tmp_path / "config.json"

    # Test writing the configuration
    success = write_configuration(example_configuration, file_location)

    # Assert that the configuration was successfully written
    assert success is True

    # Read the written configuration file
    with open(file_location, "r") as f:
        written_config = json.load(f)

    # Assert that the written configuration matches the example configuration
    assert written_config == example_configuration.model_dump()


def test_reset_configuration(tmp_path, example_configuration):
    # Create a temporary file for testing
    file_location = tmp_path / "config.json"

    # Write the example configuration to the temporary file
    with open(file_location, "w") as f:
        json.dump(example_configuration.model_dump(), f)

    # Test resetting the configuration
    success = reset_configuration(file_location)

    # Assert that the configuration was successfully reset
    assert success is True

    # Read the reset configuration file
    with open(file_location, "r") as f:
        reset_config = json.load(f)

    # Create a new empty Configuration object
    empty_config = Configuration()

    # Assert that the reset configuration matches the empty Configuration object
    assert reset_config == empty_config.model_dump()


def test_features_archetype_openness_default():
    """archetype_openness_enabled defaults to False."""
    features = Features()
    assert features.archetype_openness_enabled is False


def test_set_sources_default():
    """Settings.set_sources defaults to empty dict."""
    settings = Settings()
    assert settings.set_sources == {}


def test_set_sources_backward_compat(tmp_path):
    """Old config.json missing set_sources loads fine (empty dict)."""
    old_config = Configuration()
    config_dict = old_config.model_dump()
    del config_dict["settings"]["set_sources"]

    file_location = tmp_path / "config.json"
    with open(file_location, "w") as f:
        json.dump(config_dict, f)

    config, success = read_configuration(str(file_location))
    assert success is True
    assert config.settings.set_sources == {}


def test_old_dataset_sources_ignored(tmp_path):
    """Old config.json with dataset_sources key doesn't crash."""
    config_dict = Configuration().model_dump()
    config_dict["settings"]["dataset_sources"] = [
        {"format": "PremierDraft", "user_group": "All", "weight": 1.0}
    ]

    file_location = tmp_path / "config.json"
    with open(file_location, "w") as f:
        json.dump(config_dict, f)

    config, success = read_configuration(str(file_location))
    assert success is True
    assert config.settings.set_sources == {}


def test_old_config_with_date_fields_in_sources(tmp_path):
    """Old config.json with start_date/end_date in DatasetSource loads without error."""
    config_dict = Configuration().model_dump()
    config_dict["settings"]["set_sources"] = {
        "ECL": [
            {"format": "PremierDraft", "user_group": "All", "start_date": "2025-01-01", "end_date": "2025-06-01", "weight": 1.0},
        ]
    }

    file_location = tmp_path / "config.json"
    with open(file_location, "w") as f:
        json.dump(config_dict, f)

    config, success = read_configuration(str(file_location))
    assert success is True
    assert len(config.settings.set_sources["ECL"]) == 1
    assert config.settings.set_sources["ECL"][0].format == "PremierDraft"
    assert config.settings.set_sources["ECL"][0].weight == 1.0
    assert not hasattr(config.settings.set_sources["ECL"][0], "start_date") or "start_date" not in config.settings.set_sources["ECL"][0].model_fields


def test_set_sources_roundtrip(tmp_path):
    """Per-set sources survive write/read cycle."""
    config = Configuration()
    config.settings.set_sources = {
        "ECL": [
            DatasetSource(format="PremierDraft", user_group="All", weight=0.7),
            DatasetSource(format="TradDraft", user_group="Top", weight=0.3),
        ],
        "OTJ": [
            DatasetSource(format="QuickDraft", user_group="All", weight=1.0),
        ],
    }

    file_location = tmp_path / "config.json"
    write_configuration(config, str(file_location))
    loaded, success = read_configuration(str(file_location))

    assert success is True
    assert "ECL" in loaded.settings.set_sources
    assert "OTJ" in loaded.settings.set_sources
    assert len(loaded.settings.set_sources["ECL"]) == 2
    assert loaded.settings.set_sources["ECL"][0].format == "PremierDraft"
    assert loaded.settings.set_sources["ECL"][0].weight == 0.7
    assert loaded.settings.set_sources["ECL"][1].format == "TradDraft"
    assert loaded.settings.set_sources["ECL"][1].user_group == "Top"
    assert loaded.settings.set_sources["ECL"][1].weight == 0.3
    assert len(loaded.settings.set_sources["OTJ"]) == 1
    assert loaded.settings.set_sources["OTJ"][0].format == "QuickDraft"

