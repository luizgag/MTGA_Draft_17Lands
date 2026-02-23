"""Tests for src/migration.py — JSON → SQLite migration."""
import json
import os
import pytest

from src.migration import migrate_json_to_sqlite
from src.database import (
    load_configuration,
    load_dataset,
    load_archetype_config,
    load_trophy_analysis,
    list_datasets,
)


@pytest.fixture
def migration_env(tmp_path):
    """Build a fake project layout with JSON files for migration testing."""
    # Sets/
    sets_dir = tmp_path / "Sets"
    sets_dir.mkdir()

    otj_data = {
        "meta": {"start_date": "2024-01-01", "end_date": "2024-06-01",
                 "game_count": 1000, "version": 2.0, "collection_date": ""},
        "color_ratings": {"WU": 54.5},
        "card_ratings": {
            "12345": {
                "name": "Migrate Card",
                "colors": ["W"],
                "types": ["Creature"],
                "rarity": "common",
                "cmc": 2,
                "mana_cost": "{1}{W}",
                "image": [],
                "isprimarycard": 1,
                "linkedfacetype": 0,
                "deck_colors": {
                    "All Decks": {
                        "gihwr": 55.0, "ohwr": 54.0, "gpwr": 53.0,
                        "gnswr": 50.0, "gdwr": 51.0, "alsa": 3.2,
                        "ata": 2.8, "iwd": 2.0,
                        "ngp": 100, "ngoh": 80, "gih": 90, "ngnd": 10, "ngd": 70,
                    },
                },
            },
        },
    }
    (sets_dir / "OTJ_Data.json").write_text(json.dumps(otj_data))

    # Should NOT be migrated (4-segment)
    (sets_dir / "OTJ_PremierDraft_All_Data.json").write_text(json.dumps(otj_data))

    # Archetypes/
    arch_dir = tmp_path / "Archetypes"
    arch_dir.mkdir()
    arch_data = {
        "set_code": "OTJ",
        "detection_threshold": 5.0,
        "scoring_method": "simple",
        "archetypes": [{"name": "Golgari", "color_pair": "BG", "auto_weights": True, "cards": {}}],
    }
    (arch_dir / "OTJ_archetypes.json").write_text(json.dumps(arch_data))

    # Trophy/
    trophy_dir = tmp_path / "Trophy"
    trophy_dir.mkdir()
    trophy_data = {
        "meta": {"set_code": "OTJ", "format_name": "TradDraft"},
        "archetypes": [],
        "cards": [],
    }
    (trophy_dir / "Trophy_OTJ_TradDraft.json").write_text(json.dumps(trophy_data))

    # config.json
    config_data = {
        "settings": {"table_width": 300},
        "features": {"hotkey_enabled": True},
    }
    (tmp_path / "config.json").write_text(json.dumps(config_data))

    db_path = str(tmp_path / "test.db")
    return tmp_path, db_path


def test_migrate_sets_json(migration_env, monkeypatch):
    """migrate_json_to_sqlite imports 2-segment Sets/*.json into DB."""
    tmp_path, db_path = migration_env

    monkeypatch.chdir(tmp_path)

    count, errors = migrate_json_to_sqlite(db_path)

    assert not errors
    sets = list_datasets(db_path)
    assert "OTJ" in sets


def test_migrate_only_two_segment_files(migration_env, monkeypatch):
    """4-segment files are NOT migrated."""
    tmp_path, db_path = migration_env

    monkeypatch.chdir(tmp_path)

    migrate_json_to_sqlite(db_path)

    # Only "OTJ" (2-segment) should be there, not "OTJ_PremierDraft_All"
    sets = list_datasets(db_path)
    assert sets == ["OTJ"]


def test_migrate_config_json(migration_env, monkeypatch):
    """migrate_json_to_sqlite imports config.json into DB."""
    tmp_path, db_path = migration_env

    monkeypatch.chdir(tmp_path)

    migrate_json_to_sqlite(db_path)

    config = load_configuration(db_path)
    assert config is not None
    assert config["settings"]["table_width"] == 300


def test_migrate_archetypes_json(migration_env, monkeypatch):
    """migrate_json_to_sqlite imports Archetypes/*.json into DB."""
    tmp_path, db_path = migration_env

    monkeypatch.chdir(tmp_path)

    migrate_json_to_sqlite(db_path)

    arch = load_archetype_config("OTJ", db_path)
    assert arch is not None
    assert arch["archetypes"][0]["name"] == "Golgari"


def test_migrate_trophy_json(migration_env, monkeypatch):
    """migrate_json_to_sqlite imports Trophy/*.json into DB."""
    tmp_path, db_path = migration_env

    monkeypatch.chdir(tmp_path)

    migrate_json_to_sqlite(db_path)

    trophy = load_trophy_analysis("OTJ", "TradDraft", db_path)
    assert trophy is not None
    assert trophy["meta"]["set_code"] == "OTJ"


def test_migrate_returns_count(migration_env, monkeypatch):
    """migrate_json_to_sqlite returns correct count of migrated items."""
    tmp_path, db_path = migration_env

    monkeypatch.chdir(tmp_path)

    count, errors = migrate_json_to_sqlite(db_path)

    # Expected: 1 config + 1 set (OTJ) + 1 archetype + 1 trophy = 4
    assert count == 4
    assert errors == []


def test_migrate_missing_dirs_is_safe(tmp_path):
    """Migration with no Sets/, Archetypes/, Trophy/ folders doesn't crash."""
    db_path = str(tmp_path / "test.db")
    # Only create config.json, no folders
    (tmp_path / "config.json").write_text(json.dumps({"settings": {}}))

    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        count, errors = migrate_json_to_sqlite(db_path)
    finally:
        os.chdir(old_cwd)

    assert errors == []
    assert count == 1  # just config
