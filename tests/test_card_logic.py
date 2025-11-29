import pytest
import os
import json
from src import constants
from src.set_metrics import SetMetrics
from src.configuration import Configuration, Settings
from src.card_logic import CardResult, calculate_weighted_average
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


# Weighted Average Tests
@pytest.fixture
def sample_card():
    """Sample card with deck_colors data for testing weighted average"""
    return {
        constants.DATA_FIELD_DECK_COLORS: {
            "UB": {constants.DATA_FIELD_GIHWR: 55.0, constants.DATA_FIELD_GIH: 1000},
            "WU": {constants.DATA_FIELD_GIHWR: 52.0, constants.DATA_FIELD_GIH: 500},
            "BG": {constants.DATA_FIELD_GIHWR: 58.0, constants.DATA_FIELD_GIH: 1500}
        }
    }


def test_weighted_average_two_colors(sample_card):
    """Test weighted average with two colors
    UB: 55% * 1000 = 55000, WU: 52% * 500 = 26000
    Total: 81000 / 1500 = 54.0%
    """
    result = calculate_weighted_average(
        sample_card, ["UB", "WU"], constants.DATA_FIELD_GIHWR
    )
    assert result == 54.0


def test_weighted_average_three_colors(sample_card):
    """Test weighted average with three colors
    UB: 55000, WU: 26000, BG: 87000
    Total: 168000 / 3000 = 56.0%
    """
    result = calculate_weighted_average(
        sample_card, ["UB", "WU", "BG"], constants.DATA_FIELD_GIHWR
    )
    assert result == 56.0


def test_weighted_average_missing_color(sample_card):
    """Test weighted average when one color doesn't exist in the card data
    Only UB exists in sample, WR does not
    """
    result = calculate_weighted_average(
        sample_card, ["UB", "WR"], constants.DATA_FIELD_GIHWR
    )
    assert result == 55.0  # Falls back to only valid color


def test_weighted_average_empty_colors(sample_card):
    """Test weighted average with empty color list"""
    result = calculate_weighted_average(sample_card, [], constants.DATA_FIELD_GIHWR)
    assert result == 0.0


def test_weighted_average_no_deck_colors():
    """Test weighted average when card has no deck_colors field"""
    card = {"name": "Test Card"}
    result = calculate_weighted_average(card, ["UB"], constants.DATA_FIELD_GIHWR)
    assert result == 0.0


def test_weighted_average_invalid_field(sample_card):
    """Test weighted average with an invalid win rate field"""
    result = calculate_weighted_average(sample_card, ["UB"], "invalid_field")
    assert result == 0.0


def test_weighted_average_zero_games(sample_card):
    """Test weighted average when all colors have zero game counts"""
    card = {
        constants.DATA_FIELD_DECK_COLORS: {
            "UB": {constants.DATA_FIELD_GIHWR: 55.0, constants.DATA_FIELD_GIH: 0},
            "WU": {constants.DATA_FIELD_GIHWR: 52.0, constants.DATA_FIELD_GIH: 0}
        }
    }
    result = calculate_weighted_average(card, ["UB", "WU"], constants.DATA_FIELD_GIHWR)
    assert result == 0.0