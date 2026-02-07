"""Archetype openness detection for draft signal analysis."""

import json
import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from src.logger import create_logger

logger = create_logger()


class Archetype(BaseModel):
    """A single draft archetype with card weights."""
    name: str
    color_pair: Optional[str] = None
    auto_weights: bool = True
    cards: Dict[str, float] = Field(default_factory=dict)


class ArchetypeConfig(BaseModel):
    """Full archetype configuration for a set."""
    set_code: str
    detection_threshold: float = 5.0
    scoring_method: str = "simple"
    pack_weights: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    archetypes: List[Archetype] = Field(default_factory=list)


def load_archetype_config(file_path: str) -> Optional[ArchetypeConfig]:
    """Load archetype config from JSON file. Returns None if file missing or invalid."""
    try:
        with open(file_path, "r", encoding="utf8", errors="replace") as f:
            data = json.loads(f.read())
        return ArchetypeConfig.model_validate(data)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as error:
        logger.error("Failed to load archetype config: %s", error)
        return None


def save_archetype_config(config: ArchetypeConfig, file_path: str) -> bool:
    """Save archetype config to JSON file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf8", errors="replace") as f:
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=4)
        return True
    except (OSError, TypeError) as error:
        logger.error("Failed to save archetype config: %s", error)
        return False


from src.constants import (
    DATA_FIELD_NAME,
    DATA_FIELD_NGP,
    DATA_FIELD_DECK_COLORS,
    DECK_COLORS,
    FILTER_OPTION_ALL_DECKS,
    COLOR_NAMES_DICT,
)


def _get_all_card_ratings(dataset) -> Dict:
    """Access the internal card_ratings dict from a Dataset."""
    return dataset._dataset.get("card_ratings", {}) if dataset._dataset else {}


def calculate_card_weights(dataset, color_pair: str) -> Dict[str, float]:
    """Calculate card weights for a color pair: ngp(color_pair) / ngp(All Decks)."""
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
            if weight > 0.0:
                weights[card[DATA_FIELD_NAME]] = weight

    return weights


def auto_detect_archetypes(dataset, threshold_percent: float = 5.0) -> List[Archetype]:
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
            cards = calculate_card_weights(dataset, color_pair)
            archetypes.append(Archetype(
                name=name,
                color_pair=color_pair,
                auto_weights=True,
                cards=cards,
            ))

    return archetypes
