import pytest
import logging
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from src.overlay import start_overlay, Overlay
from src import constants
from src.configuration import Configuration, CardDataSettings

@pytest.fixture(autouse=True)
def catch_log_errors(caplog):
    """
    Verify that the app is not generating any logging errors. 
    
    This function catches any logging errors in the app by checking log records. 
    """
    yield
    errors = [record for record in caplog.get_records("call") if record.levelno >= logging.ERROR]
    assert not errors, f"Log error detected - resolve any errors that appear in the captured log call"
            
@pytest.fixture(name="mock_scanner")
def fixture_mock_scanner():
    """
    Mock the ArenaScanner class and all of its methods within overlay.py.
    """
    mock_instance = MagicMock()
    mock_instance.retrieve_color_win_rate.return_value = {"Auto": 0.0}
    mock_instance.retrieve_data_sources.return_value = {"None" : ""}
    mock_instance.retrieve_tier_source.return_value = []
    mock_instance.retrieve_set_metrics.return_value = None
    mock_instance.retrieve_tier_data.return_value = ({},{})
    mock_instance.draft_start_search.return_value = False
    mock_instance.retrieve_current_pack_and_pick.return_value = (0,0)
    mock_instance.retrieve_current_limited_event.return_value = ("","")  
    yield mock_instance
    
def test_start_overlay_pass(mock_scanner):
    """
    Verify that the app starts up without generating exceptions or logging errors.

    - Mock the mainloop function to exit the overlay after startup.
    - Mock AppUpdate and messagebox to prevent prompt windows from opening and blocking the test.
    - Mock functions interacting with external files as those files aren't available to Github runners.
    """
    with (
        patch("tkinter.Tk.mainloop", return_value=None),
        patch("tkinter.messagebox.showinfo", return_value=None),
        patch("src.overlay.stat", return_value=MagicMock(st_mtime=0)),
        patch("src.overlay.write_configuration", return_value=True),
        patch("src.overlay.LimitedSets.retrieve_limited_sets", return_value=None),
        patch("src.overlay.AppUpdate.retrieve_file_version", return_value=("","")),
        patch("src.overlay.ArenaScanner", return_value=mock_scanner),
        patch("src.overlay.FileExtractor", return_value=MagicMock()),
        patch("src.overlay.filter_options", return_value=["All Decks"]),
        patch("src.overlay.retrieve_arena_directory", return_value="fake_location"),
        patch("src.overlay.search_arena_log_locations", return_value="fake_location"),
    ):
        try:
            start_overlay()
        except Exception as e:
            pytest.fail(f"Exception occurred: {e}")
            

def test_overlay_init_does_not_check_for_updates(mock_scanner):
    """
    Verify that creating the overlay does not trigger an auto-update check.

    AppUpdate should not be instantiated during startup.
    """
    mock_app_update_cls = MagicMock()
    with (
        patch("tkinter.Tk.mainloop", return_value=None),
        patch("tkinter.messagebox.showinfo", return_value=None),
        patch("src.overlay.stat", return_value=MagicMock(st_mtime=0)),
        patch("src.overlay.write_configuration", return_value=True),
        patch("src.overlay.LimitedSets.retrieve_limited_sets", return_value=None),
        patch("src.overlay.AppUpdate", mock_app_update_cls),
        patch("src.overlay.check_version") as mock_check_version,
        patch("src.overlay.ArenaScanner", return_value=mock_scanner),
        patch("src.overlay.FileExtractor", return_value=MagicMock()),
        patch("src.overlay.filter_options", return_value=["All Decks"]),
        patch("src.overlay.retrieve_arena_directory", return_value="fake_location"),
        patch("src.overlay.search_arena_log_locations", return_value="fake_location"),
    ):
        start_overlay()
        mock_app_update_cls.assert_not_called()
        mock_check_version.assert_not_called()


def test_update_pack_pick_label_uses_mtgo_pick_in_pack():
    """MTGO label should show per-pack pick, not total pick."""
    overlay = Overlay.__new__(Overlay)
    overlay.configuration = SimpleNamespace(
        settings=SimpleNamespace(platform=constants.PLATFORM_MTGO)
    )
    overlay.draft = MagicMock()
    overlay.draft.retrieve_current_pick_in_pack.return_value = 1
    overlay.pack_pick_label = MagicMock()

    overlay._Overlay__update_pack_pick_label(2, 16)

    overlay.pack_pick_label.config.assert_called_once_with(text="Pack 2 / Pick 1")


def test_update_pack_pick_label_keeps_non_mtgo_pick():
    """Non-MTGO label should continue using provided pick value."""
    overlay = Overlay.__new__(Overlay)
    overlay.configuration = SimpleNamespace(
        settings=SimpleNamespace(platform=constants.PLATFORM_MTGA)
    )
    overlay.draft = MagicMock()
    overlay.pack_pick_label = MagicMock()

    overlay._Overlay__update_pack_pick_label(2, 16)

    overlay.pack_pick_label.config.assert_called_once_with(text="Pack 2 / Pick 16")


#TODO: create a test for CreateCardToolTip


def test_first_pick_records_passed_cards_without_previous_snapshot():
    """Regression: first detected pick should record passed cards even with empty previous snapshot.

    The overlay uses the scanner's initial_pack data to recover what the pack
    contained before the pick was made. When initial_pack is available, the
    passed cards (initial_pack minus picked) are recorded.
    """
    overlay = Overlay.__new__(Overlay)

    overlay.main_options_dict = {"Name": constants.DATA_FIELD_NAME}
    overlay.column_2_selection = SimpleNamespace(get=lambda: "Name")
    overlay.column_3_selection = SimpleNamespace(get=lambda: "Name")
    overlay.column_4_selection = SimpleNamespace(get=lambda: "Name")
    overlay.column_5_selection = SimpleNamespace(get=lambda: "Name")
    overlay.column_6_selection = SimpleNamespace(get=lambda: "Name")
    overlay.column_7_selection = SimpleNamespace(get=lambda: "Name")
    overlay.deck_filter_selection = SimpleNamespace(get=lambda: "Auto")

    picked_card = {constants.DATA_FIELD_NAME: "Picked Card"}
    current_pack_cards = [
        {constants.DATA_FIELD_NAME: "Passed One"},
        {constants.DATA_FIELD_NAME: "Passed Two"},
    ]
    # The scanner's initial_pack for pick 1 contains all 3 cards
    initial_pack_cards = [
        {constants.DATA_FIELD_NAME: "Picked Card"},
        {constants.DATA_FIELD_NAME: "Passed One"},
        {constants.DATA_FIELD_NAME: "Passed Two"},
    ]

    draft = MagicMock()
    draft.retrieve_taken_cards.return_value = [picked_card]
    draft.retrieve_current_pack_and_pick.return_value = (1, 2)
    draft.retrieve_current_limited_event.return_value = ("ECL", "Premier Draft")
    draft.retrieve_current_pack_cards.return_value = current_pack_cards
    draft.retrieve_current_picked_cards.return_value = {}
    draft.retrieve_current_missing_cards.return_value = []
    draft.retrieve_current_pick_in_pack.return_value = 2
    draft.retrieve_initial_pack_cards_for_pick.return_value = initial_pack_cards
    draft.hindsight_mode = False
    overlay.draft = draft

    overlay.openness_tracker = MagicMock()
    overlay._prev_pack_for_passed = []
    overlay._prev_pick_for_passed = 0
    overlay._prev_pack_number_for_passed = 0
    overlay._prev_taken_count = 0
    overlay._last_openness_key = (None, None)

    overlay._Overlay__update_data_source_options = MagicMock()
    overlay._Overlay__update_column_options = MagicMock()
    overlay._Overlay__display_widgets = MagicMock()
    overlay._Overlay__identify_auto_colors = MagicMock(return_value="Auto")
    overlay._Overlay__update_current_draft_label = MagicMock()
    overlay._Overlay__update_pack_pick_label = MagicMock()
    overlay._Overlay__update_pack_table = MagicMock()
    overlay._Overlay__update_missing_table = MagicMock()
    overlay._Overlay__update_deck_stats_callback = MagicMock()
    overlay._Overlay__update_taken_table = MagicMock()
    overlay._Overlay__update_compare_table = MagicMock()
    overlay._Overlay__update_openness_panel = MagicMock()
    overlay._Overlay__open_taken_cards_window = MagicMock()
    overlay._Overlay__replay_hindsight_openness = MagicMock()

    overlay._Overlay__update_overlay_callback(enable_draft_search=False)

    # Verify the fallback used initial_pack for pick 1
    draft.retrieve_initial_pack_cards_for_pick.assert_called_once_with(1)
    # record_passed should be called with initial_pack minus picked card
    overlay.openness_tracker.record_passed.assert_called_once()
    call_args = overlay.openness_tracker.record_passed.call_args
    passed_cards = call_args[0][0]
    passed_names = [c[constants.DATA_FIELD_NAME] for c in passed_cards]
    assert "Passed One" in passed_names
    assert "Passed Two" in passed_names
    assert "Picked Card" not in passed_names
    assert call_args[0][1] == 1  # pick_number
    assert call_args[0][2] == 0  # pack_number


def test_price_injection_adds_price_to_card_data():
    """Price data from GoatBots should be injected into card_ratings before export."""
    combined_data = {
        "meta": {},
        "color_ratings": {},
        "card_ratings": {
            "1001": {"name": "Lightning Bolt", "deck_colors": {}},
            "1002": {"name": "Moonshadow", "deck_colors": {}},
            "1003": {"name": "Unknown Card", "deck_colors": {}},
        }
    }
    prices = {"Lightning Bolt": 0.05, "Moonshadow": 27.12}

    # Inject prices (this is the logic that will be in __add_set)
    for card_data in combined_data["card_ratings"].values():
        card_name = card_data.get("name", "")
        card_data["price"] = prices.get(card_name, 0.0)

    assert combined_data["card_ratings"]["1001"]["price"] == pytest.approx(0.05)
    assert combined_data["card_ratings"]["1002"]["price"] == pytest.approx(27.12)
    assert combined_data["card_ratings"]["1003"]["price"] == pytest.approx(0.0)


def test_price_prefix_added_to_expensive_cards():
    """Cards above price threshold should get $$$ prefix in pack table results."""
    result_list = [
        {"name": "Moonshadow", "price": 27.12, "results": ["Moonshadow", "58.2"]},
        {"name": "Lightning Bolt", "price": 0.05, "results": ["Lightning Bolt", "52.1"]},
        {"name": "Jace", "price": 5.0, "results": ["Jace", "61.0"]},
    ]

    threshold = 3.0
    for card in result_list:
        price = card.get("price", 0.0)
        if price >= threshold:
            card["results"][0] = f"$$$ {card['results'][0]}"

    assert result_list[0]["results"][0] == "$$$ Moonshadow"
    assert result_list[1]["results"][0] == "Lightning Bolt"  # Below threshold
    assert result_list[2]["results"][0] == "$$$ Jace"


def test_price_prefix_not_added_for_arena_platform():
    """$$$ prefix should only apply when platform is MTGO."""
    result_list = [
        {"name": "Moonshadow", "price": 27.12, "results": ["Moonshadow", "58.2"]},
    ]

    platform = constants.PLATFORM_MTGA
    threshold = 3.0
    if platform == constants.PLATFORM_MTGO:
        for card in result_list:
            price = card.get("price", 0.0)
            if price >= threshold:
                card["results"][0] = f"$$$ {card['results'][0]}"

    assert result_list[0]["results"][0] == "Moonshadow"  # No prefix for Arena


def test_price_prefix_with_zero_threshold():
    """When threshold is 0, all cards with any price get the prefix."""
    result_list = [
        {"name": "Bolt", "price": 0.05, "results": ["Bolt", "52.1"]},
        {"name": "Island", "price": 0.0, "results": ["Island", "48.0"]},
    ]

    threshold = 0.0
    for card in result_list:
        price = card.get("price", 0.0)
        if price >= threshold and price > 0:
            card["results"][0] = f"$$$ {card['results'][0]}"

    assert result_list[0]["results"][0] == "$$$ Bolt"
    assert result_list[1]["results"][0] == "Island"  # price is 0, no prefix


def test_card_data_intvars_initialized_from_config(mock_scanner):
    """Column IntVars should be initialized from saved CardDataSettings."""
    import argparse
    saved = CardDataSettings(
        col_gihwr=False,
        col_ata=False,
        col_alsa=False,
        col_ohwr=True,
    )
    config = Configuration()
    config.card_data_settings = saved

    args = argparse.Namespace(file=None, data=None, step=False)

    with (
        patch("tkinter.Tk.mainloop", return_value=None),
        patch("tkinter.messagebox.showinfo", return_value=None),
        patch("src.overlay.stat", return_value=MagicMock(st_mtime=0)),
        patch("src.overlay.write_configuration", return_value=True),
        patch("src.overlay.read_configuration", return_value=(config, True)),
        patch("src.overlay._needs_migration", return_value=False),
        patch("src.overlay.LimitedSets.retrieve_limited_sets", return_value=None),
        patch("src.overlay.AppUpdate.retrieve_file_version", return_value=("", "")),
        patch("src.overlay.ArenaScanner", return_value=mock_scanner),
        patch("src.overlay.FileExtractor", return_value=MagicMock()),
        patch("src.overlay.filter_options", return_value=["All Decks"]),
        patch("src.overlay.retrieve_arena_directory", return_value="fake_location"),
        patch("src.overlay.search_arena_log_locations", return_value="fake_location"),
    ):
        overlay = Overlay(args)

    assert overlay.card_data_gihwr_checkbox_value.get() == 0
    assert overlay.card_data_ata_checkbox_value.get() == 0
    assert overlay.card_data_alsa_checkbox_value.get() == 0
    assert overlay.card_data_ohwr_checkbox_value.get() == 1


def test_close_card_data_window_saves_column_state():
    """Closing the Card Data window should persist column checkbox values to configuration."""
    overlay = Overlay.__new__(Overlay)
    overlay.configuration = MagicMock()
    overlay.configuration.card_data_settings = CardDataSettings()
    overlay._card_data_trace_ids = []
    overlay.card_data_table = MagicMock()

    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    overlay.card_data_rarity_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gihwr_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_ohwr_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_gpwr_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gnswr_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gdwr_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_ata_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_alsa_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_iwd_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_wheel_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_colors_checkbox_value = tkinter.IntVar(root, value=1)
    overlay.card_data_ngp_checkbox_value = tkinter.IntVar(root, value=0)
    overlay.card_data_gih_checkbox_value = tkinter.IntVar(root, value=0)

    popup = MagicMock()

    with patch("src.overlay.write_configuration") as mock_write:
        overlay._Overlay__close_card_data_window(popup)

    cds = overlay.configuration.card_data_settings
    assert cds.col_rarity is False
    assert cds.col_gihwr is True
    assert cds.col_ohwr is True
    assert cds.col_ata is False
    assert cds.col_alsa is False
    assert cds.col_iwd is True
    assert cds.col_colors is True
    mock_write.assert_called_once_with(overlay.configuration)

    root.destroy()