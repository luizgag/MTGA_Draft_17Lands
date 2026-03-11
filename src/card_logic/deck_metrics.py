"""Deck metrics and statistics"""
from dataclasses import dataclass, field
from src import constants
from src.logger import create_logger
from src.card_logic.card_filtering import deck_card_search

logger = create_logger()

@dataclass
class DeckMetrics:
    cmc_average: float = 0.0
    creature_count: int = 0
    noncreature_count: int = 0
    total_cards: int = 0
    total_non_land_cards: int = 0
    distribution_creatures: list = field(
        default_factory=lambda: [0, 0, 0, 0, 0, 0, 0])
    distribution_noncreatures: list = field(
        default_factory=lambda: [0, 0, 0, 0, 0, 0, 0])
    distribution_all: list = field(
        default_factory=lambda: [0, 0, 0, 0, 0, 0, 0])

def get_deck_metrics(deck):
    """This function determines the total CMC, count, and distribution of a collection of cards"""
    metrics = DeckMetrics()
    cmc_total = 0
    try:

        metrics.total_cards = len(deck)

        for card in deck:
            if any(x in [constants.CARD_TYPE_CREATURE]
                   for x in card[constants.DATA_FIELD_TYPES]):
                metrics.creature_count += 1
                metrics.total_non_land_cards += 1
                cmc_total += card[constants.DATA_FIELD_CMC]

                index = int(
                    min(card[constants.DATA_FIELD_CMC],
                        len(metrics.distribution_creatures) - 1))
                metrics.distribution_creatures[index] += 1
            else:
                if constants.CARD_TYPE_LAND not in card[constants.DATA_FIELD_TYPES]:
                    cmc_total += card[constants.DATA_FIELD_CMC]
                    metrics.total_non_land_cards += 1
                    index = int(
                        min(card[constants.DATA_FIELD_CMC],
                            len(metrics.distribution_noncreatures) - 1))
                    metrics.distribution_noncreatures[index] += 1
                metrics.noncreature_count += 1

            index = int(
                min(card[constants.DATA_FIELD_CMC],
                    len(metrics.distribution_all) - 1))
            metrics.distribution_all[index] += 1

        metrics.cmc_average = (cmc_total / metrics.total_non_land_cards
                               if metrics.total_non_land_cards
                               else 0.0)

    except Exception as error:
        logger.error(error)

    return metrics

def deck_color_stats(deck, color):
    """The function will identify the number of creature and noncreature cards in a collection of cards"""
    creature_count = 0
    noncreature_count = 0

    try:
        creature_cards = deck_card_search(
            deck, color, [constants.CARD_TYPE_CREATURE], True, True, False)
        noncreature_cards = deck_card_search(
            deck, color, [constants.CARD_TYPE_CREATURE], False, True, False)
        noncreature_cards = deck_card_search(
            noncreature_cards, color,
            [constants.CARD_TYPE_INSTANT,
             constants.CARD_TYPE_SORCERY,
             constants.CARD_TYPE_ARTIFACT,
             constants.CARD_TYPE_ENCHANTMENT,
             constants.CARD_TYPE_PLANESWALKER], True, True, False)

        creature_count = len(creature_cards)
        noncreature_count = len(noncreature_cards)

    except Exception as error:
        logger.error(error)

    return creature_count, noncreature_count
