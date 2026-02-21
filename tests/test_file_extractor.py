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

@patch('src.file_extractor.check_file_integrity', return_value=(Result.VALID, {}))
@patch('builtins.open', new_callable=mock_open)
@patch('src.file_extractor.json.dump')
def test_export_card_data(mock_json_dump, mock_file_open, mock_check_integrity, file_extractor):
    """
    Tests that the export_card_data function attempts to write the correct data to the correct file.
    """
    # Arrange
    file_extractor.select_sets(MagicMock(seventeenlands=["OTJ"]))
    file_extractor.combined_data = {"meta": {}, "card_ratings": {"1": "a"}}
    expected_filename = f"OTJ_{constants.SET_FILE_SUFFIX}"
    expected_filepath = constants.SETS_FOLDER + os.path.sep + expected_filename

    # Act
    result = file_extractor.export_card_data()

    # Assert
    assert result is True
    mock_file_open.assert_called_once_with(expected_filepath, 'w', encoding="utf-8", errors="replace")
    mock_json_dump.assert_called_once_with(file_extractor.combined_data, mock_file_open())
    mock_check_integrity.assert_called_once_with(expected_filepath)


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
        result = merge_datasets([ds], [1.0])

        assert result["card_ratings"]["100"][constants.DATA_FIELD_NAME] == "Murder"
        ad = result["card_ratings"]["100"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]
        assert ad[constants.DATA_FIELD_GIHWR] == 55.0
        assert ad[constants.DATA_FIELD_NGP] == 1000
        assert ad[constants.DATA_FIELD_GIH] == 500
        assert result["color_ratings"]["UB"] == 52.0

    def test_merge_two_datasets_equal_weights(self):
        """Two sources weight=1.0 each: rates are averaged, counts are summed."""
        stats_a = _stats(gihwr=50.0, ata=3.0, ngp=1000, gih=400)
        stats_b = _stats(gihwr=60.0, ata=5.0, ngp=2000, gih=600)
        ds_a = _make_dataset({"1": _make_card("CardA", ["W"], ["Creature"], "common", 2, "{1}{W}", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("CardA", ["W"], ["Creature"], "common", 2, "{1}{W}", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(55.0)
        assert ad[constants.DATA_FIELD_ATA] == pytest.approx(4.0)
        assert ad[constants.DATA_FIELD_NGP] == 3000
        assert ad[constants.DATA_FIELD_GIH] == 1000

    def test_merge_two_datasets_unequal_weights(self):
        """Premier weight=0.7, Traditional weight=0.3: rates are weighted-averaged."""
        stats_premier = _stats(gihwr=55.0, ata=4.0, ngp=5000, gih=2000)
        stats_trad = _stats(gihwr=58.0, ata=3.5, ngp=1000, gih=400)
        ds_premier = _make_dataset({"1": _make_card("CardA", ["R"], ["Creature"], "rare", 3, "{2}{R}", [], _make_deck_colors(stats_premier))})
        ds_trad = _make_dataset({"1": _make_card("CardA", ["R"], ["Creature"], "rare", 3, "{2}{R}", [], _make_deck_colors(stats_trad))})

        result = merge_datasets([ds_premier, ds_trad], [0.7, 0.3])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        expected_gihwr = round((55.0 * 0.7 + 58.0 * 0.3) / (0.7 + 0.3), 1)
        expected_ata = round((4.0 * 0.7 + 3.5 * 0.3) / (0.7 + 0.3), 1)
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(expected_gihwr)
        assert ad[constants.DATA_FIELD_ATA] == pytest.approx(expected_ata)
        # Counts are always summed regardless of weight
        assert ad[constants.DATA_FIELD_NGP] == 6000
        assert ad[constants.DATA_FIELD_GIH] == 2400

    def test_merge_card_in_only_one_source(self):
        """Card missing from source B: uses source A values at full weight."""
        stats_a = _stats(gihwr=60.0, ngp=500, gih=200)
        ds_a = _make_dataset({"1": _make_card("OnlyInA", ["G"], ["Creature"], "uncommon", 4, "{3}{G}", ["http://img/a.jpg"], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({})  # Card not present

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
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

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        assert ad[constants.DATA_FIELD_NGP] == 300
        assert ad[constants.DATA_FIELD_NGOH] == 150
        assert ad[constants.DATA_FIELD_GIH] == 240
        assert ad[constants.DATA_FIELD_NGND] == 60
        assert ad[constants.DATA_FIELD_NGD] == 180

    def test_merge_rate_fields_are_weighted_averaged(self):
        """gihwr, ohwr, gpwr, gnswr, gdwr are weighted-averaged."""
        stats_a = _stats(gihwr=50.0, ohwr=48.0, gpwr=52.0, gnswr=46.0, gdwr=54.0, alsa=5.0, ata=3.0, iwd=2.0,
                         ngp=1000, ngoh=500, gih=800, ngnd=200, ngd=600)
        stats_b = _stats(gihwr=60.0, ohwr=58.0, gpwr=62.0, gnswr=56.0, gdwr=64.0, alsa=3.0, ata=2.0, iwd=4.0,
                         ngp=800, ngoh=400, gih=600, ngnd=150, ngd=500)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b], [0.6, 0.4])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        for field, va, vb in [
            (constants.DATA_FIELD_GIHWR, 50.0, 60.0),
            (constants.DATA_FIELD_OHWR, 48.0, 58.0),
            (constants.DATA_FIELD_GPWR, 52.0, 62.0),
            (constants.DATA_FIELD_GNSWR, 46.0, 56.0),
            (constants.DATA_FIELD_GDWR, 54.0, 64.0),
            (constants.DATA_FIELD_ALSA, 5.0, 3.0),
            (constants.DATA_FIELD_ATA, 3.0, 2.0),
            (constants.DATA_FIELD_IWD, 2.0, 4.0),
        ]:
            expected = round((va * 0.6 + vb * 0.4) / (0.6 + 0.4), 1)
            assert ad[field] == pytest.approx(expected), f"Field {field} mismatch"

    def test_merge_nonumeric_fields_from_first_source(self):
        """name, types, colors preserved from first source that has the card."""
        stats = _stats(gihwr=50.0)
        ds_a = _make_dataset({"1": _make_card("NameA", ["W"], ["Creature"], "rare", 3, "{2}{W}", ["http://img/a.jpg"], _make_deck_colors(stats))})
        ds_b = _make_dataset({"1": _make_card("NameB", ["B"], ["Instant"], "common", 2, "{1}{B}", ["http://img/b.jpg"], _make_deck_colors(stats))})

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
        card = result["card_ratings"]["1"]
        assert card[constants.DATA_FIELD_NAME] == "NameA"
        assert card[constants.DATA_FIELD_COLORS] == ["W"]
        assert card[constants.DATA_FIELD_TYPES] == ["Creature"]
        assert card[constants.DATA_FIELD_RARITY] == "rare"
        assert card[constants.DATA_SECTION_IMAGES] == ["http://img/a.jpg"]

    def test_merge_color_ratings_blended(self):
        """color_ratings section is also weighted-averaged."""
        ds_a = _make_dataset({}, color_ratings={"WU": 55.0, "BR": 50.0}, game_count=8000)
        ds_b = _make_dataset({}, color_ratings={"WU": 60.0, "BR": 52.0}, game_count=4000)

        result = merge_datasets([ds_a, ds_b], [0.7, 0.3])
        expected_wu = round((55.0 * 0.7 + 60.0 * 0.3) / (0.7 + 0.3), 1)
        expected_br = round((50.0 * 0.7 + 52.0 * 0.3) / (0.7 + 0.3), 1)
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

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
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

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # GIHWR: both have gih>0, so average normally
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(57.5, abs=0.1)
        # OHWR: source B has ngoh=0, so only source A contributes
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(50.0, abs=0.1)

    def test_merge_zero_weight_source_excluded(self):
        """A source with weight=0.0 contributes nothing."""
        stats_a = _stats(gihwr=55.0, ngp=1000, gih=500)
        stats_b = _stats(gihwr=99.0, ngp=9999, gih=9999)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))},
                             color_ratings={"WU": 52.0})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))},
                             color_ratings={"WU": 99.0})

        result = merge_datasets([ds_a, ds_b], [1.0, 0.0])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]
        assert ad[constants.DATA_FIELD_GIHWR] == 55.0
        # Count fields from zero-weight source should not be included
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

        result = merge_datasets([ds_a, ds_b], [1.0, 1.0])
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
        """Both sources have real win rate data — normal weighted average."""
        stats_a = _stats(gihwr=50.0, ohwr=48.0, ngp=5000, ngoh=2000, gih=3000)
        stats_b = _stats(gihwr=60.0, ohwr=58.0, ngp=1000, ngoh=400, gih=600)
        ds_a = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_a))})
        ds_b = _make_dataset({"1": _make_card("C", [], [], "common", 1, "", [], _make_deck_colors(stats_b))})

        result = merge_datasets([ds_a, ds_b], [0.7, 0.3])
        ad = result["card_ratings"]["1"][constants.DATA_FIELD_DECK_COLORS][constants.FILTER_OPTION_ALL_DECKS]

        # Both sources contribute: (50.0 * 0.7 + 60.0 * 0.3) / (0.7 + 0.3) = 53.0
        assert ad[constants.DATA_FIELD_GIHWR] == pytest.approx(53.0, abs=0.1)
        # (48.0 * 0.7 + 58.0 * 0.3) / (0.7 + 0.3) = 51.0
        assert ad[constants.DATA_FIELD_OHWR] == pytest.approx(51.0, abs=0.1)


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


@patch("src.file_extractor.os.remove")
@patch("src.file_extractor.os.listdir")
def test_delete_old_set_files_case_insensitive(mock_listdir, mock_remove):
    """Set code matching is case-insensitive."""
    mock_listdir.return_value = [
        "ecl_PremierDraft_All_Data.json",  # lowercase set code -> still matches
    ]

    delete_old_set_files("ECL")

    assert mock_remove.call_count == 1
