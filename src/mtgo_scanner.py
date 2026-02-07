"""This module contains the functions that are used for parsing MTGO draft logs"""
import os
import re
import logging
from enum import Enum
from src.logger import create_logger
from src.set_metrics import SetMetrics
from src.dataset import Dataset
from src import constants
from src.utils import Result, retrieve_local_set_list

if not os.path.exists(constants.DRAFT_LOG_FOLDER):
    os.makedirs(constants.DRAFT_LOG_FOLDER)

LOG_TYPE_DRAFT = "draftLog"

logger = create_logger()


class MtgoScannerState(Enum):
    WAITING = 1
    PACK_SHOWN = 2
    PICK_MADE = 3


class MtgoScanner:
    '''Class that handles the processing of MTGO draft log files'''

    def __init__(self, log_folder, set_list, sets_location: str = constants.SETS_FOLDER, step_through: bool = False, retrieve_unknown: bool = False):
        self.log_folder = log_folder
        self.set_list = set_list
        self.draft_log = logging.getLogger(LOG_TYPE_DRAFT)
        self.draft_log.setLevel(logging.INFO)
        self.sets_location = sets_location

        self.logging_enabled = False

        self.step_through = step_through
        self.set_data = Dataset(retrieve_unknown)
        self.draft_type = constants.LIMITED_TYPE_UNKNOWN
        self.draft_sets = []
        self.current_pick = 0
        self.current_pack = 0
        self.number_of_players = 8
        self.taken_cards = []
        self.pack_cards = []
        self.initial_pack_cards = []
        self.picked_cards_in_pack = []
        self.file_size = 0
        self.search_offset = 0
        self.data_source = "None"
        self.event_string = ""
        self.draft_label = ""
        self.current_file = ""
        self.hero = ""
        self.state = MtgoScannerState.WAITING
        self.current_pick_in_pack = 0
        self.draft_detected = False

    def set_arena_file(self, filename):
        '''Public function for compatibility - sets the log folder'''
        if os.path.isdir(filename):
            self.log_folder = filename
        else:
            self.log_folder = os.path.dirname(filename)

    def log_enable(self, enable):
        '''Enable/disable the application draft log feature'''
        self.logging_enabled = enable
        self.log_suspend(not enable)

    def log_suspend(self, suspended):
        '''Prevents the application from updating the draft log file'''
        if suspended:
            self.draft_log.setLevel(logging.CRITICAL)
        elif self.logging_enabled:
            self.draft_log.setLevel(logging.INFO)

    def clear_draft(self, full_clear):
        '''Clear the stored draft data'''
        if full_clear:
            self.search_offset = 0
            self.file_size = 0
            self.current_file = ""
        self.set_data.clear()
        self.draft_type = constants.LIMITED_TYPE_UNKNOWN
        self.draft_sets = []
        self.current_pick = 0
        self.current_pack = 0
        self.number_of_players = 8
        self.taken_cards = []
        self.pack_cards = []
        self.initial_pack_cards = []
        self.picked_cards_in_pack = []
        self.data_source = "None"
        self.draft_label = ""
        self.hero = ""
        self.state = MtgoScannerState.WAITING
        self.current_pick_in_pack = 0
        self.draft_detected = False

    def draft_start_search(self):
        '''Search for the most recent MTGO draft log file and detect a new draft'''
        update = False

        try:
            if not self.log_folder or not os.path.isdir(self.log_folder):
                return False

            newest_file = self.__find_newest_draft_file()

            if not newest_file:
                return False

            # New file detected
            if newest_file != self.current_file:
                self.clear_draft(False)
                self.current_file = newest_file
                self.search_offset = 0
                self.file_size = 0

                # Parse header
                if self.__parse_header():
                    self.draft_detected = True
                    self.draft_type = constants.LIMITED_TYPE_MTGO_DRAFT
                    update = True
                    logger.info("New MTGO draft detected: %s, sets: %s",
                                self.current_file, self.draft_sets)

        except Exception as error:
            logger.error(error)

        return update

    def draft_data_search(self, use_ocr=False, save_screenshot=False):
        '''Search the current draft log file for new pack/pick data'''
        update = False

        try:
            if not self.current_file or not os.path.isfile(self.current_file):
                return False

            current_size = os.path.getsize(self.current_file)

            if current_size <= self.file_size:
                return False

            self.file_size = current_size

            with open(self.current_file, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(self.search_offset)
                new_content = f.read()
                self.search_offset = f.tell()

            if new_content:
                update = self.__parse_draft_content(new_content)

        except Exception as error:
            logger.error(error)

        return update

    def retrieve_data_sources(self):
        '''Return a list of set files that can be used with the current active draft'''
        data_sources = {}

        try:
            if self.draft_type != constants.LIMITED_TYPE_UNKNOWN and self.draft_sets:
                set_ids = self.draft_sets[:]
                set_ids.extend([x.seventeenlands[0] for x in self.set_list.data.values() if x.set_code in self.draft_sets])
                file_list, error_list = retrieve_local_set_list(set_ids)

                for error_string in error_list:
                    logger.error(error_string)

                if file_list:
                    file_list.sort(key=lambda x: x[1] == constants.LIMITED_TYPE_STRING_DRAFT_PREMIER, reverse=True)

                for file in file_list:
                    set_code = file[0]
                    event_type = file[1]
                    user_group = file[2]
                    location = file[6]
                    if re.search(r"^[Yy]\d{2}", set_code):
                        type_string = f"[{set_code[0:3]}]{event_type} ({user_group})"
                    elif re.search(r'[.\-/]', set_code):
                        dataset_type = re.split(r'[.\-/]', set_code)[-1]
                        type_string = f"[{dataset_type[0:3]}] {event_type} ({user_group})"
                    else:
                        type_string = f"{event_type} ({user_group})"
                    data_sources[type_string] = location

        except Exception as error:
            logger.error(error)

        if not data_sources:
            data_sources = constants.DATA_SOURCES_NONE

        return data_sources

    def retrieve_set_data(self, file):
        '''Retrieve set data from the set data files'''
        result = Result.ERROR_MISSING_FILE
        self.set_data.clear()

        try:
            result = self.set_data.open_file(file)
        except Exception as error:
            logger.error(error)

        return result

    def retrieve_set_metrics(self):
        '''Parse set data and calculate the mean and standard deviation for a set'''
        return SetMetrics(self.set_data)

    def retrieve_color_win_rate(self, label_type):
        '''Parse set data and return a list of color win rates'''
        deck_colors = {}
        for colors in constants.DECK_FILTERS:
            deck_color = colors
            if (label_type == constants.DECK_FILTER_FORMAT_NAMES) and (deck_color in constants.COLOR_NAMES_DICT):
                deck_color = constants.COLOR_NAMES_DICT[deck_color]
            deck_colors[colors] = deck_color

        try:
            color_ratings = self.set_data.get_color_ratings()
            if color_ratings:
                for colors in color_ratings:
                    for deck_color in deck_colors:
                        if (len(deck_color) == len(colors)) and set(deck_color).issubset(colors):
                            filter_label = deck_color
                            if (label_type == constants.DECK_FILTER_FORMAT_NAMES) and (deck_color in constants.COLOR_NAMES_DICT):
                                filter_label = constants.COLOR_NAMES_DICT[deck_color]
                            ratings_string = filter_label + \
                                f' ({color_ratings[colors]}%)'
                            deck_colors[deck_color] = ratings_string
        except Exception as error:
            logger.error(error)

        deck_colors = {v: k for k, v in deck_colors.items()}
        return deck_colors

    def retrieve_current_picked_cards(self):
        '''Return the card data for cards picked in the current pack'''
        return self.set_data.get_data_by_name(self.picked_cards_in_pack)

    def retrieve_current_missing_cards(self):
        '''Retrieve a list of missing cards from the current pack'''
        missing_cards = []

        try:
            current_names = [c for c in self.pack_cards]
            missing_names = [c for c in self.initial_pack_cards
                             if c not in current_names and c not in self.picked_cards_in_pack]
            missing_cards = self.set_data.get_data_by_name(missing_names)
        except Exception as error:
            logger.error(error)

        return missing_cards

    def retrieve_current_pack_cards(self):
        '''Return the cards from the current pack'''
        return self.set_data.get_data_by_name(self.pack_cards)

    def retrieve_taken_cards(self):
        '''Return the card data for all of the cards that were picked during the draft'''
        return self.set_data.get_data_by_name(self.taken_cards)

    def retrieve_current_pack_and_pick(self):
        '''Return the current pack and pick numbers'''
        return self.current_pack, self.current_pick

    def retrieve_current_pick_in_pack(self):
        '''Return the pick number within the current pack (1-based, resets each pack)'''
        return self.current_pick_in_pack

    def retrieve_current_limited_event(self):
        '''Return the set code string and event type string'''
        event_set = ""
        event_type = ""

        try:
            event_set = self.draft_sets[0] if self.draft_sets else ""
            event_type = self.draft_label
        except Exception as error:
            logger.error(error)

        return event_set, event_type

    # --- Private methods ---

    def __find_newest_draft_file(self):
        '''Find the most recently modified .txt file in the MTGO log folder'''
        newest_file = None
        newest_mtime = 0

        try:
            for filename in os.listdir(self.log_folder):
                if filename.endswith('.txt'):
                    filepath = os.path.join(self.log_folder, filename)
                    mtime = os.path.getmtime(filepath)
                    if mtime > newest_mtime:
                        newest_mtime = mtime
                        newest_file = filepath
        except Exception as error:
            logger.error(error)

        return newest_file

    def __parse_header(self):
        '''Parse the MTGO draft log header to extract event info, players, and set codes'''
        try:
            with open(self.current_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            self.search_offset = len(content)
            self.file_size = os.path.getsize(self.current_file)

            lines = content.split('\n')

            # Extract set codes from filename
            self.draft_sets = self.__extract_set_codes_from_filename(self.current_file)
            if not self.draft_sets:
                return False

            self.draft_label = "BoosterDraft"

            # Parse players and hero
            in_players = False
            for line in lines:
                if line.strip() == "Players:":
                    in_players = True
                    continue

                if in_players:
                    if line.strip() == "":
                        in_players = False
                        continue
                    if line.startswith("-->"):
                        self.hero = line[4:].strip()
                    # Count players
                    # (players are indented or prefixed with -->)

            # Parse any initial pack/pick data already in file
            self.__parse_draft_content(content)

            return True

        except Exception as error:
            logger.error(error)
            return False

    def __extract_set_codes_from_filename(self, filepath):
        '''Extract set codes from the MTGO draft log filename.

        Filename format: <username>-<date>-<event_num>-<event_id>-<set_codes>.txt
        Set codes suffix: e.g., "ECLECLECL" = 3 packs of ECL (3-char code repeated)
        '''
        set_codes = []

        try:
            basename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(basename)[0]

            # The set codes are the last segment after the final hyphen
            parts = name_without_ext.rsplit('-', 1)
            if len(parts) < 2:
                return set_codes

            codes_string = parts[1]

            # Set codes are 3 characters each, repeated for each pack
            if len(codes_string) >= 3 and len(codes_string) % 3 == 0:
                for i in range(0, len(codes_string), 3):
                    code = codes_string[i:i+3].upper()
                    if code not in set_codes:
                        set_codes.append(code)

        except Exception as error:
            logger.error(error)

        return set_codes

    def __parse_draft_content(self, content):
        '''Parse draft content to extract pack and pick information.

        Returns True if new pack data was found that should trigger a UI update.
        '''
        update = False

        try:
            lines = content.split('\n')
            i = 0

            while i < len(lines):
                line = lines[i]

                # Detect pack/pick header: "Pack N pick M:"
                pack_match = re.match(r'^Pack (\d+) pick (\d+):', line)
                if pack_match:
                    pack_num = int(pack_match.group(1))

                    # Detect pack transition
                    if pack_num != self.current_pack:
                        self.current_pack = pack_num
                        self.current_pick_in_pack = 0
                        self.picked_cards_in_pack = []
                        self.initial_pack_cards = []

                    # Collect card names following this header
                    card_names = []
                    picked_card = None
                    i += 1

                    while i < len(lines):
                        card_line = lines[i]

                        # Empty line or "Picked:" line signals end of this pick block
                        if card_line.strip() == "":
                            break
                        if card_line.startswith("Picked:"):
                            break

                        # Check for pack header line (------ Pack N: ...)
                        if card_line.startswith("------"):
                            break

                        # Card with pick marker
                        if card_line.startswith("-->"):
                            picked_card = card_line[4:].strip()
                            card_names.append(picked_card)
                        else:
                            card_name = card_line.strip()
                            if card_name:
                                card_names.append(card_name)

                        i += 1

                    # Process the collected data
                    if card_names:
                        self.current_pick_in_pack += 1
                        self.current_pick = (self.current_pack - 1) * 15 + self.current_pick_in_pack

                        if picked_card:
                            # Phase 2: Pick was made
                            # Remove picked card from pack display
                            remaining = [c for c in card_names if c != picked_card]
                            self.pack_cards = remaining
                            self.picked_cards_in_pack.append(picked_card)
                            self.taken_cards.append(picked_card)
                            self.state = MtgoScannerState.PICK_MADE

                            # Store initial pack if first pick in this pack
                            if self.current_pick_in_pack == 1:
                                self.initial_pack_cards = card_names[:]

                            update = True
                        else:
                            # Phase 1: Pack shown, no pick yet
                            self.pack_cards = card_names[:]
                            self.state = MtgoScannerState.PACK_SHOWN

                            # Store initial pack if first pick in this pack
                            if self.current_pick_in_pack == 1:
                                self.initial_pack_cards = card_names[:]

                            update = True

                    continue

                i += 1

        except Exception as error:
            logger.error(error)

        return update
