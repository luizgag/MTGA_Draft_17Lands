import pytest
import json
import io
import zipfile
from unittest.mock import patch, MagicMock
from src.file_extractor import retrieve_goatbots_prices


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
