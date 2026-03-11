from typing import Dict, List
from src.archetype_openness.models import Archetype
from src.constants import (
    DATA_FIELD_ALSA,
    DATA_FIELD_NAME,
    DATA_FIELD_ATA,
    DATA_FIELD_NGP,
    DATA_FIELD_DECK_COLORS,
    DECK_COLORS,
    FILTER_OPTION_ALL_DECKS,
    COLOR_NAMES_DICT,
)

def _get_all_card_ratings(dataset) -> Dict:
    """Access the internal card_ratings dict from a Dataset."""
    return dataset._dataset.get("card_ratings", {}) if dataset._dataset else {}


def calculate_card_weights(dataset, color_pair: str, threshold: float = 0.0) -> Dict[str, float]:
    """Calculate card weights for a color pair: ngp(color_pair) / ngp(All Decks).

    Args:
        dataset: Dataset instance with card ratings
        color_pair: color pair string (e.g. "BG")
        threshold: minimum weight to include (cards below this are filtered out)
    """
    card_ratings = _get_all_card_ratings(dataset)
    weights = {}

    for card_id, card in card_ratings.items():
        deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
        all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
        color_data = deck_colors.get(color_pair, {})

        total_ngp = all_decks.get(DATA_FIELD_NGP, 0)
        color_ngp = color_data.get(DATA_FIELD_NGP, 0)

        if total_ngp > 0 and color_ngp > 0:
            weight = round(color_ngp / total_ngp, 4)
            if weight > 0.0 and weight >= threshold:
                weights[card[DATA_FIELD_NAME]] = weight

    return weights


def auto_detect_archetypes(dataset, threshold_percent: float = 5.0,
                           card_weight_threshold: float = 0.0) -> List[Archetype]:
    """Detect viable archetypes by finding color pairs with games above threshold."""
    card_ratings = _get_all_card_ratings(dataset)
    if not card_ratings:
        return []

    color_totals = {}
    overall_total = 0

    for card_id, card in card_ratings.items():
        deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
        all_decks_ngp = deck_colors.get(FILTER_OPTION_ALL_DECKS, {}).get(DATA_FIELD_NGP, 0)
        overall_total += all_decks_ngp

        for color_pair in DECK_COLORS:
            if color_pair == FILTER_OPTION_ALL_DECKS:
                continue
            color_data = deck_colors.get(color_pair, {})
            ngp = color_data.get(DATA_FIELD_NGP, 0)
            color_totals[color_pair] = color_totals.get(color_pair, 0) + ngp

    if overall_total == 0:
        return []

    archetypes = []
    for color_pair, total_ngp in color_totals.items():
        percentage = (total_ngp / overall_total) * 100
        if percentage >= threshold_percent:
            name = COLOR_NAMES_DICT.get(color_pair, color_pair)
            cards = calculate_card_weights(dataset, color_pair, threshold=card_weight_threshold)
            archetypes.append(Archetype(
                name=name,
                color_pair=color_pair,
                auto_weights=True,
                cards=cards,
            ))

    return archetypes
