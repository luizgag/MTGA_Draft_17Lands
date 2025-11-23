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