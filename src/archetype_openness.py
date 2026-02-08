"""Archetype openness detection for draft signal analysis."""

import json
import os
import math
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
    weight_curve: str = "linear"
    pack_weights: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    bayesian_prior: float = 1.0
    card_weight_threshold: float = 0.4
    archetypes: List[Archetype] = Field(default_factory=list)


def load_archetype_config(file_path: str) -> Optional[ArchetypeConfig]:
    """Load archetype config from JSON file. Returns None if file missing or invalid."""
    try:
        with open(file_path, "r", encoding="utf8", errors="replace") as f:
            data = json.loads(f.read())
        return ArchetypeConfig.model_validate(data)
    except FileNotFoundError:
        logger.info("No archetype config found at %s, will use defaults", file_path)
        return None
    except (json.JSONDecodeError, Exception) as error:
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


class OpennessTracker:
    """Tracks archetype openness signals during a draft."""

    def __init__(self, config: ArchetypeConfig):
        self.scoring_method = config.scoring_method
        self.weight_curve = config.weight_curve
        self.pack_weights = config.pack_weights
        self.archetypes = config.archetypes
        self.bayesian_prior = config.bayesian_prior
        self.signals: List[Dict] = []

    def record_pack(self, pack_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record signals from a pack of cards.

        Positive signal = card is wheeling later than expected (archetype is OPEN).
        Negative signal = card was taken earlier than expected (archetype is CLOSED).

        Args:
            pack_cards: list of card dicts from the dataset
            pick_number: 1-based pick position within the pack (resets each pack)
            pack_number: 0-indexed pack number (0=pack1, 1=pack2, 2=pack3)
        """
        if pick_number <= 1:
            return

        pack_weight = self.pack_weights[pack_number] if pack_number < len(self.pack_weights) else 1.0

        for card in pack_cards:
            card_name = card.get(DATA_FIELD_NAME, "")
            deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
            all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
            ata = all_decks.get(DATA_FIELD_ATA, 0.0)

            for archetype in self.archetypes:
                if card_name not in archetype.cards:
                    continue

                card_weight = archetype.cards[card_name]

                if self.scoring_method == "normalized":
                    if ata == 0.0:
                        continue
                    pick_weight = self._pick_weight(pick_number, max_picks=14)
                    raw_signal = ((pick_number - ata) / ata) * pick_weight
                else:
                    if ata == 0.0:
                        continue
                    raw_signal = (pick_number - ata) / ata

                signal = raw_signal * card_weight * pack_weight

                self.signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": signal,
                })

    def _pick_weight(self, pick_number: int, max_picks: int = 14) -> float:
        """Weight from 0.0 (pick 1) to 1.0 (final pick), shaped by weight_curve."""
        if max_picks <= 1:
            return 1.0
        t = max(0.0, (pick_number - 1) / (max_picks - 1))
        if self.weight_curve == "sqrt":
            return t ** 0.5
        elif self.weight_curve == "squared":
            return t ** 2
        else:  # "linear"
            return t

    def _confidence_level(self, archetype_name: str) -> str:
        """Determine confidence level based on signal count for an archetype."""
        count = sum(1 for s in self.signals if s["archetype"] == archetype_name)
        if count == 0:
            return "none"
        elif count < 5:
            return "low"
        elif count < 15:
            return "medium"
        else:
            return "high"

    def get_scores(self) -> Dict[str, dict]:
        """Get aggregated openness scores for all archetypes.

        Positive score = archetype is OPEN (cards wheeling later than ATA).
        Negative score = archetype is CLOSED (cards taken earlier than ATA).

        Returns dict of {archetype_name: {"score": float, "confidence": str, "interval": tuple|None}}.
        Archetypes with no signals return score 0.0, confidence "none".
        """
        if self.scoring_method == "bayesian_beta":
            return self._scores_bayesian_beta()
        return self._scores_simple()

    def _scores_simple(self) -> Dict[str, dict]:
        """Simple/normalized scoring — sum of signals, no credible interval."""
        scores = {}
        for arch in self.archetypes:
            total = sum(s["signal"] for s in self.signals if s["archetype"] == arch.name)
            scores[arch.name] = {
                "score": total,
                "confidence": self._confidence_level(arch.name),
                "interval": None,
            }
        return scores

    def _scores_bayesian_beta(self) -> Dict[str, dict]:
        """Bayesian Beta scoring — P(open) as posterior mean with credible interval.

        For each archetype, signals are classified as positive (card seen later than ATA,
        archetype is open) or negative (card seen earlier than ATA, archetype is closed).
        Signal magnitude is weighted by card_weight (archetype affinity) and pack_weight,
        preserving the existing weight system.

        Returns {name: {"score": P(open), "confidence": str, "interval": (low, high)}}.
        """
        prior = self.bayesian_prior
        scores = {}

        for arch in self.archetypes:
            alpha = prior
            beta_param = prior

            for sig in self.signals:
                if sig["archetype"] != arch.name:
                    continue
                # Signal already incorporates card_weight and pack_weight
                # from record_pack: signal = raw * card_weight * pack_weight
                magnitude = abs(sig["signal"])
                if sig["signal"] > 0:
                    alpha += magnitude
                elif sig["signal"] < 0:
                    beta_param += magnitude

            total = alpha + beta_param
            p_open = alpha / total if total > 0 else 0.5

            # 95% credible interval approximation using Normal approximation to Beta
            variance = (alpha * beta_param) / (total * total * (total + 1))
            stderr = math.sqrt(variance) if variance > 0 else 0.0
            interval_low = max(0.0, p_open - 1.96 * stderr)
            interval_high = min(1.0, p_open + 1.96 * stderr)

            scores[arch.name] = {
                "score": p_open,
                "confidence": self._confidence_level(arch.name),
                "interval": (interval_low, interval_high),
            }

        return scores

    def get_top_contributors(self, archetype_name: str, count: int = 3) -> List[Dict]:
        """Get the top N contributing signals for an archetype, sorted by absolute signal.

        Returns list of dicts: [{"card_name", "pick_number", "ata", "signal"}, ...]
        """
        arch_signals = [s for s in self.signals if s["archetype"] == archetype_name]
        arch_signals.sort(key=lambda s: abs(s["signal"]), reverse=True)
        return [
            {
                "card_name": s["card_name"],
                "pick_number": s["pick_number"],
                "ata": s["ata"],
                "signal": s["signal"],
            }
            for s in arch_signals[:count]
        ]

    def reset(self) -> None:
        """Clear all accumulated signals."""
        self.signals.clear()
