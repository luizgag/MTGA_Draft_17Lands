import unittest
from unittest.mock import MagicMock
from src import constants
from src.card_logic import CardResult

class TestBestPerformance(unittest.TestCase):

    def setUp(self):
        self.mock_metrics = MagicMock()
        self.mock_tier_data = MagicMock()
        self.mock_configuration = MagicMock()
        self.mock_configuration.settings.result_format = constants.RESULT_FORMAT_WIN_RATE
        self.mock_configuration.settings.color_identity_enabled = False
        
        self.card_result = CardResult(self.mock_metrics, self.mock_tier_data, self.mock_configuration, 1)

    def test_best_gihwr_percentage(self):
        card = {
            constants.DATA_FIELD_DECK_COLORS: {
                "WU": {constants.DATA_FIELD_GIHWR: 55.0, constants.DATA_FIELD_GIH: 100},
                "UB": {constants.DATA_FIELD_GIHWR: 60.0, constants.DATA_FIELD_GIH: 100},
                "RW": {constants.DATA_FIELD_GIHWR: 50.0, constants.DATA_FIELD_GIH: 100}
            }
        }
        
        # Test Best GIHWR
        result = self.card_result._CardResult__process_best_performance(card, constants.DATA_FIELD_GIHWR)
        self.assertEqual(result, "UB (60.0%)")

    def test_best_gpwr_percentage(self):
        card = {
            constants.DATA_FIELD_DECK_COLORS: {
                "WU": {constants.DATA_FIELD_GPWR: 55.0, constants.DATA_FIELD_NGP: 100},
                "UB": {constants.DATA_FIELD_GPWR: 60.0, constants.DATA_FIELD_NGP: 100},
                "RW": {constants.DATA_FIELD_GPWR: 50.0, constants.DATA_FIELD_NGP: 100}
            }
        }
        
        # Test Best GPWR
        result = self.card_result._CardResult__process_best_performance(card, constants.DATA_FIELD_GPWR)
        self.assertEqual(result, "UB (60.0%)")

    def test_best_gihwr_grade(self):
        self.mock_configuration.settings.result_format = constants.RESULT_FORMAT_GRADE
        # Mock metrics to return mean=50, std=10 for grade calculation
        self.mock_metrics.get_metrics.return_value = (50.0, 10.0)
        
        card = {
            constants.DATA_FIELD_DECK_COLORS: {
                "WU": {constants.DATA_FIELD_GIHWR: 55.0, constants.DATA_FIELD_GIH: 100}, # +0.5 std -> B
                "UB": {constants.DATA_FIELD_GIHWR: 70.0, constants.DATA_FIELD_GIH: 100}, # +2.0 std -> A+
                "RW": {constants.DATA_FIELD_GIHWR: 50.0, constants.DATA_FIELD_GIH: 100}  # +0.0 std -> C+
            }
        }
        
        # Test Best GIHWR with Grade
        result = self.card_result._CardResult__process_best_performance(card, constants.DATA_FIELD_GIHWR)
        self.assertEqual(result, "UB (A+)")

    def test_best_gihwr_rating(self):
        self.mock_configuration.settings.result_format = constants.RESULT_FORMAT_RATING
        # Mock metrics to return mean=50, std=10 for rating calculation
        self.mock_metrics.get_metrics.return_value = (50.0, 10.0)
        
        card = {
            constants.DATA_FIELD_DECK_COLORS: {
                "WU": {constants.DATA_FIELD_GIHWR: 55.0, constants.DATA_FIELD_GIH: 100},
                "UB": {constants.DATA_FIELD_GIHWR: 70.0, constants.DATA_FIELD_GIH: 100},
                "RW": {constants.DATA_FIELD_GIHWR: 50.0, constants.DATA_FIELD_GIH: 100}
            }
        }
        
        # Test Best GIHWR with Rating
        # Rating calculation: ((winrate - lower_limit) / (upper_limit - lower_limit)) * 5.0
        # upper = mean + std * 2 = 70
        # lower = mean + std * -1.67 = 33.3
        # range = 36.7
        # UB: 70 -> (70-33.3)/36.7 * 5 = 5.0
        
        result = self.card_result._CardResult__process_best_performance(card, constants.DATA_FIELD_GIHWR)
        self.assertEqual(result, "UB (5.0)")

if __name__ == '__main__':
    unittest.main()
