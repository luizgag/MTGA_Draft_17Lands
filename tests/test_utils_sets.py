import pytest
import src.database as database
from src.utils import retrieve_all_local_sets


@pytest.fixture
def db_with_two_sets(tmp_path):
    """Create a temp DB with two datasets."""
    db_path = str(tmp_path / "test.db")
    database.save_dataset("ECL", {
        "meta": {"collection_date": "2026-02-28", "start_date": "2026-01-20",
                 "end_date": "2026-02-28", "version": 3.0, "game_count": 100000},
        "color_ratings": {"WU": 55.0},
        "card_ratings": {
            "1001": {"name": "TestCard", "cmc": 2, "mana_cost": "{1}{W}",
                     "isprimarycard": 1, "linkedfacetype": 0, "rarity": "common",
                     "colors": ["W"], "types": ["Creature"], "image": [],
                     "deck_colors": {"All Decks": {"gihwr": 55.0, "ohwr": 54.0,
                                                    "gpwr": 53.0, "gnswr": 52.0,
                                                    "gdwr": 51.0, "alsa": 5.0,
                                                    "ata": 4.0, "iwd": 3.0,
                                                    "ngp": 100, "ngoh": 50,
                                                    "gih": 80, "ngnd": 30,
                                                    "ngd": 20}}}
        },
    }, db_path)
    database.save_dataset("TMT", {
        "meta": {"collection_date": "2026-03-11", "start_date": "2026-03-03",
                 "end_date": "2026-03-11", "version": 3.0, "game_count": 50000},
        "color_ratings": {"BR": 52.0},
        "card_ratings": {},
    }, db_path)
    return db_path


def test_retrieve_all_local_sets_returns_all(db_with_two_sets):
    """Should return entries for ALL sets in the DB, not filtered."""
    file_list, error_list = retrieve_all_local_sets(db_path=db_with_two_sets)
    assert len(error_list) == 0
    set_codes = [f[0] for f in file_list]
    assert "ECL" in set_codes
    assert "TMT" in set_codes


def test_retrieve_all_local_sets_tuple_structure(db_with_two_sets):
    """Each entry should be a 7-tuple matching retrieve_local_set_list format."""
    file_list, _ = retrieve_all_local_sets(db_path=db_with_two_sets)
    for entry in file_list:
        assert len(entry) == 7
        set_name, event_type, user_group, start_date, end_date, game_count, file_location = entry
        assert event_type == ""
        assert user_group == ""
        assert isinstance(game_count, int)
        assert file_location.endswith("_Data.json")


def test_retrieve_all_local_sets_empty_db(tmp_path):
    """Should return empty list for empty DB."""
    db_path = str(tmp_path / "empty.db")
    file_list, error_list = retrieve_all_local_sets(db_path=db_path)
    assert file_list == []
    assert error_list == []
