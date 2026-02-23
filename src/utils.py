import base64
import json
import os
import time
import platform
import subprocess
import tkinter
from enum import Enum
from io import BytesIO
from PIL import ImageGrab
from typing import List
from src.constants import (
    LIMITED_USER_GROUP_ALL,
    LIMITED_TYPES_DICT,
    LIMITED_GROUPS_LIST,
    SET_FILE_SUFFIX,
    SETS_FOLDER,
    DATA_FIELD_NAME,
    DATA_FIELD_COLORS,
    DATA_FIELD_CMC,
    DATA_FIELD_TYPES,
    DATA_FIELD_DECK_COLORS,
    DATA_FIELD_GIHWR,
    DATA_FIELD_ALSA,
    DATA_FIELD_IWD,
    DATA_FIELD_MANA_COST,
    DATA_SECTION_IMAGES,
    FILTER_OPTION_ALL_DECKS,
    SCREENSHOT_FOLDER,
    SCREENSHOT_PREFIX
)

class Result(Enum):
    '''Enumeration class for file integrity results'''
    VALID = 0
    ERROR_MISSING_FILE = 1
    ERROR_UNREADABLE_FILE = 2

def process_json(obj):
    """ 
    Convert JSON string with escape characters to a nested dictionary 
    """
    if isinstance(obj, dict):
        return {key: process_json(value) for key, value in obj.items()}
    elif isinstance(obj, str):
        try:
            parsed_json = json.loads(obj)
            return process_json(parsed_json)
        except json.JSONDecodeError:
            return obj
    else:
        return obj
        
def json_find(key, obj):
    """ 
    Retrieve a value from a nested dictionary using a specified key.
    """
    result = None
    if isinstance(obj, dict):
        if key in obj:
            result = obj[key]
        else:
            for value in obj.values():
                result = json_find(key, value)
                if result is not None:
                    break
    return result

def retrieve_local_set_list(codes, names=None, db_path=None):
    '''Returns a list of valid datasets from the SQLite database matching the given codes.

    Each entry is a tuple:
        (set_name, event_type, user_group, start_date, end_date, game_count, file_location)

    All DB-stored datasets are merged (2-segment) so event_type="" and user_group="".
    file_location is a synthetic path compatible with Dataset.open_file().
    '''
    import src.database as database

    file_list = []
    error_list = []
    cleaned_codes = [clean_string(code) for code in codes]

    try:
        all_meta = database.list_datasets_with_meta(db_path)
    except Exception as error:
        error_list.append(error)
        return file_list, error_list

    for row in all_meta:
        try:
            set_code = row["set_code"]
            if set_code not in cleaned_codes:
                continue

            if names:
                idx = list(cleaned_codes).index(set_code)
                set_name = list(names)[idx]
            else:
                set_name = set_code

            start_date = row.get("start_date", "")
            end_date = row.get("end_date", "")
            game_count = int(row.get("game_count", 0) or 0)

            # Synthetic file path so Dataset.open_file() can derive the set_code
            file_location = os.path.join(SETS_FOLDER, f"{set_code}_{SET_FILE_SUFFIX}")

            file_list.append((
                set_name,
                "",       # event_type — always empty for merged DB entries
                "",       # user_group — always empty for merged DB entries
                start_date,
                end_date,
                game_count,
                file_location,
            ))
        except Exception as error:
            error_list.append(error)

    return file_list, error_list
    
def check_file_integrity(filename):
    '''Extracts data from a file to determine if it's formatted correctly'''
    result = Result.VALID
    json_data = {}

    try:
        with open(filename, 'r', encoding="utf-8", errors="replace") as json_file:
            json_data = json_file.read()
    except FileNotFoundError:
        return Result.ERROR_MISSING_FILE, json_data

    try:
        json_data = json.loads(json_data)

        if json_data.get("meta"):
            meta = json_data["meta"]
            version = meta.get("version")
            if version == 1:
                meta.get("date_range", "").split("->")
            else:
                meta.get("start_date")
                meta.get("end_date")
        else:
            return Result.ERROR_UNREADABLE_FILE, json_data

        cards = json_data.get("card_ratings")
        if isinstance(cards, dict) and len(cards) >= 100:
            for card in cards.values():
                card.get(DATA_FIELD_NAME)
                card.get(DATA_FIELD_COLORS)
                card.get(DATA_FIELD_CMC)
                card.get(DATA_FIELD_TYPES)
                card.get(DATA_FIELD_MANA_COST)
                card.get(DATA_SECTION_IMAGES)
                deck_colors = card.get(DATA_FIELD_DECK_COLORS, {}).get(FILTER_OPTION_ALL_DECKS, {})
                deck_colors.get(DATA_FIELD_GIHWR)
                deck_colors.get(DATA_FIELD_ALSA)
                deck_colors.get(DATA_FIELD_IWD)
                break
        else:
            return Result.ERROR_UNREADABLE_FILE, json_data

    except json.JSONDecodeError:
        return Result.ERROR_UNREADABLE_FILE, json_data

    return result, json_data

def capture_screen_base64str(persist):
    '''takes a screenshot and returns it as a base64 encoded string'''
    screenshot = ImageGrab.grab()
    buffered = BytesIO()
    screenshot.save(buffered, format="PNG")
    if persist:
        current_timestamp = int(time.time())
        filename = SCREENSHOT_PREFIX + str(current_timestamp) + ".png"
        if not os.path.exists(SCREENSHOT_FOLDER):
            os.makedirs(SCREENSHOT_FOLDER)
        screenshot.save(os.path.join(SCREENSHOT_FOLDER, filename), format="PNG")

    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def detect_string(search_line: str, search_strings: List[str], replace: str = '_') -> int:
    '''Search a line for a string and return the offset at the end of the string.'''
    # Extend search strings with modified versions (replacing 'replace' character)
    modified_strings = search_strings + [
        string.replace(replace, "") for string in search_strings
    ]
    # Find the first matching string and return its offset
    for string in modified_strings:
        if string in search_line:
            return search_line.find(string) + len(string)
    # Return -1 if no match is found
    return -1
    
def open_file(file_path: str):
    """
    Open a file in its default application based on the operating system.

    Parameters:
        file_path (str): The path to the file to be opened.

    Behavior:
        - On Windows: Uses os.startfile() to open the file with the default application.
        - On macOS: Uses the 'open' command via subprocess to open the file.
        - On Linux/Unix: Uses the 'xdg-open' command via subprocess to open the file.
    
    This function ensures cross-platform compatibility for opening files.
    """
    if platform.system() == 'Windows':
        os.startfile(file_path)
    elif platform.system() == 'Darwin':  # macOS
        subprocess.call(['open', file_path])
    else:  # Linux and other Unix-based systems
        subprocess.call(['xdg-open', file_path])

def clean_string(input_string: str, uppercase: bool = True) -> str:
    '''Cleans a string by removing unwanted characters'''
    unwanted_chars = [' ', '.', '/', '_']
    for char in unwanted_chars:
        input_string = input_string.replace(char, '')
    return input_string.upper() if uppercase else input_string


class AutocompleteEntry(tkinter.Entry):
    def initialize(self, completion_list):
        self.completion_list = completion_list
        self.hitsIndex = -1
        self.hits = []
        self.autocompleted = False
        self.current = ""
        self.bind('<KeyRelease>', self.act_on_release)
        self.bind('<KeyPress>', self.act_on_press)

    def autocomplete(self):
        self.current = self.get().lower()
        self.hits = [item for item in self.completion_list if item.lower().startswith(self.current)]
        if self.hits:
            self.hitsIndex = 0  # Start with the first hit
            self.display_autocompletion()
        else:
            self.hitsIndex = -1
            self.remove_autocompletion()

    def remove_autocompletion(self):
        self.autocompleted = False

    def display_autocompletion(self):
        if self.hitsIndex == -1:
            self.remove_autocompletion()  # Don't display anything if hitsIndex is -1
            return
        if self.hits:
            cursor = self.index(tkinter.INSERT)
            self.delete(0, tkinter.END)
            self.insert(0, self.hits[self.hitsIndex])
            self.select_range(cursor, tkinter.END)
            self.icursor(cursor)
            self.autocompleted = True
        else:
            self.autocompleted = False

    def act_on_release(self, event):
        if event.keysym in ('BackSpace', 'Delete'):
            self.autocompleted = False
            return

        if event.keysym not in ('Down', 'Up', 'Tab', 'Right', 'Left'):
            self.autocomplete()

    def act_on_press(self, event):
        if event.keysym == 'Left':
            if self.autocompleted:
                self.remove_autocompletion()
                return "break"

        if event.keysym in ('Down', 'Up', 'Tab'):
            if self.select_present():
                cursor = self.index(tkinter.SEL_FIRST)
                if self.hits and self.current == self.get().lower()[0:cursor]:
                    if event.keysym == 'Up':
                        self.hitsIndex = (self.hitsIndex - 1) % len(self.hits)
                    else:
                        self.hitsIndex = (self.hitsIndex + 1) % len(self.hits)
                    self.display_autocompletion()
            else:
                self.autocomplete()
            return "break"

        if event.keysym == 'Right':
            if self.select_present():
                self.selection_clear()
                self.icursor(tkinter.END)
                return "break"

        if event.keysym in ('BackSpace', 'Delete'):
            if self.autocompleted:
                self.remove_autocompletion()

    def select_present(self):
        try:
            self.index(tkinter.SEL_FIRST)
            return True
        except tkinter.TclError:
            return False