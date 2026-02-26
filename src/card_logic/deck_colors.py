"""Deck color analysis and filtering"""
from itertools import combinations
from src import constants
from src.logger import create_logger
from src.card_logic.utils import get_card_colors
from src.card_logic.card_filtering import deck_card_search
from src.card_logic.deck_metrics import get_deck_metrics

logger = create_logger()

def calculate_color_affinity(deck_cards, color_filter, threshold, configuration):
    """This function identifies the main deck colors based on the GIHWR of the collected cards"""
    colors = {}

    for card in deck_cards:
        try:
            if color_filter in card[constants.DATA_FIELD_DECK_COLORS]:
                gihwr = card[constants.DATA_FIELD_DECK_COLORS][color_filter][constants.DATA_FIELD_GIHWR]
                if gihwr > threshold:
                    mana_colors = get_card_colors(card[constants.DATA_FIELD_MANA_COST])
                    for color in mana_colors:
                        if color not in colors:
                            colors[color] = 0
                        colors[color] += (gihwr - threshold)
        except Exception as error:
            logger.error(error)
    return colors

def calculate_color_rating(cards, color_filter, threshold, configuration):
    """This function identifies the main deck colors based on the GIHWR of the collected cards"""
    rating = 0

    for card in cards:
        try:
            if color_filter in card[constants.DATA_FIELD_DECK_COLORS]:
                gihwr = card[constants.DATA_FIELD_DECK_COLORS][color_filter][constants.DATA_FIELD_GIHWR]
                if gihwr > threshold:
                    rating += gihwr - threshold
        except Exception as error:
            logger.error(error)
    return rating

def calculate_curve_factor(deck, color_filter, configuration):
    """This function will assign a rating to a collection of cards based on how well they meet the deck building requirements"""
    curve_levels = [.10, .10, .10, .10, .15,
                    .15, .15, .20, .20, .20,
                    .25, .25, .25, .30, .30,
                    .30, .30, .40, .40, .40]

    curve_start = 15
    pick_number = len(deck)
    index = max(pick_number - curve_start, 0)
    curve_level = 0.0
    curve_factor = 0.0
    base_curve_factor = 1.0
    minimum_creature_count = configuration.card_logic.minimum_creatures

    try:
        filtered_cards = deck_card_search(
            deck,
            color_filter,
            constants.CARD_TYPE_DICT[constants.CARD_TYPE_SELECTION_NON_LANDS][0],
            True,
            True,
            False)
        deck_info = get_deck_metrics(filtered_cards)
        curve_level = curve_levels[int(
            min(index, len(curve_levels) - 1))]

        if deck_info.total_cards < configuration.card_logic.deck_control.maximum_card_count:
            curve_factor -= ((configuration.card_logic.deck_control.maximum_card_count - deck_info.creature_count)
                             / configuration.card_logic.deck_control.maximum_card_count) * curve_level
        elif deck_info.creature_count < minimum_creature_count:
            curve_factor = (deck_info.creature_count
                            / minimum_creature_count) * curve_level
        else:
            curve_factor = curve_level

    except Exception as error:
        logger.error(error)

    return base_curve_factor + curve_factor

def deck_colors(deck, colors_max, metrics, configuration):
    """This function determines the prominent colors for a collection of cards"""
    colors_result = {}
    try:
        mean, std = metrics.get_metrics(constants.FILTER_OPTION_ALL_DECKS, constants.DATA_FIELD_GIHWR)
        threshold = mean - 0.33 * std
        colors = calculate_color_affinity(
            deck, constants.FILTER_OPTION_ALL_DECKS, threshold, configuration)

        # Modify the dictionary to include ratings
        color_list = list(
            map((lambda x: {"color": x, "rating": colors[x]}), colors.keys()))

        # Sort the list by decreasing ratings
        color_list = sorted(
            color_list, key=lambda k: k["rating"], reverse=True)

        # Remove extra colors beyond limit
        color_list = color_list[0:colors_max]

        # Return colors
        sorted_colors = list(map((lambda x: x["color"]), color_list))

        # Create color permutation
        color_combination = []

        for count in range(colors_max + 1):
            if count > 1:
                color_combination.extend(combinations(sorted_colors, count))
            else:
                color_combination.extend((sorted_colors))

        # Convert tuples to list of strings
        color_strings = [''.join(tups) for tups in color_combination]
        color_strings = [x for x in color_strings if len(x) <= colors_max]

        color_strings = list(set(color_strings))

        color_dict = {}
        for color_string in color_strings:
            for color in color_string:
                if color_string not in color_dict:
                    color_dict[color_string] = 0
                color_dict[color_string] += colors[color]

        for color_option in constants.DECK_COLORS:
            for key, value in color_dict.items():
                if (len(key) == len(color_option)) and set(key).issubset(color_option):
                    colors_result[color_option] = value

        # Recalculate values based on the filtered win rates
        for color in colors_result:
            base_rating = calculate_color_rating(deck,
                                                 color,
                                                 threshold,
                                                 configuration)
            curve_factor = calculate_curve_factor(deck,
                                                  color,
                                                  configuration)
            colors_result[color] = base_rating * curve_factor

        # Add All Decks as a baseline
        colors_result[constants.FILTER_OPTION_ALL_DECKS] = calculate_color_rating(deck,
                                                                                  constants.FILTER_OPTION_ALL_DECKS,
                                                                                  mean,
                                                                                  configuration)
        colors_result = dict(
            sorted(colors_result.items(), key=lambda item: item[1], reverse=True))
    except Exception as error:
        logger.error(error)

    return colors_result

def auto_colors(deck, colors_max, metrics, configuration):
    """When the Auto deck filter is selected, this function identifies the prominent color pairs from the collected cards"""
    try:
        deck_colors_list = [constants.FILTER_OPTION_ALL_DECKS]
        colors_dict = {}
        deck_length = len(deck)
        if deck_length > 15:
            colors_dict = deck_colors(deck, colors_max, metrics, configuration)
            colors = list(colors_dict.keys())
            auto_select_threshold = max(70 - deck_length, 25)
            if len(colors) >= 2:
                if (colors_dict[colors[0]] - colors_dict[colors[1]]) > auto_select_threshold:
                    deck_colors_list = colors[0:1]
                elif configuration.settings.auto_highest_enabled:
                    deck_colors_list = colors[0:2]

    except Exception as error:
        logger.error(error)

    return deck_colors_list

def filter_options(deck, option_selection, metrics, configuration):
    """This function returns a list of colors based on the deck filter option"""
    filtered_color_list = [option_selection]
    try:
        if constants.FILTER_OPTION_AUTO in option_selection:
            filtered_color_list = auto_colors(deck, 5, metrics, configuration)
        else:
            filtered_color_list = [option_selection]
    except Exception as error:
        logger.error(error)
    return filtered_color_list
