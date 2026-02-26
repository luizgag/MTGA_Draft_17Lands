"""Card filtering functions"""
from src import constants
from src.logger import create_logger
from src.card_logic.utils import get_card_colors

logger = create_logger()

def deck_card_search(deck, search_colors, card_types, include_types, include_colorless, include_partial):
    """This function retrieves a subset of cards that meet certain criteria (type, color, etc.)"""
    card_color_sorted = {}
    main_color = ""
    combined_cards = []
    for card in deck:
        try:
            colors = list(get_card_colors(
                card[constants.DATA_FIELD_MANA_COST]).keys())

            if constants.CARD_TYPE_LAND in card[constants.DATA_FIELD_TYPES]:
                colors = card[constants.DATA_FIELD_COLORS]

            if colors and (set(colors) <= set(search_colors)):
                main_color = colors[0]

                if ((include_types and any(x in card[constants.DATA_FIELD_TYPES] for x in card_types)) or
                   (not include_types and not any(x in card[constants.DATA_FIELD_TYPES] for x in card_types))):

                    if main_color not in card_color_sorted:
                        card_color_sorted[main_color] = []

                    card_color_sorted[main_color].append(card)

            elif set(search_colors).intersection(colors) and include_partial:
                for color in colors:
                    if ((include_types and any(x in card[constants.DATA_FIELD_TYPES] for x in card_types)) or
                       (not include_types and not any(x in card[constants.DATA_FIELD_TYPES] for x in card_types))):

                        if color not in card_color_sorted:
                            card_color_sorted[color] = []

                        card_color_sorted[color].append(card)

            if not colors and include_colorless:

                if ((include_types and any(x in card[constants.DATA_FIELD_TYPES] for x in card_types)) or
                   (not include_types and not any(x in card[constants.DATA_FIELD_TYPES] for x in card_types))):

                    combined_cards.append(card)
        except Exception as error:
            logger.error(error)

    for key, value in card_color_sorted.items():
        if key in search_colors:
            combined_cards.extend(value)

    return combined_cards
