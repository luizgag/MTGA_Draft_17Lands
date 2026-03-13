import pytest
import json
import io
import zipfile
from unittest.mock import patch, MagicMock
from src.file_extractor import retrieve_goatbots_prices
from src import constants
from src.database import save_dataset
from src.dataset import Dataset
from src.card_logic.card_result import CardResult


def _make_zip(data_dict):
    """Helper: create an in-memory ZIP containing a single JSON file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # Use the first key as filename (doesn't matter, we read the first entry)
        zf.writestr("data.json", json.dumps(data_dict))
    return buf.getvalue()


@pytest.fixture
def mock_goatbots_data():
    """Fixture providing card definitions and price history as mock ZIP bytes."""
    card_definitions = {
        "100": {"name": "Lightning Bolt", "cardset": "ECL", "rarity": "Common", "version": "1", "foil": 0},
        "101": {"name": "Lightning Bolt", "cardset": "ECL", "rarity": "Common", "version": "2", "foil": 1},
        "102": {"name": "Moonshadow", "cardset": "ECL", "rarity": "Mythic", "version": "110", "foil": 0},
        "103": {"name": "Moonshadow", "cardset": "ECL", "rarity": "Mythic", "version": "310", "foil": 0},
        "104": {"name": "Island", "cardset": "ECL", "rarity": "Common", "version": "1", "foil": 0},
        "105": {"name": "Other Card", "cardset": "FDN", "rarity": "Rare", "version": "1", "foil": 0},
    }
    price_history = {
        "100": 0.05,
        "101": 0.10,
        "102": 27.12,
        "103": 15.00,
        "104": 0.01,
        "105": 5.00,
    }
    return _make_zip(card_definitions), _make_zip(price_history)


def test_retrieve_goatbots_prices_basic(mock_goatbots_data):
    """Prices returned for matching set, foil versions excluded."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("ECL")

    assert prices["Lightning Bolt"] == pytest.approx(0.05)
    assert prices["Moonshadow"] == pytest.approx(27.12)  # highest of 27.12 and 15.00
    assert prices["Island"] == pytest.approx(0.01)
    assert "Other Card" not in prices  # FDN set, not ECL


def test_retrieve_goatbots_prices_uses_highest_price(mock_goatbots_data):
    """When multiple regular versions exist, use the highest price."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("ECL")

    # Moonshadow has IDs 102 (27.12) and 103 (15.00) - should pick highest
    assert prices["Moonshadow"] == pytest.approx(27.12)


def test_retrieve_goatbots_prices_case_insensitive_set_code(mock_goatbots_data):
    """Set code matching should be case-insensitive."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("ecl")

    assert "Lightning Bolt" in prices
    assert "Moonshadow" in prices


def test_retrieve_goatbots_prices_empty_on_failure():
    """Return empty dict if download fails."""
    with patch("src.file_extractor.urllib.request.urlopen", side_effect=Exception("Network error")):
        prices = retrieve_goatbots_prices("ECL")

    assert prices == {}


def test_retrieve_goatbots_prices_no_matching_set(mock_goatbots_data):
    """Return empty dict when no cards match the requested set."""
    defs_zip, prices_zip = mock_goatbots_data

    mock_responses = [
        MagicMock(read=lambda b=defs_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
        MagicMock(read=lambda b=prices_zip: b, __enter__=lambda s: s, __exit__=lambda *a: None),
    ]

    with patch("src.file_extractor.urllib.request.urlopen", side_effect=mock_responses):
        prices = retrieve_goatbots_prices("NONEXISTENT")

    assert prices == {}


def test_price_data_survives_json_roundtrip(tmp_path):
    """Price field should persist through JSON save/load cycle (like export_card_data)."""
    card_data = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "1001": {"name": "Moonshadow", "price": 27.12, "deck_colors": {}},
            "1002": {"name": "Lightning Bolt", "price": 0.05, "deck_colors": {}},
        }
    }

    filepath = tmp_path / "ECL_Data.json"
    with open(filepath, "w") as f:
        json.dump(card_data, f)

    with open(filepath, "r") as f:
        loaded = json.load(f)

    assert loaded["card_ratings"]["1001"]["price"] == pytest.approx(27.12)
    assert loaded["card_ratings"]["1002"]["price"] == pytest.approx(0.05)


def test_price_survives_db_to_card_result_flow(tmp_path):
    """Price field should survive the full DB -> Dataset -> CardResult pipeline."""
    all_decks_stats = {
        "gihwr": 60.0, "ohwr": 58.0, "gpwr": 55.0, "gnswr": 57.0, "gdwr": 56.0,
        "alsa": 2.5, "ata": 3.0, "iwd": 5.0,
        "ngp": 1000, "ngoh": 800, "gih": 700, "ngnd": 200, "ngd": 150,
    }

    # Step 1: build dataset dict
    dataset = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "2001": {
                "name": "Expensive Card",
                "price": 27.12,
                "cmc": 3,
                "mana_cost": "{1}{W}{W}",
                "isprimarycard": 1,
                "linkedfacetype": 0,
                "rarity": "mythic",
                "colors": ["W"],
                "types": ["Creature"],
                "image": ["https://example.com/expensive.jpg"],
                "deck_colors": {"All Decks": dict(all_decks_stats)},
            },
            "2002": {
                "name": "Cheap Card",
                "price": 0.05,
                "cmc": 1,
                "mana_cost": "{R}",
                "isprimarycard": 1,
                "linkedfacetype": 0,
                "rarity": "common",
                "colors": ["R"],
                "types": ["Instant"],
                "image": ["https://example.com/cheap.jpg"],
                "deck_colors": {"All Decks": dict(all_decks_stats)},
            },
        },
    }

    # Step 2: save to temp DB
    db_path = str(tmp_path / "test.db")
    save_dataset("TMT", dataset, db_path=db_path)

    # Step 3: load via Dataset
    ds = Dataset()
    result = ds.open_set("TMT", db_path=db_path)
    assert result.name == "VALID"

    # Step 4: retrieve by name
    card_list = ds.get_data_by_name(["Expensive Card", "Cheap Card"])
    assert len(card_list) == 2

    # Price field must survive DB round-trip
    prices_by_name = {c["name"]: c.get(constants.DATA_FIELD_PRICE) for c in card_list}
    assert prices_by_name["Expensive Card"] == pytest.approx(27.12)
    assert prices_by_name["Cheap Card"] == pytest.approx(0.05)

    # Step 5: build CardResult with mocked dependencies
    mock_metrics = MagicMock()
    mock_metrics.get_metrics.return_value = (55.0, 5.0)

    mock_config = MagicMock()
    mock_config.settings.deck_filter = constants.FILTER_OPTION_ALL_DECKS
    mock_config.settings.result_format = "Rating"
    mock_config.settings.color_identity_enabled = False
    mock_config.settings.best_in_column_threshold = 10.0

    card_result = CardResult(
        set_metrics=mock_metrics,
        tier_data={},
        configuration=mock_config,
        pick_number=1,
    )

    # Step 6: call return_results
    fields = [constants.DATA_FIELD_NAME, constants.DATA_FIELD_GIHWR]
    results = card_result.return_results(card_list, ["All Decks"], fields)

    # Step 7: price field must still be present in returned cards
    assert len(results) == 2
    result_prices = {c["name"]: c.get(constants.DATA_FIELD_PRICE) for c in results}
    assert result_prices["Expensive Card"] == pytest.approx(27.12)
    assert result_prices["Cheap Card"] == pytest.approx(0.05)

    # Step 8: apply $$$ display logic (platform=MTGO, price_enabled=True, threshold=3.0)
    # Inline $$$ logic mirrors overlay.py:870-873; changes there must be reflected here
    threshold = 3.0
    for card in results:
        price = card.get(constants.DATA_FIELD_PRICE, 0.0)
        if price >= threshold and price > 0:
            card["results"][0] = f"$$$ {card['results'][0]}"

    names_in_results = [card["results"][0] for card in results]
    assert "$$$ Expensive Card" in names_in_results
    # Cheap Card (0.05) is below threshold — should NOT have $$$ prefix
    assert not any(n.startswith("$$$") and "Cheap" in n for n in names_in_results)


def test_price_isolation_between_sets(tmp_path):
    """Prices are stored and retrieved per-set; different sets don't contaminate each other."""
    all_decks_stats = {
        "gihwr": 50.0, "ohwr": 50.0, "gpwr": 50.0, "gnswr": 50.0, "gdwr": 50.0,
        "alsa": 3.0, "ata": 4.0, "iwd": 0.0,
        "ngp": 100, "ngoh": 80, "gih": 70, "ngnd": 20, "ngd": 15,
    }

    # Create dataset for SET_A with Shared Card at price 10.0
    dataset_a = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "3001": {
                "name": "Shared Card",
                "price": 10.0,
                "cmc": 2,
                "mana_cost": "{1}{W}",
                "isprimarycard": 1,
                "linkedfacetype": 0,
                "rarity": "common",
                "colors": ["W"],
                "types": ["Creature"],
                "image": [],
                "deck_colors": {"All Decks": dict(all_decks_stats)},
            },
        },
    }

    # Create dataset for SET_B with Shared Card at price 0.5
    dataset_b = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "4001": {
                "name": "Shared Card",
                "price": 0.5,
                "cmc": 2,
                "mana_cost": "{1}{W}",
                "isprimarycard": 1,
                "linkedfacetype": 0,
                "rarity": "common",
                "colors": ["W"],
                "types": ["Creature"],
                "image": [],
                "deck_colors": {"All Decks": dict(all_decks_stats)},
            },
        },
    }

    # Save both datasets to the same temp DB
    db_path = str(tmp_path / "test.db")
    save_dataset("SET_A", dataset_a, db_path=db_path)
    save_dataset("SET_B", dataset_b, db_path=db_path)

    # Load SET_A and retrieve Shared Card
    ds_a = Dataset()
    result_a = ds_a.open_set("SET_A", db_path=db_path)
    assert result_a.name == "VALID"

    card_list_a = ds_a.get_data_by_name(["Shared Card"])
    assert len(card_list_a) == 1
    assert card_list_a[0]["name"] == "Shared Card"
    assert card_list_a[0].get(constants.DATA_FIELD_PRICE) == pytest.approx(10.0)

    # Load SET_B and retrieve Shared Card
    ds_b = Dataset()
    result_b = ds_b.open_set("SET_B", db_path=db_path)
    assert result_b.name == "VALID"

    card_list_b = ds_b.get_data_by_name(["Shared Card"])
    assert len(card_list_b) == 1
    assert card_list_b[0]["name"] == "Shared Card"
    assert card_list_b[0].get(constants.DATA_FIELD_PRICE) == pytest.approx(0.5)
