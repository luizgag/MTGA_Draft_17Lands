"""Card logic package"""

from src.card_logic.utils import (
    get_card_colors,
    row_color_tag,
    field_process_sort,
    format_tier_results,
    stack_cards,
    copy_deck,
    sort_cards_win_rate,
    ratings_limits
)

from src.card_logic.card_filtering import deck_card_search

from src.card_logic.deck_metrics import (
    DeckMetrics,
    get_deck_metrics,
    deck_color_stats
)

from src.card_logic.deck_colors import (
    calculate_color_affinity,
    calculate_color_rating,
    calculate_curve_factor,
    deck_colors,
    auto_colors,
    filter_options
)

from src.card_logic.deck_builder import (
    card_cmc_search,
    deck_rating,
    color_splash,
    mana_base,
    build_deck,
    suggest_deck
)

from src.card_logic.card_result import CardResult

__all__ = [
    "get_card_colors",
    "row_color_tag",
    "field_process_sort",
    "format_tier_results",
    "stack_cards",
    "copy_deck",
    "sort_cards_win_rate",
    "ratings_limits",
    "deck_card_search",
    "DeckMetrics",
    "get_deck_metrics",
    "deck_color_stats",
    "calculate_color_affinity",
    "calculate_color_rating",
    "calculate_curve_factor",
    "deck_colors",
    "auto_colors",
    "filter_options",
    "card_cmc_search",
    "deck_rating",
    "color_splash",
    "mana_base",
    "build_deck",
    "suggest_deck",
    "CardResult"
]
