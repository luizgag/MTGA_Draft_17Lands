"""Utility functions for card logic"""
from src import constants
from src.logger import create_logger

logger = create_logger()

def get_card_colors(mana_cost):
    """The function parses a mana cost string and returns a list of mana symbols"""
    colors = {}
    try:
        for color in constants.CARD_COLORS:
            if color in mana_cost:
                if color not in colors:
                    colors[color] = 1
                else:
                    colors[color] += 1

    except Exception as error:
        logger.error(error)
    return colors

def row_color_tag(mana_cost):
    """This function selects the color tag for a table row based on a card's mana cost"""
    colors = list(get_card_colors(mana_cost).keys())

    row_tag = constants.CARD_ROW_COLOR_COLORLESS_TAG
    if len(colors) > 1:
        row_tag = constants.CARD_ROW_COLOR_GOLD_TAG
    elif constants.CARD_COLOR_SYMBOL_RED in colors:
        row_tag = constants.CARD_ROW_COLOR_RED_TAG
    elif constants.CARD_COLOR_SYMBOL_BLUE in colors:
        row_tag = constants.CARD_ROW_COLOR_BLUE_TAG
    elif constants.CARD_COLOR_SYMBOL_BLACK in colors:
        row_tag = constants.CARD_ROW_COLOR_BLACK_TAG
    elif constants.CARD_COLOR_SYMBOL_WHITE in colors:
        row_tag = constants.CARD_ROW_COLOR_WHITE_TAG
    elif constants.CARD_COLOR_SYMBOL_GREEN in colors:
        row_tag = constants.CARD_ROW_COLOR_GREEN_TAG
    return row_tag

def field_process_sort(field_value):
    """This function collects the numeric order of a letter grade for the purpose of sorting"""
    processed_value = field_value

    try:
        # Remove the tier asterisks before sorting
        if isinstance(field_value, str):
            field_value = field_value.replace('*', '')
        if field_value in constants.GRADE_ORDER_DICT:
            processed_value = constants.GRADE_ORDER_DICT[field_value]
        elif field_value == constants.RESULT_UNKNOWN_STRING:
            processed_value = constants.RESULT_UNKNOWN_VALUE
    except ValueError:
        pass
    return processed_value

def format_tier_results(value, old_format, new_format):
    """This function converts the tier list ratings, from old tier lists, back to letter grades"""
    new_value = value
    try:
        # ratings to grades
        if (old_format == constants.RESULT_FORMAT_RATING) and (new_format == constants.RESULT_FORMAT_GRADE):
            new_value = constants.LETTER_GRADE_NA
            for grade, threshold in constants.TIER_CONVERSION_RATINGS_GRADES_DICT.items():
                if value > threshold:
                    new_value = grade
                    break
    except Exception as error:
        logger.error(error)

    return new_value

def stack_cards(cards):
    """The function will produce a list consisting of unique cards and the number of copies of each card"""
    deck = {}
    deck_list = []
    for card in cards:
        try:
            name = card[constants.DATA_FIELD_NAME]
            if name not in deck:
                deck[name] = {constants.DATA_FIELD_COUNT: 1}
                for data_field in constants.DATA_SET_FIELDS:
                    if data_field in card:
                        deck[name][data_field] = card[data_field]
            else:
                deck[name][constants.DATA_FIELD_COUNT] += 1
        except Exception as error:
            logger.error(error)
    # Convert to list format
    deck_list = list(deck.values())

    return deck_list

def copy_deck(deck, sideboard):
    """The function will produce a deck/sideboard list that is formatted in such a way that it can be copied to Arena and Sealdeck.tech"""
    deck_copy = ""
    try:
        # Copy Deck
        deck_copy = "Deck\n"
        # identify the arena_id for the cards
        for card in deck:
            deck_copy += f"{card[constants.DATA_FIELD_COUNT]} {card[constants.DATA_FIELD_NAME]}\n"

        # Copy sideboard
        if sideboard is not None:
            deck_copy += "\nSideboard\n"
            for card in sideboard:
                deck_copy += f"{card[constants.DATA_FIELD_COUNT]} {card[constants.DATA_FIELD_NAME]}\n"

    except Exception as error:
        logger.error(error)

    return deck_copy

def sort_cards_win_rate(cards, filter_order):
    """This function will acquire a non-zero win rate for each card and sort the cards by the win rate (highest to lowest)"""
    for card in cards:
        card["results"] = [0]
        try:
            for color_filter in filter_order:
                win_rate = card[constants.DATA_FIELD_DECK_COLORS][color_filter][constants.DATA_FIELD_GIHWR]
                if win_rate:
                    card["results"] = [win_rate]
                    break

        except Exception as error:
            logger.error(error)

    sorted_cards = sorted(
        cards, key=lambda k: k["results"][0], reverse=True)

    return sorted_cards

def ratings_limits(cards):
    """The function identifies the upper and lower win rates from a collection of cards"""
    upper_limit = 0
    lower_limit = 100

    for card in cards:
        for color in constants.DECK_COLORS:
            try:
                if color in cards[card][constants.DATA_FIELD_DECK_COLORS]:
                    gihwr = cards[card][constants.DATA_FIELD_DECK_COLORS][color][constants.DATA_FIELD_GIHWR]
                    if gihwr > upper_limit:
                        upper_limit = gihwr
                    if gihwr < lower_limit and gihwr != 0:
                        lower_limit = gihwr
            except Exception as error:
                logger.error(error)

    return upper_limit, lower_limit
