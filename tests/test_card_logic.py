import pytest
import os
import json
from src import constants
from src.set_metrics import SetMetrics
from src.configuration import Configuration, Settings
from src.card_logic import CardResult
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
    
    config = Configuration(settings=Settings(result_format=constants.RESULT_FORMAT_GRADE,
                                              deck_filter=constants.FILTER_OPTION_ALL_DECKS))
    results = CardResult(metrics, None, config, 2)
    card_data = data_list[0]
    result_list = results.return_results([card_data], [colors],  [field])

    assert result_list[0]["results"][0] == expected_grade

FORCED_RATING_TESTS = [
    # Filtered deck + GIHWR/GPWR/OHWR/GDWR with Percentage => forced to Rating
    ("Colossal Rattlewurm", "WG", constants.RESULT_FORMAT_WIN_RATE, constants.DATA_FIELD_GIHWR, True),
    ("Colossal Rattlewurm", "WG", constants.RESULT_FORMAT_WIN_RATE, constants.DATA_FIELD_GPWR, True),
    ("Colossal Rattlewurm", "WG", constants.RESULT_FORMAT_WIN_RATE, constants.DATA_FIELD_OHWR, True),
    ("Colossal Rattlewurm", "WG", constants.RESULT_FORMAT_WIN_RATE, constants.DATA_FIELD_GDWR, True),
    # Filtered deck + GIHWR with Grade => forced to Rating
    ("Colossal Rattlewurm", "WG", constants.RESULT_FORMAT_GRADE, constants.DATA_FIELD_GIHWR, True),
    # Filtered deck + GNSWR => NOT forced (stays Percentage)
    ("Colossal Rattlewurm", "WG", constants.RESULT_FORMAT_WIN_RATE, constants.DATA_FIELD_GNSWR, False),
    # All Decks + GIHWR => NOT forced (respects user format)
    ("Colossal Rattlewurm", constants.FILTER_OPTION_ALL_DECKS, constants.RESULT_FORMAT_WIN_RATE, constants.DATA_FIELD_GIHWR, False),
    ("Colossal Rattlewurm", constants.FILTER_OPTION_ALL_DECKS, constants.RESULT_FORMAT_GRADE, constants.DATA_FIELD_GIHWR, False),
]

@pytest.mark.parametrize("card_name, deck_filter, result_format, field, should_be_rating", FORCED_RATING_TESTS)
def test_forced_rating_on_deck_filter(otj_premier, card_name, deck_filter, result_format, field, should_be_rating):
    metrics, dataset = otj_premier
    data_list = dataset.get_data_by_name([card_name])
    assert data_list

    config = Configuration(settings=Settings(result_format=result_format,
                                              deck_filter=deck_filter))
    results = CardResult(metrics, None, config, 2)
    card_data = data_list[0]

    color_filter = deck_filter
    result_list = results.return_results([card_data], [color_filter], [field])
    result_value = result_list[0]["results"][0]

    if should_be_rating:
        assert isinstance(result_value, float), f"Expected Rating (float), got {type(result_value).__name__}: {result_value}"
        assert 0.1 <= result_value <= 5.0
    else:
        if result_format == constants.RESULT_FORMAT_WIN_RATE:
            assert isinstance(result_value, float)
        elif result_format == constants.RESULT_FORMAT_GRADE:
            assert isinstance(result_value, str)