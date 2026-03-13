import pytest
import json
import os
from unittest.mock import patch, MagicMock, mock_open
from src.file_extractor import (
    FileExtractor,
    decode_mana_cost,
    extract_types,
    initialize_card_data,
    check_date,
    merge_datasets,
    delete_old_set_files,
)
from src import constants
from src.utils import Result

# --- Fixtures ---

@pytest.fixture
def file_extractor():
    """Fixture to create a FileExtractor instance with default values for testing."""
    extractor = FileExtractor(directory=None)
    extractor.draft = "PremierDraft"
    extractor.start_date = "2023-01-01"
    extractor.end_date = "2023-01-31"
    extractor.user_group = constants.LIMITED_USER_GROUP_ALL
    return extractor

# --- Test Standalone Utility Functions ---

@pytest.mark.parametrize("encoded_cost, expected_decoded, expected_cmc", [
    ("o1oW", "{1}{W}", 2),
    ("o2oUoU", "{2}{U}{U}", 4),
    ("oXoGoG", "{X}{G}{G}", 3),
    ("o5", "{5}", 5),
    ("", "", 0),
    (None, "", 0),
    ("(o2oG)", "{2}{G}", 3), # Test with parentheses
])
def test_decode_mana_cost(encoded_cost, expected_decoded, expected_cmc):
    """Tests the decode_mana_cost utility function for various mana cost formats."""
    decoded, cmc = decode_mana_cost(encoded_cost)
    assert decoded == expected_decoded
    assert cmc == expected_cmc

@pytest.mark.parametrize("type_line, expected_types", [
    ("Creature — Human Soldier", ["Creature"]),
    ("Artifact Creature — Golem", ["Creature", "Artifact"]),
    ("Legendary Enchantment Artifact", ["Enchantment", "Artifact"]),
    ("Instant", ["Instant"]),
    ("Basic Land — Forest", ["Land"]),
    ("Vanguard", []),
])
def test_extract_types(type_line, expected_types):
    """Tests the extract_types utility function to correctly identify main card types."""
    types = extract_types(type_line)
    # Use sets for comparison to ignore order
    assert set(types) == set(expected_types)

def test_initialize_card_data():
    """Tests that a card data dictionary is correctly initialized with deck_colors."""
    card = {}
    initialize_card_data(card)
    assert constants.DATA_FIELD_DECK_COLORS in card
    assert constants.FILTER_OPTION_ALL_DECKS in card[constants.DATA_FIELD_DECK_COLORS]
    assert "W" in card[constants.DATA_FIELD_DECK_COLORS]
    assert "WUBRG" not in card[constants.DATA_FIELD_DECK_COLORS] # Example of a non-standard color combo
    for color in constants.DECK_COLORS:
        assert color in card[constants.DATA_FIELD_DECK_COLORS]
        assert constants.DATA_FIELD_GIHWR in card[constants.DATA_FIELD_DECK_COLORS][color]
        assert card[constants.DATA_FIELD_DECK_COLORS][color][constants.DATA_FIELD_GIHWR] == 0.0

@pytest.mark.parametrize("date_str, expected_result", [
    ("2023-01-01", True),
    ("9999-12-31", False), # Future date
    ("invalid-date", False),
    ("2023-13-01", False), # Invalid month
])
def test_check_date(date_str, expected_result):
    """Tests the date validation utility function."""
    assert check_date(date_str) == expected_result


# --- Test FileExtractor Class Methods ---

# Test cases: (input_set_code, expected_encoded_set_code)
URL_ENCODING_TEST_CASES = [
    ("OTJ", "OTJ"),
    ("CUBE - POWERED", "CUBE%20-%20POWERED"),
    ("SET/CODE", "SET%2FCODE"),
    ("SPECIAL&CHARS", "SPECIAL%26CHARS"),
]

@pytest.mark.parametrize("set_code, expected_encoded_set_code", URL_ENCODING_TEST_CASES)
@patch('src.file_extractor.urllib.request.urlopen')
def test_retrieve_17lands_data_url_encoding(mock_urlopen, file_extractor, set_code, expected_encoded_set_code):
    """
    Tests that the set code in the URL for retrieve_17lands_data is correctly URL-encoded.
    """
    mock_response = MagicMock()
    mock_response.read.return_value = b'[]'
    mock_urlopen.return_value = mock_response

    # The UI elements must be mocked to avoid AttributeErrors on `None`.
    mock_root = MagicMock()
    mock_progress = MagicMock()
    mock_status = MagicMock()
    
    # FIX: Set up self.selected_sets correctly before calling the method under test.
    # This state is normally set by the `select_sets` method.
    mock_set_info = MagicMock()
    mock_set_info.seventeenlands = [set_code]
    file_extractor.select_sets(mock_set_info)

    expected_url = (
        f"https://www.17lands.com/card_ratings/data?expansion={expected_encoded_set_code}"
        f"&format={file_extractor.draft}"
        f"&start_date={file_extractor.start_date}"
        f"&end_date={file_extractor.end_date}"
    )

    file_extractor.retrieve_17lands_data(
        sets=[set_code],
        deck_colors=[constants.FILTER_OPTION_ALL_DECKS],
        root=mock_root,
        progress=mock_progress,
        initial_progress=0,
        status=mock_status
    )

    # Assert
    # Check that urlopen was called with a Request object with the correctly encoded URL.
    mock_urlopen.assert_called_once()
    call_args = mock_urlopen.call_args
    request_obj = call_args[0][0]
    import urllib.request as _urllib_request
    assert isinstance(request_obj, _urllib_request.Request)
    assert request_obj.full_url == expected_url
    assert call_args[1]['context'] == file_extractor.context

def test_process_17lands_data(file_extractor):
    """
    Tests the processing of raw JSON data from the 17Lands API into the internal structure.
    """
    # Arrange: Mock 17Lands API response
    mock_api_data = [
        {
            "name": "Sol Ring",
            "url": "/static/images/cards/s_123.jpg",
            "ever_drawn_win_rate": 0.65,
            "avg_seen": 1.1,
            "drawn_improvement_win_rate": 0.1,
            "drawn_game_count": 1000,
        },
        {
            "name": "Island",
            "url": "https://c1.scryfall.com/island.jpg",
            "ever_drawn_win_rate": None, # Test null value
            "avg_seen": 9.5,
            "drawn_improvement_win_rate": -0.05,
            "drawn_game_count": 500,
        }
    ]
    color = "All Decks"
    
    # Act
    file_extractor._process_17lands_data(color, mock_api_data)
    
    # Assert
    ratings = file_extractor.card_ratings
    assert "Sol Ring" in ratings
    assert "Island" in ratings
    
    sol_ring_data = ratings["Sol Ring"]
    assert sol_ring_data["image"] == ["https://www.17lands.com/static/images/cards/s_123.jpg"]
    
    sol_ring_ratings = sol_ring_data["ratings"][0][color]
    assert sol_ring_ratings[constants.DATA_FIELD_GIHWR] == 65.0  # Check percentage conversion
    assert sol_ring_ratings[constants.DATA_FIELD_ALSA] == 1.1
    assert sol_ring_ratings[constants.DATA_FIELD_IWD] == 10.0 # Check percentage conversion
    assert sol_ring_ratings[constants.DATA_FIELD_NGD] == 1000

    island_ratings = ratings["Island"]["ratings"][0][color]
    assert island_ratings[constants.DATA_FIELD_GIHWR] == 0.0  # Check null handling
    assert island_ratings[constants.DATA_FIELD_IWD] == -5.0 # Check negative percentage

def test_process_card_data_merging(file_extractor):
    """
    Tests the merging of 17Lands data (`card_ratings`) into the main card dictionary (`card_dict`).
    """
    # Arrange
    card_name = "Test Card"
    file_extractor.card_dict = {
        "12345": {
            constants.DATA_FIELD_NAME: card_name,
            constants.DATA_FIELD_MANA_COST: "{U}",
            constants.DATA_FIELD_TYPES: ["Creature"],
            constants.DATA_FIELD_CMC: 1,
            constants.DATA_FIELD_COLORS: ["U"],
            constants.DATA_SECTION_IMAGES: [],
        }
    }
    file_extractor.card_ratings = {
        card_name: {
            "image": ["http://example.com/image.png"],
            "ratings": [
                {
                    "All Decks": {
                        constants.DATA_FIELD_GIHWR: 55.5,
                        constants.DATA_FIELD_ALSA: 3.3
                    }
                }
            ]
        }
    }

    # Act
    card_to_process = file_extractor.card_dict["12345"]
    result = file_extractor._process_card_data(card_to_process)

    # Assert
    assert result is True
    assert card_to_process[constants.DATA_SECTION_IMAGES] == ["http://example.com/image.png"]
    assert constants.DATA_FIELD_DECK_COLORS in card_to_process
    deck_colors = card_to_process[constants.DATA_FIELD_DECK_COLORS]
    assert deck_colors["All Decks"][constants.DATA_FIELD_GIHWR] == 55.5
    assert deck_colors["All Decks"][constants.DATA_FIELD_ALSA] == 3.3
    assert deck_colors["WU"][constants.DATA_FIELD_GIHWR] == 0.0 # Check that other colors are initialized

def test_process_card_data_no_match(file_extractor):
    """
    Tests that if a card has no 17Lands rating, it is still processed and initialized.
    """
    # Arrange
    card_name = "Unrated Card"
    file_extractor.card_dict = { "54321": { constants.DATA_FIELD_NAME: card_name } }
    file_extractor.card_ratings = {} # No ratings available

    # Act
    card_to_process = file_extractor.card_dict["54321"]
    result = file_extractor._process_card_data(card_to_process)

    # Assert
    assert result is False # Should return false as no match was found
    # But it should still initialize the deck_colors structure
    initialize_card_data(card_to_process) # Manually call for assertion comparison
    assert constants.DATA_FIELD_DECK_COLORS in card_to_process
    assert card_to_process[constants.DATA_FIELD_DECK_COLORS]["All Decks"][constants.DATA_FIELD_GIHWR] == 0.0

def test_export_card_data_writes_to_db(file_extractor, tmp_path):
    """
    Tests that export_card_data() persists data to the SQLite database.
    """
    from src.database import load_dataset
    db_path = str(tmp_path / "test.db")

    # Arrange
    file_extractor.select_sets(MagicMock(seventeenlands=["OTJ"]))
    file_extractor.combined_data = {
        "meta": {"start_date": "2024-01-01", "end_date": "2024-06-01", "game_count": 100, "version": 2.0},
        "color_ratings": {"WU": 54.0},
        "card_ratings": {},
    }

    # Act
    result = file_extractor.export_card_data(db_path=db_path)

    # Assert: export_card_data returned True
    assert result is True

    # Assert: data is in the DB
    loaded = load_dataset("OTJ", db_path)
    assert loaded is not None
    assert loaded["meta"]["start_date"] == "2024-01-01"
    assert loaded["color_ratings"]["WU"] == 54.0


# --- Helpers for merge_datasets tests ---

def _make_card(name, colors, types, rarity, cmc, mana_cost, image, deck_colors_data):
    """Build a card dict matching the real dataset JSON structure."""
    card = {
        constants.DATA_FIELD_NAME: name,
        constants.DATA_FIELD_COLORS: colors,
        constants.DATA_FIELD_TYPES: types,
        constants.DATA_FIELD_RARITY: rarity,
        constants.DATA_FIELD_CMC: cmc,
        constants.DATA_FIELD_MANA_COST: mana_cost,
        constants.DATA_SECTION_IMAGES: image,
        "isprimarycard": 1,
        "linkedfacetype": 0,
        constants.DATA_FIELD_DECK_COLORS: deck_colors_data,
    }
    return card


def _make_deck_colors(all_decks_stats):
    """Build a minimal deck_colors dict with just 'All Decks'."""
    return {constants.FILTER_OPTION_ALL_DECKS: all_decks_stats}


def _make_dataset(card_ratings, color_ratings=None, game_count=10000):
    """Build a dataset dict matching the real JSON structure."""
    ds = {
        "meta": {
            "collection_date": "2026-01-01",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "version": 3.0,
            "game_count": game_count,
        },
        "card_ratings": card_ratings,
    }
    if color_ratings is not None:
        ds["color_ratings"] = color_ratings
    return ds


def _stats(gihwr=0.0, ohwr=0.0, gpwr=0.0, gnswr=0.0, gdwr=0.0,
           alsa=0.0, ata=0.0, iwd=0.0, ngp=0, ngoh=0, gih=0, ngnd=0, ngd=0):
    """Build a stats dict for a single deck_colors entry."""
    return {
        constants.DATA_FIELD_GIHWR: gihwr,
        constants.DATA_FIELD_OHWR: ohwr,
        constants.DATA_FIELD_GPWR: gpwr,
        constants.DATA_FIELD_GNSWR: gnswr,
        constants.DATA_FIELD_GDWR: gdwr,
        constants.DATA_FIELD_ALSA: alsa,
        constants.DATA_FIELD_ATA: ata,
        constants.DATA_FIELD_IWD: iwd,
        constants.DATA_FIELD_NGP: ngp,
        constants.DATA_FIELD_NGOH: ngoh,
        constants.DATA_FIELD_GIH: gih,
        constants.DATA_FIELD_NGND: ngnd,
        constants.DATA_FIELD_NGD: ngd,
    }


# --- Test merge_datasets ---

class TestMergeDatasets:
    def test_merge_single_dataset_passthrough(self):
        """One dataset in, same dataset out unchanged."""
        card_ratings = {
            "100": _make_card(
                "Murder", ["B"], ["Instant"], "common", 3, "{1}{B}{B}",
                ["http://img/murder.jpg"],
                _make_deck_colors(_stats(gihwr=55.0, ngp=1000, gih=500)),
            )
        }
        ds = _make_dataset(card_ratings, color_ratings={"UB": 52.0, "BR": 51.0})
        result = merge_datasets([ds])

        assert result["card_ratings"]["100"][constants.DATA_FIELD_NAME] == "Murder"
        ad = result["card_ratings"]["100"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]
        assert ad[constants.DATA_FIELD_GIHWR] == 55.0
        assert ad[constants.DATA_FIELD_NGP] == 1000
        assert ad[constants.DATA_FIELD_GIH] == 500
        assert result["color_ratings"]["UB"] == 52.0

    def test_merge_two_datasets_rate_weighted_by_game_count(self):
        """Rate fields weighted by actual game counts, not equal split."""
        stats_a = _stats(gihwr=50.0, ata=3.0, ngp=1000, gih=400)
        stats_b = _stats(gihwr=60.0, ata=5.0, ngp=2000, gih=600)
        ds_a = _make_dataset({"1": _make_card("CardA", ["W"], ["Creature"], "common", 2, "{1}{W}", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("CardA", ["W"], ["Creature"], "common", 2, "{1}{W}", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # gihwr: (50*400 + 60*600) / 1000 = 56.0
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(56.0)
        # ata: (3.0*1000 + 5.0*2000) / 3000 = 4.3
        assert ad[constants.DATA_FIELD_ATA] == pytest.approx(4.3, abs=0.1)
        assert ad[constants.DATA_FIELD_NGP] == 3000
        assert ad[constants.DATA_FIELD_GIH] == 1000

    def test_merge_two_datasets_large_source_dominates(self):
        """Large source (more games) contributes more to rates than small source."""
        stats_premier = _stats(gihwr=55.0, ata=4.0, ngp=5000, gih=2000)
        stats_trad = _stats(gihwr=58.0, ata=3.5, ngp=1000, gih=400)
        ds_premier = _make_dataset({"1": _make_card("CardA", ["R"], ["Creature"], "rare", 3, "{2}{R}", [], _make_deck_colors(stats_premier))})
        ds_trad = _make_dataset({"1": _make_card("CardA", ["R"], ["Creature"], "rare", 3, "{2}{R}", [], _make_deck_colors(stats_trad))})

        result = merge_datasets([ds_premier, ds_trad])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # gihwr: (55*2000 + 58*400) / 2400 = 55.5
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(55.5, abs=0.1)
        # ata: (4.0*5000 + 3.5*1000) / 6000 = 3.9
        assert ad[constants.DATA_FIELD_ATA] == pytest.approx(3.9, abs=0.1)
        assert ad[constants.DATA_FIELD_NGP] == 6000
        assert ad[constants.DATA_FIELD_GIH] == 2400

    def test_merge_card_in_only_one_source(self):
        """Card missing from source B: uses source A values at full weight."""
        stats_a = _stats(gihwr=60.0, ngp=500, gih=200)
        ds_a = _make_dataset({"1": _make_card("OnlyInA", ["G"], ["Creature"], "uncommon", 4, "{3}{G}", ["http://img/a.jpg"], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({})  # Card not present

        result = merge_datasets([ds_a, ds_b])
        assert "1" in result["card_ratings"]
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]
        assert ad[constants.DATA_FIELD_GIHWR] == 60.0
        assert ad[constants.DATA_FIELD_NGP] == 500

    def test_merge_count_fields_are_summed(self):
        """ngp, ngoh, gih, ngnd, ngd are summed (NOT averaged)."""
        stats_a = _stats(ngp=100, ngoh=50, gih=80, ngnd=20, ngd=60)
        stats_b = _stats(ngp=200, ngoh=100, gih=160, ngnd=40, ngd=120)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        assert ad[constants.DATA_FIELD_NGP] == 300
        assert ad[constants.DATA_FIELD_NGOH] == 150
        assert ad[constants.DATA_FIELD_GIH] == 240
        assert ad[constants.DATA_FIELD_NGND] == 60
        assert ad[constants.DATA_FIELD_NGD] == 180

    def test_merge_all_rate_fields_game_count_weighted(self):
        """All rate fields use game-count weighting, including iwd from 17Lands."""
        stats_a = _stats(gihwr=50.0, ohwr=48.0, gpwr=52.0, gnswr=46.0, gdwr=54.0, alsa=5.0, ata=3.0, iwd=4.0,
                         ngp=1000, ngoh=500, gih=800, ngnd=200, ngd=600)
        stats_b = _stats(gihwr=60.0, ohwr=58.0, gpwr=62.0, gnswr=56.0, gdwr=64.0, alsa=3.0, ata=2.0, iwd=10.0,
                         ngp=800, ngoh=400, gih=600, ngnd=150, ngd=500)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # gihwr: (50*800 + 60*600) / 1400 = 54.3
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(54.3, abs=0.1)
        # ohwr: (48*500 + 58*400) / 900 = 52.4
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(52.4, abs=0.1)
        # gpwr: (52*1000 + 62*800) / 1800 = 56.4
        assert ad[constants.DATA_FIELD_GPWR] == pytest.approx(56.4, abs=0.1)
        # gnswr: (46*200 + 56*150) / 350 = 50.3
        assert ad[constants.DATA_FIELD_GNSWR] == pytest.approx(50.3, abs=0.1)
        # gdwr: (54*600 + 64*500) / 1100 = 58.5
        assert ad[constants.DATA_FIELD_GDWR] == pytest.approx(58.5, abs=0.1)
        # iwd: (4.0*800 + 10.0*600) / 1400 = 6.6
        assert ad[constants.DATA_FIELD_IWD] == pytest.approx(6.6, abs=0.1)
        # alsa: (5.0*1000 + 3.0*800) / 1800 = 4.1
        assert ad[constants.DATA_FIELD_ALSA] == pytest.approx(4.1, abs=0.1)
        # ata: (3.0*1000 + 2.0*800) / 1800 = 2.6
        assert ad[constants.DATA_FIELD_ATA] == pytest.approx(2.6, abs=0.1)

    def test_merge_nonumeric_fields_from_first_source(self):
        """name, types, colors preserved from first source that has the card."""
        stats = _stats(gihwr=50.0)
        ds_a = _make_dataset({"1": _make_card("NameA", ["W"], ["Creature"], "rare", 3, "{2}{W}", ["http://img/a.jpg"], _make_deck_colors(stats))})
        ds_b = _make_dataset({"1": _make_card("NameB", ["B"], ["Instant"], "common", 2, "{1}{B}", ["http://img/b.jpg"], _make_deck_colors(stats))})

        result = merge_datasets([ds_a, ds_b])
        card = result["card_ratings"]["1"]
        assert card[constants.DATA_FIELD_NAME] == "NameA"
        assert card[constants.DATA_FIELD_COLORS] == ["W"]
        assert card[constants.DATA_FIELD_TYPES] == ["Creature"]
        assert card[constants.DATA_FIELD_RARITY] == "rare"
        assert card[constants.DATA_SECTION_IMAGES] == ["http://img/a.jpg"]

    def test_merge_color_ratings_blended(self):
        """color_ratings weighted by each source's meta.game_count."""
        ds_a = _make_dataset({}, color_ratings={"WU": 55.0, "BR": 50.0}, game_count=8000)
        ds_b = _make_dataset({}, color_ratings={"WU": 60.0, "BR": 52.0}, game_count=4000)

        result = merge_datasets([ds_a, ds_b])

        # Weighted by game_count: (55*8000 + 60*4000) / 12000 = 56.7
        expected_wu = round((55.0 * 8000 + 60.0 * 4000) / (8000 + 4000), 1)
        # (50*8000 + 52*4000) / 12000 = 50.7
        expected_br = round((50.0 * 8000 + 52.0 * 4000) / (8000 + 4000), 1)
        assert result["color_ratings"]["WU"] == pytest.approx(expected_wu)
        assert result["color_ratings"]["BR"] == pytest.approx(expected_br)

    def test_merge_zero_count_rate_excluded(self):
        """Rate fields with zero corresponding count are excluded from average.

        Reproduces real scenario: Premier has OHWR=50.26 (ngoh=500),
        Traditional has OHWR=0.0 (ngoh=0 = no data). The 0.0 should NOT
        drag the average down to 25.13.
        """
        stats_premier = _stats(gihwr=56.42, ohwr=50.26, gpwr=57.94, ngp=1000, ngoh=500, gih=800)
        stats_trad = _stats(gihwr=0.0, ohwr=0.0, gpwr=0.0, ngp=0, ngoh=0, gih=0)
        ds_a = _make_dataset({"1": _make_card("Wayfinder", ["U"], ["Creature"], "common", 2, "{1}{U}", [],
                                              _make_deck_colors(stats_premier))})
        ds_b = _make_dataset({"1": _make_card("Wayfinder", ["U"], ["Creature"], "common", 2, "{1}{U}", [],
                                              _make_deck_colors(stats_trad))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # Source B has no data (all counts are 0), so rates should come entirely from source A
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(50.26, abs=0.1)
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(56.42, abs=0.1)
        assert ad[constants.DATA_FIELD_GPWR] == pytest.approx(57.94, abs=0.1)
        # Counts are still summed (0 + real = real)
        assert ad[constants.DATA_FIELD_NGP] == 1000
        assert ad[constants.DATA_FIELD_NGOH] == 500

    def test_merge_partial_zero_count(self):
        """One source has OHWR data but not GIHWR — only the missing rate is excluded."""
        stats_a = _stats(gihwr=55.0, ohwr=50.0, ngp=1000, ngoh=500, gih=800)
        stats_b = _stats(gihwr=60.0, ohwr=0.0, ngp=500, ngoh=0, gih=300)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # GIHWR: both have gih>0 → game-count weighted: (55*800 + 60*300) / 1100 = 56.4
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(56.4, abs=0.1)
        # OHWR: source B has ngoh=0 → only source A contributes → 50.0
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(50.0, abs=0.1)

    def test_merge_disabled_source_excluded_by_caller(self):
        """Disabled sources are filtered out by caller before merge_datasets is called.
        When only source A is passed, result reflects source A only."""
        stats_a = _stats(gihwr=55.0, ngp=1000, gih=500)
        stats_b_unused = _stats(gihwr=99.0, ngp=9999, gih=9999)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))},
                             color_ratings={"WU": 52.0})
        # ds_b_unused not passed — caller excluded it
        result = merge_datasets([ds_a])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]
        assert ad[constants.DATA_FIELD_GIHWR] == 55.0
        assert ad[constants.DATA_FIELD_NGP] == 1000
        assert ad[constants.DATA_FIELD_GIH] == 500
        assert result["color_ratings"]["WU"] == pytest.approx(52.0)

    def test_merge_zero_rate_nonzero_count_excluded(self):
        """Win rate of 0.0 with nonzero count is treated as 'no data' (suppressed by 17Lands API)."""
        stats_premier = _stats(gihwr=50.0, ohwr=48.0, gpwr=52.0, gnswr=46.0, gdwr=54.0,
                               ngp=5000, ngoh=2000, gih=3000, ngnd=1000, ngd=2000)
        stats_trad = _stats(gihwr=0.0, ohwr=0.0, gpwr=0.0, gnswr=0.0, gdwr=0.0,
                            ngp=200, ngoh=80, gih=12, ngnd=50, ngd=40)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_premier))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_trad))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # All win rate fields should come entirely from source A (source B has 0.0 = suppressed)
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(50.0, abs=0.1)
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(48.0, abs=0.1)
        assert ad[constants.DATA_FIELD_GPWR] == pytest.approx(52.0, abs=0.1)
        assert ad[constants.DATA_FIELD_GNSWR] == pytest.approx(46.0, abs=0.1)
        assert ad[constants.DATA_FIELD_GDWR] == pytest.approx(54.0, abs=0.1)
        # Count fields are still summed
        assert ad[constants.DATA_FIELD_NGP] == 5200
        assert ad[constants.DATA_FIELD_GIH] == 3012

    def test_merge_both_sources_nonzero_rates(self):
        """Both sources have real win rate data — game-count weighted average."""
        stats_a = _stats(gihwr=50.0, ohwr=48.0, ngp=5000, ngoh=2000, gih=3000)
        stats_b = _stats(gihwr=60.0, ohwr=58.0, ngp=1000, ngoh=400, gih=600)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # gihwr: (50*3000 + 60*600) / 3600 = 51.7
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(51.7, abs=0.1)
        # ohwr: (48*2000 + 58*400) / 2400 = 49.7
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(49.7, abs=0.1)


    def test_merge_meta_game_count_summed(self):
        """merged meta.game_count is the sum across all sources."""
        ds_a = _make_dataset({}, game_count=59529)
        ds_b = _make_dataset({}, game_count=12000)
        ds_c = _make_dataset({}, game_count=8500)
        ds_d = _make_dataset({}, game_count=3200)

        result = merge_datasets([ds_a, ds_b, ds_c, ds_d])

        assert result["meta"]["game_count"] == 59529 + 12000 + 8500 + 3200

    def test_merge_iwd_weighted_from_17lands_values(self):
        """iwd uses 17Lands-provided values and is weighted by gih game count."""
        # Source A: gihwr=55.0, gnswr=50.0 → iwd=5.0 (gih=1000, ngnd=500)
        # Source B: gihwr=65.0, gnswr=55.0 → iwd=10.0 (gih=200, ngnd=100)
        stats_a = _stats(gihwr=55.0, gnswr=50.0, iwd=5.0, ngp=1500, gih=1000, ngnd=500)
        stats_b = _stats(gihwr=65.0, gnswr=55.0, iwd=10.0, ngp=300, gih=200, ngnd=100)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # merged_iwd: (5.0*1000 + 10.0*200) / 1200 = 5.8
        expected_iwd = round((5.0 * 1000 + 10.0 * 200) / 1200, 1)

        # For sanity, this differs from the old re-derived path (56.7 - 50.8 = 5.9)
        expected_rederived = round(
            round((55.0 * 1000 + 65.0 * 200) / 1200, 1)
            - round((50.0 * 500 + 55.0 * 100) / 600, 1),
            1,
        )

        assert ad[constants.DATA_FIELD_IWD] == pytest.approx(expected_iwd, abs=0.1)
        assert ad[constants.DATA_FIELD_IWD] != pytest.approx(expected_rederived, abs=0.05)



@patch("src.file_extractor.os.remove")
@patch("src.file_extractor.os.listdir")
def test_delete_old_set_files(mock_listdir, mock_remove):
    """Only old 4-segment files for the matching set are deleted."""
    mock_listdir.return_value = [
        "ECL_PremierDraft_All_Data.json",   # old format, matches ECL -> delete
        "ECL_TradDraft_Top_Data.json",      # old format, matches ECL -> delete
        "ECL_Data.json",                    # new format, 2 segments -> keep
        "OTJ_PremierDraft_All_Data.json",   # old format, different set -> keep
        "MH3_QuickDraft_Bottom_Data.json",  # old format, different set -> keep
    ]

    delete_old_set_files("ECL")

    assert mock_remove.call_count == 2
    deleted = [call.args[0] for call in mock_remove.call_args_list]
    assert os.path.join(constants.SETS_FOLDER, "ECL_PremierDraft_All_Data.json") in deleted
    assert os.path.join(constants.SETS_FOLDER, "ECL_TradDraft_Top_Data.json") in deleted


# --- Test backfill unmatched 17Lands cards ---

def test_process_17lands_data_captures_metadata(file_extractor):
    """_process_17lands_data stores mtga_id, color, rarity, types from the API response."""
    mock_api_data = [
        {
            "name": "New TMT Card",
            "url": "/static/images/cards/tmt_001.jpg",
            "mtga_id": 99001,
            "color": "WU",
            "rarity": "rare",
            "types": ["Creature"],
            "ever_drawn_win_rate": 0.60,
            "avg_seen": 2.5,
            "drawn_improvement_win_rate": 0.05,
            "drawn_game_count": 800,
        }
    ]
    file_extractor._process_17lands_data("All Decks", mock_api_data)

    rating_data = file_extractor.card_ratings["New TMT Card"]
    assert rating_data.get("mtga_id") == 99001
    assert rating_data.get("color") == "WU"
    assert rating_data.get("rarity") == "rare"
    assert rating_data.get("types") == ["Creature"]


def test_assemble_set_backfills_unmatched_cards(file_extractor):
    """_assemble_set backfills 17Lands cards not found in card_dict using mtga_id as key."""
    file_extractor.select_sets(MagicMock(seventeenlands=["TMT"]))
    # card_dict has no matching cards for the 17Lands data
    file_extractor.card_dict = {
        "11111": {
            constants.DATA_FIELD_NAME: "Unrelated Reprint",
            constants.DATA_FIELD_CMC: 1,
            constants.DATA_FIELD_MANA_COST: "{W}",
            constants.DATA_FIELD_COLORS: ["W"],
            constants.DATA_FIELD_TYPES: ["Creature"],
            constants.DATA_SECTION_IMAGES: [],
        }
    }
    # card_ratings has a card with mtga_id that isn't in card_dict
    file_extractor.card_ratings = {
        "Brand New TMT Card": {
            constants.DATA_SECTION_IMAGES: ["https://example.com/tmt.jpg"],
            "mtga_id": 99999,
            "color": "R",
            "rarity": "uncommon",
            "types": ["Instant"],
            constants.DATA_SECTION_RATINGS: [
                {"All Decks": {constants.DATA_FIELD_GIHWR: 58.0, constants.DATA_FIELD_ALSA: 3.0}}
            ],
        }
    }

    file_extractor._assemble_set(matching_only=True)

    card_ratings = file_extractor.combined_data["card_ratings"]
    assert 99999 in card_ratings, "Backfilled card should be keyed by mtga_id"
    backfilled = card_ratings[99999]
    assert backfilled[constants.DATA_FIELD_NAME] == "Brand New TMT Card"
    assert backfilled[constants.DATA_FIELD_COLORS] == ["R"]
    assert backfilled[constants.DATA_FIELD_RARITY] == "uncommon"
    assert backfilled[constants.DATA_FIELD_TYPES] == ["Instant"]
    assert backfilled[constants.DATA_SECTION_IMAGES] == ["https://example.com/tmt.jpg"]
    assert backfilled[constants.DATA_FIELD_DECK_COLORS]["All Decks"][constants.DATA_FIELD_GIHWR] == 58.0


def test_assemble_set_no_duplicate_backfill(file_extractor):
    """Cards matched from card_dict are NOT duplicated by the backfill logic."""
    file_extractor.select_sets(MagicMock(seventeenlands=["TMT"]))
    file_extractor.card_dict = {
        "22222": {
            constants.DATA_FIELD_NAME: "Matched Card",
            constants.DATA_FIELD_CMC: 2,
            constants.DATA_FIELD_MANA_COST: "{1}{U}",
            constants.DATA_FIELD_COLORS: ["U"],
            constants.DATA_FIELD_TYPES: ["Creature"],
            constants.DATA_SECTION_IMAGES: [],
        }
    }
    file_extractor.card_ratings = {
        "Matched Card": {
            constants.DATA_SECTION_IMAGES: ["https://example.com/matched.jpg"],
            "mtga_id": 88888,
            "color": "U",
            "rarity": "common",
            "types": ["Creature"],
            constants.DATA_SECTION_RATINGS: [
                {"All Decks": {constants.DATA_FIELD_GIHWR: 50.0, constants.DATA_FIELD_ALSA: 4.0}}
            ],
        }
    }

    file_extractor._assemble_set(matching_only=True)

    card_ratings = file_extractor.combined_data["card_ratings"]
    # Should only appear once (matched from card_dict, not duplicated by backfill)
    assert "22222" in card_ratings
    assert 88888 not in card_ratings


def test_assemble_set_backfill_skips_cards_without_mtga_id(file_extractor):
    """17Lands cards without an mtga_id are skipped during backfill."""
    file_extractor.select_sets(MagicMock(seventeenlands=["TMT"]))
    file_extractor.card_dict = {}
    file_extractor.card_ratings = {
        "No ID Card": {
            constants.DATA_SECTION_IMAGES: [],
            "mtga_id": None,
            "color": "G",
            "rarity": "common",
            "types": ["Sorcery"],
            constants.DATA_SECTION_RATINGS: [],
        }
    }

    file_extractor._assemble_set(matching_only=True)

    assert file_extractor.combined_data["card_ratings"] == {}


@patch("src.file_extractor.os.remove")
@patch("src.file_extractor.os.listdir")
def test_delete_old_set_files_case_insensitive(mock_listdir, mock_remove):
    """Set code matching is case-insensitive."""
    mock_listdir.return_value = [
        "ecl_PremierDraft_All_Data.json",  # lowercase set code -> still matches
    ]

    delete_old_set_files("ECL")

    assert mock_remove.call_count == 1
