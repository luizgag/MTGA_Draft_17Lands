import unittest
from unittest.mock import patch, MagicMock
import os
from src.constants import SETS_FOLDER
from src.utils import (
    capture_screen_base64str,
    retrieve_local_set_list,
    Result
)

SCREENSHOT_FOLDER = os.path.join(os.getcwd(), "Screenshots")
SCREENSHOT_PREFIX = "p1p1_screenshot_"

MOCKED_SET_CODES = ["MH3", "OTJ"]

# After DB migration only 2-segment (merged) entries exist — no 4-segment event_type entries
MOCKED_DB_META = [
    {"set_code": "MH3", "start_date": "2019-01-01", "end_date": "2024-07-11", "game_count": 0, "collection_date": "", "version": 2.0},
    {"set_code": "OTJ", "start_date": "2019-01-01", "end_date": "2024-07-11", "game_count": 0, "collection_date": "", "version": 2.0},
    # DMU is not in MOCKED_SET_CODES — should be filtered out
    {"set_code": "DMU", "start_date": "2022-09-09", "end_date": "2023-01-01", "game_count": 5000, "collection_date": "", "version": 2.0},
]

MOCKED_DATASETS_LIST_VALID = [
    ("MH3", "", "", "2019-01-01", "2024-07-11", 0, os.path.join(SETS_FOLDER, "MH3_Data.json")),
    ("OTJ", "", "", "2019-01-01", "2024-07-11", 0, os.path.join(SETS_FOLDER, "OTJ_Data.json")),
]

class TestCaptureScreenBase64str(unittest.TestCase):

    @patch('PIL.ImageGrab.grab')
    @patch('time.time')
    @patch('os.path.join')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_screenshot_persist(self, mock_open, mock_path_join, mock_time, mock_grab):
        # Arrange
        mock_image = MagicMock()
        mock_grab.return_value = mock_image
        mock_time.return_value = 1234567890
        mock_path_join.return_value = "/Screenshots/screenshot_1234567890.png"
        
        expected_filename = "/Screenshots/screenshot_1234567890.png"
        
        # Act
        base64str = capture_screen_base64str(True)
        
        # Assert
        mock_grab.assert_called_once()
        mock_time.assert_called_once()
        mock_path_join.assert_called_once_with(SCREENSHOT_FOLDER, SCREENSHOT_PREFIX + "1234567890.png")
        mock_image.save.assert_any_call(expected_filename, format="PNG")
        self.assertIsInstance(base64str, str)

    @patch('PIL.ImageGrab.grab')
    @patch('time.time')
    @patch('os.path.join')
    @patch('builtins.open', new_callable=unittest.mock.mock_open)
    def test_screenshot_not_persist(self, mock_open, mock_path_join, mock_time, mock_grab):
        # Arrange
        mock_image = MagicMock()
        mock_grab.return_value = mock_image
        
        # Act
        base64str = capture_screen_base64str(False)
        
        # Assert
        mock_grab.assert_called_once()
        mock_time.assert_not_called()
        mock_path_join.assert_not_called()
        self.assertIsInstance(base64str, str)

if __name__ == '__main__':
    unittest.main()

@patch("src.utils.database.list_datasets_with_meta")
def test_retrieve_local_set_list_from_db(mock_list_meta):
    """Verify that the function reads from DB and filters by provided codes."""
    mock_list_meta.return_value = MOCKED_DB_META

    file_list, error_list = retrieve_local_set_list(MOCKED_SET_CODES)

    assert not error_list
    # Only MH3 and OTJ should be returned (DMU is filtered out)
    assert file_list == MOCKED_DATASETS_LIST_VALID
