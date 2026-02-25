"""Tests for src/database.py — TDD for the SQLite persistence layer."""
import json
import os
import sqlite3
import pytest

from src.database import (
    init_db,
    save_dataset,
    load_dataset,
    delete_dataset,
    list_datasets,
    list_datasets_with_meta,
    save_configuration,
    load_configuration,
    save_archetype_config,
    load_archetype_config,
    save_trophy_analysis,
    load_trophy_analysis,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path):
    """Return path to a fresh temp database."""
    return str(tmp_path / "test.db")


SAMPLE_DATASET = {
    "meta": {
        "collection_date": "2024-01-01 00:00:00",
        "start_date": "2024-01-01",
        "end_date": "2024-06-01",
        "version": 2.0,
        "game_count": 1000,
    },
    "color_ratings": {
        "WU": 54.5,
        "WB": 52.1,
        "BG": 53.0,
    },
    "card_ratings": {
        "12345": {
            "name": "Test Card",
            "colors": ["W"],
            "types": ["Creature"],
            "rarity": "common",
            "cmc": 2,
            "mana_cost": "{1}{W}",
            "image": ["https://example.com/card.jpg"],
            "isprimarycard": 1,
            "linkedfacetype": 0,
            "deck_colors": {
                "All Decks": {
                    "gihwr": 55.0, "ohwr": 54.0, "gpwr": 53.0,
                    "gnswr": 50.0, "gdwr": 51.0, "alsa": 3.2,
                    "ata": 2.8, "iwd": 2.0,
                    "ngp": 1000, "ngoh": 800, "gih": 900, "ngnd": 100, "ngd": 700,
                },
                "W": {
                    "gihwr": 57.0, "ohwr": 56.0, "gpwr": 55.0,
                    "gnswr": 52.0, "gdwr": 53.0, "alsa": 3.0,
                    "ata": 2.5, "iwd": 3.0,
                    "ngp": 500, "ngoh": 400, "gih": 450, "ngnd": 50, "ngd": 350,
                },
            },
        },
        "67890": {
            "name": "Another Card",
            "colors": ["U", "B"],
            "types": ["Instant"],
            "rarity": "rare",
            "cmc": 3,
            "mana_cost": "{1}{U}{B}",
            "image": [],
            "isprimarycard": 1,
            "linkedfacetype": 0,
            "deck_colors": {
                "All Decks": {
                    "gihwr": 60.0, "ohwr": 59.0, "gpwr": 58.0,
                    "gnswr": 55.0, "gdwr": 57.0, "alsa": 2.1,
                    "ata": 1.9, "iwd": 4.0,
                    "ngp": 2000, "ngoh": 1800, "gih": 1900, "ngnd": 100, "ngd": 1500,
                },
            },
        },
    },
}

SAMPLE_CONFIG = {
    "settings": {"table_width": 300, "deck_filter": "Auto"},
    "features": {"hotkey_enabled": True},
}

SAMPLE_ARCHETYPE = {
    "set_code": "OTJ",
    "detection_threshold": 5.0,
    "scoring_method": "simple",
    "archetypes": [
        {"name": "Golgari", "color_pair": "BG", "auto_weights": True, "cards": {"Card A": 0.8}},
    ],
}

SAMPLE_TROPHY = {
    "meta": {"set_code": "OTJ", "format_name": "Traditional Draft"},
    "archetypes": [{"name": "WU", "trophy_wins": 15, "trophy_count": 5, "total_games": 1000}],
    "cards": [{"name": "Test Card", "trophy_wins": 10, "trophy_count": 3, "total_games": 500}],
}


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def test_init_db_creates_schema(db_path):
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    expected = {
        "dataset_meta", "color_ratings", "cards", "card_deck_stats",
        "archetypes_config", "trophy_analysis", "configuration",
    }
    assert expected.issubset(tables)


def test_init_db_is_idempotent(db_path):
    """Calling init_db twice does not raise or duplicate tables."""
    init_db(db_path)
    init_db(db_path)  # Should not raise
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cards'"
        ).fetchone()
    assert rows[0] == 1


# ---------------------------------------------------------------------------
# Dataset save / load round-trip
# ---------------------------------------------------------------------------

def test_save_and_load_dataset(db_path):
    save_dataset("OTJ", SAMPLE_DATASET, db_path)
    result = load_dataset("OTJ", db_path)

    assert result is not None
    assert result["meta"]["start_date"] == "2024-01-01"
    assert result["meta"]["end_date"] == "2024-06-01"
    assert result["meta"]["game_count"] == 1000
    assert result["meta"]["version"] == 2.0

    assert result["color_ratings"]["WU"] == 54.5
    assert result["color_ratings"]["WB"] == 52.1
    assert "BG" in result["color_ratings"]

    assert "12345" in result["card_ratings"]
    assert "67890" in result["card_ratings"]


def test_dataset_reconstructed_correctly(db_path):
    """Loaded dict structure exactly matches original card data."""
    save_dataset("OTJ", SAMPLE_DATASET, db_path)
    result = load_dataset("OTJ", db_path)

    card = result["card_ratings"]["12345"]
    assert card["name"] == "Test Card"
    assert card["cmc"] == 2
    assert card["mana_cost"] == "{1}{W}"
    assert card["colors"] == ["W"]
    assert card["types"] == ["Creature"]
    assert card["rarity"] == "common"
    assert card["isprimarycard"] == 1
    assert card["linkedfacetype"] == 0
    assert card["image"] == ["https://example.com/card.jpg"]

    all_decks = card["deck_colors"]["All Decks"]
    assert all_decks["gihwr"] == 55.0
    assert all_decks["ngp"] == 1000
    assert all_decks["gih"] == 900

    w_stats = card["deck_colors"]["W"]
    assert w_stats["gihwr"] == 57.0
    assert w_stats["ngp"] == 500

    card2 = result["card_ratings"]["67890"]
    assert card2["name"] == "Another Card"
    assert card2["colors"] == ["U", "B"]
    assert card2["image"] == []


def test_load_dataset_missing_returns_none(db_path):
    init_db(db_path)
    assert load_dataset("NONEXISTENT", db_path) is None


def test_load_dataset_no_db_returns_none(tmp_path):
    missing = str(tmp_path / "missing.db")
    assert load_dataset("OTJ", missing) is None


def test_price_field_is_persisted_and_loaded(db_path):
    """Price injected into card_ratings must survive save/load round-trip."""
    dataset_with_prices = {
        "meta": {"collection_date": "", "start_date": "", "end_date": "", "version": 1.0, "game_count": 100},
        "color_ratings": {},
        "card_ratings": {
            "11111": {
                "name": "Expensive Card",
                "colors": ["R"], "types": ["Creature"], "rarity": "mythic",
                "cmc": 5, "mana_cost": "{3}{R}{R}", "image": [],
                "isprimarycard": 1, "linkedfacetype": 0,
                "price": 12.5,
                "deck_colors": {},
            },
            "22222": {
                "name": "Cheap Card",
                "colors": ["W"], "types": ["Land"], "rarity": "common",
                "cmc": 0, "mana_cost": "", "image": [],
                "isprimarycard": 1, "linkedfacetype": 0,
                "price": 0.05,
                "deck_colors": {},
            },
            "33333": {
                "name": "No Price Card",
                "colors": [], "types": ["Instant"], "rarity": "uncommon",
                "cmc": 2, "mana_cost": "{1}{U}", "image": [],
                "isprimarycard": 1, "linkedfacetype": 0,
                "deck_colors": {},
            },
        },
    }
    save_dataset("OTJ", dataset_with_prices, db_path)
    result = load_dataset("OTJ", db_path)

    assert result["card_ratings"]["11111"]["price"] == 12.5
    assert result["card_ratings"]["22222"]["price"] == 0.05
    assert result["card_ratings"]["33333"].get("price", 0.0) == 0.0


def test_price_persisted_on_existing_db_without_price_column(tmp_path):
    """init_db on a DB created before the price column was added must add the column."""
    db_path = str(tmp_path / "old.db")
    # Simulate an old DB: create schema without price column
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS dataset_meta (
                set_code TEXT PRIMARY KEY,
                collection_date TEXT DEFAULT '',
                start_date TEXT DEFAULT '',
                end_date TEXT DEFAULT '',
                version REAL DEFAULT 0.0,
                game_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS color_ratings (
                set_code TEXT NOT NULL,
                color_pair TEXT NOT NULL,
                win_rate REAL NOT NULL,
                PRIMARY KEY (set_code, color_pair)
            );
            CREATE TABLE IF NOT EXISTS cards (
                arena_id TEXT NOT NULL,
                set_code TEXT NOT NULL,
                name TEXT NOT NULL,
                cmc INTEGER DEFAULT 0,
                mana_cost TEXT DEFAULT '',
                isprimarycard INTEGER DEFAULT 0,
                linkedfacetype INTEGER DEFAULT 0,
                rarity TEXT DEFAULT '',
                colors TEXT DEFAULT '[]',
                types TEXT DEFAULT '[]',
                image TEXT DEFAULT '[]',
                PRIMARY KEY (arena_id, set_code)
            );
            CREATE TABLE IF NOT EXISTS card_deck_stats (
                arena_id TEXT NOT NULL,
                set_code TEXT NOT NULL,
                color_filter TEXT NOT NULL,
                alsa REAL DEFAULT 0.0,
                ata REAL DEFAULT 0.0,
                iwd REAL DEFAULT 0.0,
                gihwr REAL DEFAULT 0.0,
                ohwr REAL DEFAULT 0.0,
                gpwr REAL DEFAULT 0.0,
                gnswr REAL DEFAULT 0.0,
                gdwr REAL DEFAULT 0.0,
                ngp INTEGER DEFAULT 0,
                ngoh INTEGER DEFAULT 0,
                gih INTEGER DEFAULT 0,
                ngnd INTEGER DEFAULT 0,
                ngd INTEGER DEFAULT 0,
                PRIMARY KEY (arena_id, set_code, color_filter)
            );
            CREATE TABLE IF NOT EXISTS archetypes_config (set_code TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trophy_analysis (set_code TEXT NOT NULL, format_name TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (set_code, format_name));
            CREATE TABLE IF NOT EXISTS configuration (id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), data TEXT NOT NULL);
        """)

    # init_db should migrate the old schema to add the price column
    init_db(db_path)

    # Should be able to save and load prices now
    dataset = {
        "meta": {"collection_date": "", "start_date": "", "end_date": "", "version": 1.0, "game_count": 50},
        "color_ratings": {},
        "card_ratings": {
            "99999": {
                "name": "Pricey", "colors": [], "types": [], "rarity": "rare",
                "cmc": 3, "mana_cost": "{2}{G}", "image": [],
                "isprimarycard": 1, "linkedfacetype": 0,
                "price": 7.25,
                "deck_colors": {},
            },
        },
    }
    save_dataset("MH3", dataset, db_path)
    result = load_dataset("MH3", db_path)
    assert result["card_ratings"]["99999"]["price"] == 7.25


def test_save_dataset_overwrites_existing(db_path):
    """Saving a dataset twice replaces the old data."""
    save_dataset("OTJ", SAMPLE_DATASET, db_path)

    updated = {
        "meta": {"start_date": "2025-01-01", "end_date": "2025-06-01", "game_count": 9999, "version": 3.0},
        "color_ratings": {"WU": 60.0},
        "card_ratings": {
            "99999": {
                "name": "New Card", "colors": ["R"], "types": ["Sorcery"],
                "rarity": "uncommon", "cmc": 3, "mana_cost": "{2}{R}",
                "image": [], "isprimarycard": 1, "linkedfacetype": 0,
                "deck_colors": {
                    "All Decks": {
                        "gihwr": 50.0, "ohwr": 50.0, "gpwr": 50.0,
                        "gnswr": 50.0, "gdwr": 50.0, "alsa": 5.0,
                        "ata": 4.0, "iwd": 0.0,
                        "ngp": 500, "ngoh": 400, "gih": 450, "ngnd": 50, "ngd": 350,
                    },
                },
            },
        },
    }
    save_dataset("OTJ", updated, db_path)
    result = load_dataset("OTJ", db_path)

    assert result["meta"]["game_count"] == 9999
    assert "12345" not in result["card_ratings"]  # Old card gone
    assert "99999" in result["card_ratings"]


# ---------------------------------------------------------------------------
# list_datasets / list_datasets_with_meta
# ---------------------------------------------------------------------------

def test_list_datasets(db_path):
    save_dataset("OTJ", SAMPLE_DATASET, db_path)
    save_dataset("MH3", SAMPLE_DATASET, db_path)
    result = list_datasets(db_path)
    assert set(result) == {"OTJ", "MH3"}


def test_list_datasets_empty_db(db_path):
    init_db(db_path)
    assert list_datasets(db_path) == []


def test_list_datasets_no_db(tmp_path):
    assert list_datasets(str(tmp_path / "missing.db")) == []


def test_list_datasets_with_meta(db_path):
    save_dataset("OTJ", SAMPLE_DATASET, db_path)
    rows = list_datasets_with_meta(db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["set_code"] == "OTJ"
    assert row["start_date"] == "2024-01-01"
    assert row["end_date"] == "2024-06-01"
    assert row["game_count"] == 1000


# ---------------------------------------------------------------------------
# delete_dataset
# ---------------------------------------------------------------------------

def test_delete_dataset(db_path):
    save_dataset("OTJ", SAMPLE_DATASET, db_path)
    save_dataset("MH3", SAMPLE_DATASET, db_path)

    delete_dataset("OTJ", db_path)

    assert "OTJ" not in list_datasets(db_path)
    assert "MH3" in list_datasets(db_path)
    assert load_dataset("OTJ", db_path) is None


def test_delete_dataset_removes_from_all_tables(db_path):
    save_dataset("OTJ", SAMPLE_DATASET, db_path)
    delete_dataset("OTJ", db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM color_ratings WHERE set_code='OTJ'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM cards WHERE set_code='OTJ'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM card_deck_stats WHERE set_code='OTJ'").fetchone()[0] == 0


def test_delete_nonexistent_set_is_noop(db_path):
    init_db(db_path)
    delete_dataset("NONEXISTENT", db_path)  # Should not raise


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def test_save_and_load_configuration(db_path):
    save_configuration(SAMPLE_CONFIG, db_path)
    result = load_configuration(db_path)
    assert result is not None
    assert result["settings"]["table_width"] == 300
    assert result["features"]["hotkey_enabled"] is True


def test_save_configuration_overwrites(db_path):
    save_configuration(SAMPLE_CONFIG, db_path)
    updated = {"settings": {"table_width": 999}}
    save_configuration(updated, db_path)
    result = load_configuration(db_path)
    assert result["settings"]["table_width"] == 999


def test_load_configuration_missing_returns_none(db_path):
    init_db(db_path)
    assert load_configuration(db_path) is None


def test_load_configuration_no_db_returns_none(tmp_path):
    assert load_configuration(str(tmp_path / "missing.db")) is None


# ---------------------------------------------------------------------------
# Archetype config
# ---------------------------------------------------------------------------

def test_save_and_load_archetype_config(db_path):
    save_archetype_config("OTJ", SAMPLE_ARCHETYPE, db_path)
    result = load_archetype_config("OTJ", db_path)
    assert result is not None
    assert result["set_code"] == "OTJ"
    assert result["archetypes"][0]["name"] == "Golgari"
    assert result["archetypes"][0]["cards"]["Card A"] == 0.8


def test_save_archetype_config_overwrites(db_path):
    save_archetype_config("OTJ", SAMPLE_ARCHETYPE, db_path)
    updated = {"set_code": "OTJ", "archetypes": []}
    save_archetype_config("OTJ", updated, db_path)
    result = load_archetype_config("OTJ", db_path)
    assert result["archetypes"] == []


def test_load_archetype_config_missing_returns_none(db_path):
    init_db(db_path)
    assert load_archetype_config("NONEXISTENT", db_path) is None


def test_load_archetype_config_no_db_returns_none(tmp_path):
    assert load_archetype_config("OTJ", str(tmp_path / "missing.db")) is None


def test_archetype_config_per_set_isolation(db_path):
    """Two sets do not share archetype config."""
    save_archetype_config("OTJ", SAMPLE_ARCHETYPE, db_path)
    assert load_archetype_config("MH3", db_path) is None


# ---------------------------------------------------------------------------
# Trophy analysis
# ---------------------------------------------------------------------------

def test_save_and_load_trophy_analysis(db_path):
    save_trophy_analysis("OTJ", "Traditional Draft", SAMPLE_TROPHY, db_path)
    result = load_trophy_analysis("OTJ", "Traditional Draft", db_path)
    assert result is not None
    assert result["meta"]["set_code"] == "OTJ"
    assert result["archetypes"][0]["name"] == "WU"
    assert result["cards"][0]["name"] == "Test Card"


def test_save_trophy_analysis_overwrites(db_path):
    save_trophy_analysis("OTJ", "Traditional Draft", SAMPLE_TROPHY, db_path)
    updated = {"meta": {"set_code": "OTJ", "format_name": "Traditional Draft"}, "archetypes": [], "cards": []}
    save_trophy_analysis("OTJ", "Traditional Draft", updated, db_path)
    result = load_trophy_analysis("OTJ", "Traditional Draft", db_path)
    assert result["archetypes"] == []


def test_load_trophy_analysis_missing_returns_none(db_path):
    init_db(db_path)
    assert load_trophy_analysis("OTJ", "Traditional Draft", db_path) is None


def test_load_trophy_analysis_no_db_returns_none(tmp_path):
    assert load_trophy_analysis("OTJ", "Traditional Draft", str(tmp_path / "missing.db")) is None


def test_trophy_analysis_per_format_isolation(db_path):
    """Different formats for same set are stored independently."""
    save_trophy_analysis("OTJ", "Traditional Draft", SAMPLE_TROPHY, db_path)
    assert load_trophy_analysis("OTJ", "Premier Draft", db_path) is None
