"""Deck building and suggestion logic"""
import math
from src import constants
from src.logger import create_logger
from src.card_logic.utils import get_card_colors, stack_cards
from src.card_logic.card_filtering import deck_card_search
from src.card_logic.deck_metrics import deck_color_stats
from src.card_logic.deck_colors import calculate_color_affinity, deck_colors

logger = create_logger()

def card_cmc_search(deck, offset, starting_cmc, cmc_limit, remaining_count):
    """The function will use recursion to search through a collection of cards and produce a list of cards with a mean CMC that is below a specific limit"""
    cards = []
    unused = []
    try:
        for count, card in enumerate(deck[offset:]):
            card_cmc = card[constants.DATA_FIELD_CMC]

            if card_cmc + starting_cmc <= cmc_limit:
                card_cmc += starting_cmc
                current_offset = offset + count
                current_remaining = int(max(remaining_count - 1, 0))
                if current_remaining == 0:
                    cards.append(card)
                    unused.extend(deck[current_offset + 1:])
                    break
                elif current_offset > (len(deck) - remaining_count):
                    unused.extend(deck[current_offset:])
                    break
                else:
                    current_offset += 1
                    cards, skipped = card_cmc_search(
                        deck, current_offset, card_cmc, cmc_limit, current_remaining)
                    if cards:
                        cards.append(card)
                        unused.extend(skipped)
                        break
                    else:
                        unused.append(card)
            else:
                unused.append(card)
    except Exception as error:
        logger.error(error)

    return cards, unused

def deck_rating(deck, deck_type, color, threshold):
    """The function will produce a deck rating based on the combined GIHWR value for each card with a GIHWR value above a certain threshold"""
    rating = 0
    try:
        # Combined GIHWR of the cards
        for card in deck:
            try:
                gihwr = card[constants.DATA_FIELD_DECK_COLORS][color][constants.DATA_FIELD_GIHWR]
                if gihwr > threshold:
                    rating += gihwr
            except Exception:
                pass

        # Deck contains the recommended number of creatures
        recommended_creature_count = deck_type.recommended_creature_count
        filtered_cards = deck_card_search(
            deck, color, [constants.CARD_TYPE_CREATURE], True, True, False)

        if len(filtered_cards) < recommended_creature_count:
            rating -= (recommended_creature_count - len(filtered_cards)) * 10

        # Average CMC of the creatures is below the ideal cmc average
        cmc_average = deck_type.cmc_average
        total_cards = len(filtered_cards)
        total_cmc = 0

        for card in filtered_cards:
            total_cmc += card[constants.DATA_FIELD_CMC]

        cmc = total_cmc / total_cards

        if cmc > cmc_average:
            rating -= 50

        # Cards fit distribution
        minimum_distribution = deck_type.distribution
        distribution = [0, 0, 0, 0, 0, 0, 0]
        for card in filtered_cards:
            index = int(min(card[constants.DATA_FIELD_CMC],
                        len(minimum_distribution) - 1))
            distribution[index] += 1

    except Exception as error:
        logger.error(error)

    rating = int(rating)

    return rating

def color_splash(cards, colors, splash_threshold, configuration):
    """The function will parse a list of cards to determine if there are any cards that might justify a splash"""
    color_affinity = {}
    splash_color = ""
    try:
        # Calculate affinity to rank colors based on splash threshold (minimum GIHWR)
        color_affinity = calculate_color_affinity(
            cards, colors, splash_threshold, configuration)

        # Modify the dictionary to include ratings
        color_affinity = list(
            map((lambda x: {"color": x, "rating": color_affinity[x]}), color_affinity.keys()))
        # Remove the current colors
        filtered_colors = color_affinity[:]
        for color in color_affinity:
            if color["color"] in colors:
                filtered_colors.remove(color)
        # Sort the list by decreasing ratings
        filtered_colors = sorted(
            filtered_colors, key=lambda k: k["rating"], reverse=True)

        if filtered_colors:
            splash_color = filtered_colors[0]["color"]
    except Exception as error:
        logger.error(error)
    return splash_color

def mana_base(deck):
    """The function will identify the number of lands that are needed to fill out a deck"""
    maximum_deck_size = 40
    combined_deck = []
    mana_types = {"Swamp": {"color": constants.CARD_COLOR_SYMBOL_BLACK, constants.DATA_FIELD_COUNT: 0},
                  "Forest": {"color": constants.CARD_COLOR_SYMBOL_GREEN, constants.DATA_FIELD_COUNT: 0},
                  "Mountain": {"color": constants.CARD_COLOR_SYMBOL_RED, constants.DATA_FIELD_COUNT: 0},
                  "Island": {"color": constants.CARD_COLOR_SYMBOL_BLUE, constants.DATA_FIELD_COUNT: 0},
                  "Plains": {"color": constants.CARD_COLOR_SYMBOL_WHITE, constants.DATA_FIELD_COUNT: 0}}
    total_count = 0
    try:
        number_of_lands = 0 if maximum_deck_size < len(
            deck) else maximum_deck_size - len(deck)

        # Go through the cards and count the mana types
        for card in deck:
            if constants.CARD_TYPE_LAND in card[constants.DATA_FIELD_TYPES]:
                # Subtract symbol for lands
                for mana_type in mana_types.values():
                    mana_type[constants.DATA_FIELD_COUNT] -= (1 if (mana_type["color"] in card[constants.DATA_FIELD_COLORS])
                                                              else 0)
            else:
                # Increase count for abilities that are not part of the mana cost
                mana_count = get_card_colors(card[constants.DATA_FIELD_MANA_COST])
                # for color in card[constants.DATA_FIELD_COLORS]:
                #    mana_count[color] = (
                #        mana_count[color] + 1) if color in mana_count else 1

                for mana_type in mana_types.values():
                    color = mana_type["color"]
                    mana_type[constants.DATA_FIELD_COUNT] += mana_count[color] if color in mana_count else 0

        for land in mana_types.values():
            land[constants.DATA_FIELD_COUNT] = max(
                land[constants.DATA_FIELD_COUNT], 0)
            total_count += land[constants.DATA_FIELD_COUNT]

        # Sort by lowest count
        mana_types = dict(
            sorted(mana_types.items(), key=lambda t: t[1][constants.DATA_FIELD_COUNT]))
        # Add x lands with a distribution set by the mana types
        total_lands = number_of_lands
        for land in mana_types:
            if not total_lands or not mana_types[land][constants.DATA_FIELD_COUNT]:
                continue

            land_count = int(math.ceil(
                (mana_types[land][constants.DATA_FIELD_COUNT] / total_count) * number_of_lands))

            land_count = min(land_count, total_lands)
            total_lands -= land_count

            if land_count:
                card = {constants.DATA_FIELD_COLORS: mana_types[land]["color"],
                        constants.DATA_FIELD_TYPES: constants.CARD_TYPE_LAND,
                        constants.DATA_FIELD_CMC: 0,
                        constants.DATA_FIELD_NAME: land,
                        constants.DATA_FIELD_MANA_COST: mana_types[land]["color"],
                        constants.DATA_FIELD_COUNT: land_count}
                combined_deck.append(card)

    except Exception as error:
        logger.error(error)
    return combined_deck

def build_deck(deck_type, cards, color, metrics, configuration):
    """The function will build a deck list that meets specific criteria"""
    minimum_distribution = deck_type.distribution
    maximum_card_count = deck_type.maximum_card_count
    maximum_deck_size = 40
    cmc_average = deck_type.cmc_average
    recommended_creature_count = deck_type.recommended_creature_count
    deck_list = []
    unused_creature_list = []
    sideboard_list = cards[:]  # Copy by value
    try:
        for card in cards:
            card["results"] = [card[constants.DATA_FIELD_DECK_COLORS][color][constants.DATA_FIELD_GIHWR]]

        # identify a splashable color
        mean, std = metrics.get_metrics(constants.FILTER_OPTION_ALL_DECKS, constants.DATA_FIELD_GIHWR)
        splash_threshold = mean + 2.33 * std
        color += (color_splash(cards, color, splash_threshold, configuration))

        card_colors_sorted = deck_card_search(
            cards, color, [constants.CARD_TYPE_CREATURE], True, True, False)
        card_colors_sorted = sorted(
            card_colors_sorted, key=lambda k: k["results"][0], reverse=True)

        # Identify creatures that fit distribution
        distribution = [0, 0, 0, 0, 0, 0, 0]
        used_count = 0
        used_cmc_combined = 0
        for card in card_colors_sorted:
            index = int(min(card[constants.DATA_FIELD_CMC],
                        len(minimum_distribution) - 1))
            if distribution[index] < minimum_distribution[index]:
                deck_list.append(card)
                sideboard_list.remove(card)
                distribution[index] += 1
                used_count += 1
                used_cmc_combined += card[constants.DATA_FIELD_CMC]
            else:
                unused_creature_list.append(card)

        # Go back and identify remaining creatures that have the highest base rating but don't push average above the threshold
        unused_cmc_combined = cmc_average * recommended_creature_count - used_cmc_combined

        unused_creature_list.sort(key=lambda x: x["results"][0], reverse=True)

        # Identify remaining cards that won't exceed recommeneded CMC average
        cmc_cards, unused_creature_list = card_cmc_search(
            unused_creature_list, 0, 0, unused_cmc_combined, recommended_creature_count - used_count)

        for card in cmc_cards:
            deck_list.append(card)
            sideboard_list.remove(card)

        total_card_count = len(deck_list)

        if len(cmc_cards) == 0:
            for card in unused_creature_list:
                if total_card_count >= recommended_creature_count:
                    break

                deck_list.append(card)
                sideboard_list.remove(card)
                total_card_count += 1

        card_colors_sorted = deck_card_search(sideboard_list, color, [
            constants.CARD_TYPE_CREATURE,
            constants.CARD_TYPE_INSTANT,
            constants.CARD_TYPE_SORCERY,
            constants.CARD_TYPE_ENCHANTMENT,
            constants.CARD_TYPE_ARTIFACT,
            constants.CARD_TYPE_PLANESWALKER], True, True, False)

        card_colors_sorted = sorted(
            card_colors_sorted, key=lambda k: k["results"][0], reverse=True)

        # Add remaining non-land cards
        for card in card_colors_sorted:
            if total_card_count >= maximum_card_count:
                break

            deck_list.append(card)
            sideboard_list.remove(card)
            total_card_count += 1

        # Add in special lands if they have a win rate that is at least 0.33 standard deviations from the mean (C-)
        land_cards = deck_card_search(
            sideboard_list, color, [constants.CARD_TYPE_LAND], True, True, False)
        land_cards = [
            x for x in land_cards if x[constants.DATA_FIELD_NAME] not in constants.BASIC_LANDS]
        land_cards = sorted(
            land_cards, key=lambda k: k["results"][0], reverse=True)
        for card in land_cards:
            if total_card_count >= maximum_deck_size:
                break

            if card["results"][0] >= mean - 0.33 * std:
                deck_list.append(card)
                sideboard_list.remove(card)
                total_card_count += 1

    except Exception as error:
        logger.error(error)
    return deck_list, sideboard_list

def suggest_deck(taken_cards, metrics, configuration):
    """The function will analyze the list of taken cards and produce several viable decks based on specific criteria"""
    colors_max = 5
    maximum_card_count = 22
    sorted_decks = {}
    try:
        deck_types = {"Mid": configuration.card_logic.deck_mid,
                      "Aggro": configuration.card_logic.deck_aggro,
                      "Control": configuration.card_logic.deck_control}
        # Identify the top color combinations
        colors = deck_colors(taken_cards, colors_max, metrics, configuration)
        filtered_colors = []

        colors.pop(constants.FILTER_OPTION_ALL_DECKS, None)

        # Collect color stats and remove colors that don't meet the minimum requirements
        for color in colors:
            creature_count, noncreature_count = deck_color_stats(
                taken_cards, color)
            if ((creature_count >= configuration.card_logic.minimum_creatures) and
               (noncreature_count >= configuration.card_logic.minimum_noncreatures) and
               (creature_count + noncreature_count >= maximum_card_count)):
                filtered_colors.append(color)

        decks = {}
        mean, std = metrics.get_metrics(constants.FILTER_OPTION_ALL_DECKS, constants.DATA_FIELD_GIHWR)
        threshold = mean - 0.33 * std
        for color in filtered_colors:
            for key, value in deck_types.items():
                deck, sideboard_cards = build_deck(
                    value, taken_cards, color, metrics, configuration)
                rating = deck_rating(deck, value, color, threshold)
                if rating >= configuration.card_logic.ratings_threshold:

                    if ((color not in decks) or
                            (color in decks and rating > decks[color]["rating"])):
                        decks[color] = {}
                        decks[color]["deck_cards"] = stack_cards(deck)
                        decks[color]["sideboard_cards"] = stack_cards(
                            sideboard_cards)
                        decks[color]["rating"] = rating
                        decks[color]["type"] = key
                        decks[color]["deck_cards"].extend(mana_base(deck))

        sorted_colors = sorted(
            decks, key=lambda x: decks[x]["rating"], reverse=True)
        for color in sorted_colors:
            sorted_decks[color] = decks[color]
    except Exception as error:
        logger.error(error)

    return sorted_decks
