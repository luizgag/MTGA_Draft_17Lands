import pytest
import os
import json
from src import constants
from src.set_metrics import SetMetrics
from src.configuration import Configuration, Settings
from src.card_logic import CardResult, extract_colored_pips
from src.dataset import Dataset
from src.tier_list import TierList, Meta, Rating

# 17Lands OTJ data from 2024-4-16 to 2024-5-3
OTJ_PREMIER_SNAPSHOT = os.path.join(os.getcwd(), "tests", "data","OTJ_PremierDraft_Data_2024_5_3.json")

TEST_TIER_LIST = {
    "TIER0": TierList(
        meta=Meta(
            collection_date="",
            label="",
            set="",
            version=3
        ),
        ratings={
            "Push // Pull": Rating(rating="C+", comment=""),
            "Etali, Primal Conqueror": Rating(rating="A+", comment=""),
            "Virtue of Persistence": Rating(rating="A+", comment=""),
            "Consign // Oblivion": Rating(rating="C+", comment=""),
            "The Mightstone and Weakstone": Rating(rating="B-", comment=""),
            "Invasion of Gobakhan": Rating(rating="B+", comment=""),
        }
    )
}

TIER_TESTS = [
    ([{"name": "Push // Pull"}], "C+"),
    ([{"name": "Consign /// Oblivion"}], "C+"),
    ([{"name": "Etali, Primal Conqueror"}], "A+"),
    ([{"name": "Invasion of Gobakhan"}], "B+"),
    ([{"name": "The Mightstone and Weakstone"}], "B-"),
    ([{"name": "Virtue of Persistence"}], "A+"),
    ([{"name": "Fake Card"}], "NA"),
]

OTJ_GRADE_TESTS = [
    ("Colossal Rattlewurm", "All Decks", constants.DATA_FIELD_GIHWR, constants.LETTER_GRADE_A_MINUS),
    ("Colossal Rattlewurm", "All Decks", constants.DATA_FIELD_OHWR, constants.LETTER_GRADE_A_MINUS),
    ("Colossal Rattlewurm", "All Decks", constants.DATA_FIELD_GPWR, constants.LETTER_GRADE_B_PLUS),
    ("Colossal Rattlewurm", "WG", constants.DATA_FIELD_GIHWR, constants.LETTER_GRADE_A_MINUS),
    ("Colossal Rattlewurm", "WG", constants.DATA_FIELD_OHWR, constants.LETTER_GRADE_B_PLUS),
    ("Colossal Rattlewurm", "WG", constants.DATA_FIELD_GPWR, constants.LETTER_GRADE_B_PLUS),
]

@pytest.fixture(name="card_result", scope="module")
def fixture_card_result():
    return CardResult(SetMetrics(None), TEST_TIER_LIST, Configuration(), 1)
    
@pytest.fixture(name="otj_premier", scope="module")
def fixture_otj_premier():
    dataset = Dataset()
    dataset.open_file(OTJ_PREMIER_SNAPSHOT)
    set_metrics = SetMetrics(dataset, 2)
        
    return set_metrics, dataset
    
#The card data is pulled from the JSON set files downloaded from 17Lands, excluding the fake card
@pytest.mark.parametrize("card_list, expected_tier",TIER_TESTS)
def test_tier_results(card_result, card_list, expected_tier):
    # Go through a list of non-standard cards and confirm that the CardResults class is producing the expected result
    result_list = card_result.return_results(card_list, ["All Decks"], ["TIER0"])
    
    assert result_list[0]["results"][0] == expected_tier
    
@pytest.mark.parametrize("card_name, colors, field, expected_grade", OTJ_GRADE_TESTS)
def test_otj_grades(otj_premier, card_name, colors, field, expected_grade):
    metrics, dataset = otj_premier
    data_list = dataset.get_data_by_name([card_name])
    assert data_list

    config = Configuration(settings=Settings(result_format=constants.RESULT_FORMAT_GRADE))
    results = CardResult(metrics, None, config, 2)
    card_data = data_list[0]
    result_list = results.return_results([card_data], [colors],  [field])

    assert result_list[0]["results"][0] == expected_grade


# Test cases for extract_colored_pips function
EXTRACT_PIPS_TESTS = [
    # Regular mana costs
    ("{W}", {"W": 1}),
    ("{W}{W}", {"W": 2}),
    ("{1}{W}", {"W": 1}),
    ("{2}{W}{W}", {"W": 2}),
    ("{1}{B}{B}", {"B": 2}),
    ("{U}{B}", {"U": 1, "B": 1}),
    ("{3}{U}{R}", {"U": 1, "R": 1}),
    ("{4}{G}{W}", {"G": 1, "W": 1}),
    # Colorless mana costs
    ("{2}", {}),
    ("{X}", {}),
    ("{0}", {}),
    # Hybrid mana - two colors
    ("{W/U}", {"W": 0.5, "U": 0.5}),
    ("{B/R}", {"B": 0.5, "R": 0.5}),
    ("{G/W}", {"G": 0.5, "W": 0.5}),
    # Hybrid mana - generic/color (2/C)
    ("{2/W}", {"W": 0.5}),
    ("{2/U}", {"U": 0.5}),
    ("{2/B}", {"B": 0.5}),
    ("{2/R}", {"R": 0.5}),
    ("{2/G}", {"G": 0.5}),
    # Phyrexian hybrid mana
    ("{G/P}", {"G": 0.5}),
    ("{W/P}", {"W": 0.5}),
    ("{U/P}", {"U": 0.5}),
    ("{B/P}", {"B": 0.5}),
    ("{R/P}", {"R": 0.5}),
    # Mixed mana costs
    ("{W/U}{W}", {"W": 1.5, "U": 0.5}),
    ("{1}{W/U}{B}", {"W": 0.5, "U": 0.5, "B": 1}),
    ("{2/W}{2/U}", {"W": 0.5, "U": 0.5}),
    ("{G/P}{G}{G}", {"G": 2.5}),
    ("{W/U}{U/B}{B/R}", {"W": 0.5, "U": 1.0, "B": 1.0, "R": 0.5}),
    # Empty/null cases
    ("", {}),
    (None, {}),
    # Lowercase handling
    ("{w}", {"W": 1}),
    ("{w/u}", {"W": 0.5, "U": 0.5}),
]


@pytest.mark.parametrize("mana_cost, expected_pips", EXTRACT_PIPS_TESTS)
def test_extract_colored_pips(mana_cost, expected_pips):
    result = extract_colored_pips(mana_cost)
    assert result == expected_pips


# Test cases for Best Performance filters
def test_best_gihwr_basic():
    """Test basic GIHWR best performance selection"""
    # Create a mock card with different GIHWR values for different colors
    card = {
        "name": "Test Card",
        "deck_colors": {
            "All Decks": {
                "gihwr": 50.0,
                "gih": 100
            },
            "W": {
                "gihwr": 55.0,
                "gih": 50
            },
            "U": {
                "gihwr": 60.0,  # Highest
                "gih": 50
            },
            "B": {
                "gihwr": 52.0,
                "gih": 50
            }
        }
    }

    config = Configuration(settings=Settings(min_game_threshold=0))
    card_result = CardResult(SetMetrics(None), None, config, 1)

    # Test that Best GIHWR column shows "U: 60.0" (the best color with value)
    result_list = card_result.return_results([card], ["All Decks"], [constants.DATA_FIELD_BEST_GIHWR])
    assert result_list[0]["results"][0] == "U: 60.0"


def test_best_gpwr_basic():
    """Test basic GPWR best performance selection"""
    # Create a mock card with different GPWR values for different colors
    card = {
        "name": "Test Card",
        "deck_colors": {
            "All Decks": {
                "gpwr": 50.0,
                "ngp": 100
            },
            "W": {
                "gpwr": 55.0,
                "ngp": 50
            },
            "R": {
                "gpwr": 58.0,  # Highest
                "ngp": 50
            },
            "G": {
                "gpwr": 52.0,
                "ngp": 50
            }
        }
    }

    config = Configuration(settings=Settings(min_game_threshold=0))
    card_result = CardResult(SetMetrics(None), None, config, 1)

    # Test that Best GPWR column shows "R: 58.0" (the best color with value)
    result_list = card_result.return_results([card], ["All Decks"], [constants.DATA_FIELD_BEST_GPWR])
    assert result_list[0]["results"][0] == "R: 58.0"


def test_best_gihwr_with_threshold():
    """Test GIHWR best performance with minimum game threshold"""
    # Create a mock card where the highest WR color has low games
    card = {
        "name": "Test Card",
        "deck_colors": {
            "All Decks": {
                "gihwr": 50.0,
                "gih": 1000
            },
            "W": {
                "gihwr": 70.0,  # Highest WR but only 30 games
                "gih": 30
            },
            "U": {
                "gihwr": 55.0,  # Lower WR but 100 games
                "gih": 100
            }
        }
    }

    # With threshold of 50, W should be ignored and U selected
    config = Configuration(settings=Settings(min_game_threshold=50))
    card_result = CardResult(SetMetrics(None), None, config, 1)

    result_list = card_result.return_results([card], ["All Decks"], [constants.DATA_FIELD_BEST_GIHWR])
    assert result_list[0]["results"][0] == "U: 55.0"


def test_best_gihwr_fallback_to_all_decks():
    """Test fallback to All Decks when no color meets threshold"""
    # Create a mock card where all colors have low game counts
    card = {
        "name": "Test Card",
        "deck_colors": {
            "All Decks": {
                "gihwr": 50.0,
                "gih": 1000
            },
            "W": {
                "gihwr": 60.0,
                "gih": 30
            },
            "U": {
                "gihwr": 55.0,
                "gih": 40
            }
        }
    }

    # With threshold of 100, both colors should be ignored, falling back to "All Decks"
    config = Configuration(settings=Settings(min_game_threshold=100))
    card_result = CardResult(SetMetrics(None), None, config, 1)

    result_list = card_result.return_results([card], ["All Decks"], [constants.DATA_FIELD_BEST_GIHWR])
    assert result_list[0]["results"][0] == "All Decks: 50.0"


def test_best_gpwr_fallback_to_all_decks():
    """Test fallback to All Decks for GPWR when no color meets threshold"""
    # Create a mock card where all colors have low game counts
    card = {
        "name": "Test Card",
        "deck_colors": {
            "All Decks": {
                "gpwr": 50.0,
                "ngp": 1000
            },
            "R": {
                "gpwr": 60.0,
                "ngp": 30
            },
            "G": {
                "gpwr": 55.0,
                "ngp": 40
            }
        }
    }

    # With threshold of 100, both colors should be ignored, falling back to "All Decks"
    config = Configuration(settings=Settings(min_game_threshold=100))
    card_result = CardResult(SetMetrics(None), None, config, 1)

    result_list = card_result.return_results([card], ["All Decks"], [constants.DATA_FIELD_BEST_GPWR])
    assert result_list[0]["results"][0] == "All Decks: 50.0"


def test_best_gihwr_filter_usage():
    """Test using Best GIHWR as a deck filter and retrieving ALSA for that color"""
    # Create a mock card with different GIHWR and ALSA values for different colors
    card = {
        "name": "Test Card",
        "deck_colors": {
            "All Decks": {
                "gihwr": 50.0,
                "gih": 100,
                "alsa": 5.0
            },
            "W": {
                "gihwr": 55.0,
                "gih": 50,
                "alsa": 6.0
            },
            "U": {
                "gihwr": 60.0,  # Highest
                "gih": 50,
                "alsa": 7.0  # Should return this ALSA
            }
        }
    }

    config = Configuration(settings=Settings(min_game_threshold=0))
    card_result = CardResult(SetMetrics(None), None, config, 1)

    # When using Best GIHWR filter, should get ALSA from U (the best GIHWR color)
    result_list = card_result.return_results([card], [constants.FILTER_OPTION_BEST_GIHWR], [constants.DATA_FIELD_ALSA])
    assert result_list[0]["results"][0] == 7.0