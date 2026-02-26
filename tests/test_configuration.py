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
    CardDataSettings,
    DatasetSource,
    Features,
    Settings,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_config.db")


@pytest.fixture
def example_configuration():
    # Create an example Configuration object for testing
    config = Configuration()
    config.features.override_scale_factor = 1.5
    config.features.hotkey_enabled = True
    config.features.images_enabled = False
    return config


def test_read_configuration_existing(db_path, example_configuration):
    # Write the example configuration to the DB
    write_configuration(example_configuration, db_path)

    # Test reading the configuration from the DB
    config, success = read_configuration(db_path)

    # Assert that the configuration was successfully read
    assert success is True

    # Assert that the returned configuration matches the example configuration
    assert config == example_configuration


def test_read_configuration_empty_db(db_path):
    """Reading from a DB with no config row returns defaults and success=False."""
    from src.database import init_db
    init_db(db_path)

    config, success = read_configuration(db_path)

    # Assert that the configuration was not successfully read (no row)
    assert success is False

    # Assert that the returned configuration is a default Configuration object
    assert isinstance(config, Configuration)
    assert config == Configuration()


def test_read_configuration_missing_db(tmp_path):
    """Reading from a non-existent DB returns defaults and success=False."""
    missing = str(tmp_path / "nonexistent.db")

    config, success = read_configuration(missing)

    assert success is False
    assert isinstance(config, Configuration)
    assert config == Configuration()


def test_write_configuration(db_path, example_configuration):
    # Test writing the configuration
    success = write_configuration(example_configuration, db_path)

    # Assert that the configuration was successfully written
    assert success is True

    # Verify round-trip
    config, read_success = read_configuration(db_path)
    assert read_success is True
    assert config == example_configuration


def test_reset_configuration(db_path, example_configuration):
    # Write the example configuration to the DB
    write_configuration(example_configuration, db_path)

    # Test resetting the configuration
    success = reset_configuration(db_path)

    # Assert that the configuration was successfully reset
    assert success is True

    # Read the reset configuration
    reset_config, read_success = read_configuration(db_path)

    # Assert that the reset configuration matches the empty Configuration object
    assert read_success is True
    assert reset_config == Configuration()


def test_features_archetype_openness_default():
    """archetype_openness_enabled defaults to False."""
    features = Features()
    assert features.archetype_openness_enabled is False


def test_set_sources_default():
    """Settings.set_sources defaults to empty dict."""
    settings = Settings()
    assert settings.set_sources == {}


def test_set_sources_backward_compat(db_path):
    """Config missing set_sources loads fine (empty dict)."""
    old_config = Configuration()
    config_dict = old_config.model_dump()
    del config_dict["settings"]["set_sources"]

    from src.database import save_configuration
    save_configuration(config_dict, db_path)

    config, success = read_configuration(db_path)
    assert success is True
    assert config.settings.set_sources == {}


def test_old_dataset_sources_ignored(db_path):
    """Config with dataset_sources key doesn't crash."""
    config_dict = Configuration().model_dump()
    config_dict["settings"]["dataset_sources"] = [
        {"format": "PremierDraft", "user_group": "All", "weight": 1.0}
    ]

    from src.database import save_configuration
    save_configuration(config_dict, db_path)

    config, success = read_configuration(db_path)
    assert success is True
    assert config.settings.set_sources == {}


def test_old_config_with_date_fields_in_sources(db_path):
    """Config with start_date/end_date in DatasetSource loads without error."""
    config_dict = Configuration().model_dump()
    config_dict["settings"]["set_sources"] = {
        "ECL": [
            {"format": "PremierDraft", "user_group": "All", "start_date": "2025-01-01", "end_date": "2025-06-01", "weight": 1.0},
        ]
    }

    from src.database import save_configuration
    save_configuration(config_dict, db_path)

    config, success = read_configuration(db_path)
    assert success is True
    assert len(config.settings.set_sources["ECL"]) == 1
    assert config.settings.set_sources["ECL"][0].format == "PremierDraft"
    assert config.settings.set_sources["ECL"][0].enabled is True
    assert not hasattr(config.settings.set_sources["ECL"][0], "start_date") or "start_date" not in config.settings.set_sources["ECL"][0].model_fields


def test_datasetsource_default_enabled():
    """DatasetSource defaults to enabled=True."""
    source = DatasetSource()
    assert source.enabled is True


def test_datasetsource_enabled_roundtrip(db_path):
    """enabled field survives write/read cycle."""
    config = Configuration()
    config.settings.set_sources = {
        "ECL": [
            DatasetSource(format="PremierDraft", user_group="All", enabled=True),
            DatasetSource(format="TradDraft", user_group="Top", enabled=False),
        ],
    }
    write_configuration(config, db_path)
    loaded, success = read_configuration(db_path)

    assert success is True
    assert loaded.settings.set_sources["ECL"][0].enabled is True
    assert loaded.settings.set_sources["ECL"][1].enabled is False


def test_datasetsource_weight_migrates_to_enabled(db_path):
    """Old config with weight field is migrated: weight>0 → enabled=True, weight=0 → enabled=False."""
    config_dict = Configuration().model_dump()
    config_dict["settings"]["set_sources"] = {
        "ECL": [
            {"format": "PremierDraft", "user_group": "All", "weight": 1.0},
            {"format": "TradDraft", "user_group": "Top", "weight": 0.0},
        ]
    }

    from src.database import save_configuration
    save_configuration(config_dict, db_path)

    config, success = read_configuration(db_path)

    assert success is True
    assert config.settings.set_sources["ECL"][0].enabled is True
    assert config.settings.set_sources["ECL"][1].enabled is False


def test_card_data_settings_defaults():
    s = CardDataSettings()
    assert s.col_rarity is True
    assert s.col_gihwr is True
    assert s.col_ohwr is False
    assert s.col_gpwr is False
    assert s.col_gnswr is False
    assert s.col_gdwr is False
    assert s.col_ata is True
    assert s.col_alsa is True
    assert s.col_iwd is False
    assert s.col_wheel is False
    assert s.col_colors is True
    assert s.col_ngp is False
    assert s.col_gih is False


def test_configuration_has_card_data_settings():
    config = Configuration()
    assert hasattr(config, "card_data_settings")
    assert isinstance(config.card_data_settings, CardDataSettings)


def test_import_configuration_does_not_create_db(tmp_path, monkeypatch):
    """Importing configuration module must NOT create a DB file as a side effect."""
    monkeypatch.chdir(tmp_path)
    import importlib
    import src.configuration as cfg_mod
    importlib.reload(cfg_mod)
    assert not (tmp_path / "mtga_draft.db").exists(), (
        "configuration module created mtga_draft.db as a side effect"
    )
