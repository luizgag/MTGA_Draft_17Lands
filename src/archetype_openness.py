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
    opportunity_cost_decay: float = 0.1
    hmm_transition_decay: float = 0.15
    hmm_emission_scale: float = 1.0
    hmm_openness_factor: float = 2.0
    hmm_pick_ramp: int = 5
    rarity_odds: Dict[str, float] = Field(default_factory=lambda: {
        "common": 0.0899,
        "uncommon": 0.0388,
        "rare": 0.0148,
        "mythic": 0.0055,
        "special": 0.0001,
        "bonus": 0.0001,
    })
    card_weight_threshold: float = 0.4
    absence_enabled: bool = True
    slots_per_rarity: Dict[str, int] = Field(default_factory=lambda: {
        "common": 10, "uncommon": 3, "rare": 1, "mythic": 0,
    })
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


class OpennessTracker:
    """Tracks archetype openness signals during a draft."""

    def __init__(self, config: ArchetypeConfig):
        self.config = config
        self.scoring_method = config.scoring_method
        self.weight_curve = config.weight_curve
        self.pack_weights = config.pack_weights
        self.archetypes = config.archetypes
        self.bayesian_prior = config.bayesian_prior
        self.signals: List[Dict] = []
        self.hmm_log_odds: Dict[str, float] = {arch.name: 0.0 for arch in self.archetypes}
        self.hmm_last_pick: Dict[str, int] = {arch.name: 1 for arch in self.archetypes}
        self.hmm_sum_sq: Dict[str, float] = {arch.name: 0.0 for arch in self.archetypes}
        # bayesian_survival state
        self.bs_log_odds: Dict[str, float] = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_sum_sq: Dict[str, float] = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_last_pick: Dict[str, int] = {arch.name: 1 for arch in self.archetypes}
        self.bs_card_seen: Dict[str, Dict[str, int]] = {arch.name: {} for arch in self.archetypes}
        self.bs_packs_observed: int = 0
        self._bs_card_rarity: Dict[str, str] = {}
        self._bs_card_ata: Dict[str, float] = {}
        # Passed cards tracking state
        self.passed_signals: List[Dict] = []
        # Invert pack weights: swap P1 and P2 weights
        if len(self.pack_weights) >= 2:
            self.passed_pack_weights = [self.pack_weights[1], self.pack_weights[0]] + list(self.pack_weights[2:])
        else:
            self.passed_pack_weights = list(self.pack_weights)

    def record_pack(self, pack_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record positive signals from a pack of cards.

        Positive signal = card is wheeling later than expected (archetype is OPEN).

        Args:
            pack_cards: list of card dicts from the dataset (cards still in pack)
            pick_number: 1-based pick position within the pack (resets each pack)
            pack_number: 0-indexed pack number (0=pack1, 1=pack2, 2=pack3)
        """
        if pick_number <= 1:
            logger.debug(
                "Openness pick %s.%s skipped: pick 1 has no openness signal",
                pack_number + 1,
                pick_number,
            )
            return

        pack_weight = self.pack_weights[pack_number] if pack_number < len(self.pack_weights) else 1.0
        logger.debug(
            "Openness pick %s.%s evaluating %d cards (method=%s, pack_weight=%.3f)",
            pack_number + 1,
            pick_number,
            len(pack_cards),
            self.scoring_method,
            pack_weight,
        )

        signal_count = 0

        for card in pack_cards:
            card_name = card.get(DATA_FIELD_NAME, "")
            deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
            all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
            ata = all_decks.get(DATA_FIELD_ATA, 0.0)
            alsa = all_decks.get(DATA_FIELD_ALSA, 0.0)

            logger.debug(
                "  Card '%s' at pick %s.%s: ATA=%.3f",
                card_name,
                pack_number + 1,
                pick_number,
                ata,
            )

            for archetype in self.archetypes:
                if card_name not in archetype.cards:
                    continue

                card_weight = archetype.cards[card_name]

                if ata == 0.0:
                    logger.debug(
                        "    %s <- %s skipped (missing ATA)",
                        archetype.name,
                        card_name,
                    )
                    continue

                if pick_number <= alsa and self.scoring_method != "hmm_hybrid":
                    logger.debug(
                        "    %s <- %s skipped (pick %.1f <= ATA %.1f)",
                        archetype.name,
                        card_name,
                        pick_number,
                        ata,
                    )
                    continue

                if self.scoring_method == "normalized":
                    pick_weight = self._pick_weight(pick_number, max_picks=14)
                    raw_signal = ((pick_number - ata) / (ata + pick_number)**2) * pick_weight
                    signal = raw_signal * card_weight * pack_weight * 100
                elif self.scoring_method == "bayesian_beta":
                    raw_signal = (pick_number - ata) / (pick_number + ata)
                    signal = raw_signal * card_weight * pack_weight
                elif self.scoring_method == "hmm_hybrid":
                    raw_signal = (pick_number - ata) / (pick_number + ata)
                    emission = self._hmm_emission(card, pick_number, ata, card_weight, pack_weight)
                    self._hmm_update_state(archetype.name, pick_number, emission)
                    signal = emission
                elif self.scoring_method == "bayesian_survival":
                    emission = self._bs_wheeling_emission(card, pick_number, ata, card_weight, pack_weight)
                    self._bs_update_state(archetype.name, pick_number, emission)
                    raw_signal = emission
                    signal = emission
                elif self.scoring_method == "simple_alsa":
                    if pick_number <= 8:
                        raw_signal = (pick_number - alsa) / (alsa + pick_number) 
                    elif pick_number >= 8 and ata <= pick_number:
                        raw_signal = (pick_number - ata) / (ata + pick_number)**2
                    else:
                        continue

                    signal = raw_signal * card_weight * pack_weight * 100
                else:  # simple
                    raw_signal = (pick_number - ata) / (ata + pick_number)**2 
                    signal = raw_signal * card_weight * pack_weight * 100

                signal_count += 1
                logger.debug(
                    "    %s <- %s contributes signal=%.4f (raw=%.4f, card_weight=%.3f, pack_weight=%.3f)",
                    archetype.name,
                    card_name,
                    signal,
                    raw_signal,
                    card_weight,
                    pack_weight,
                )

                self.signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": signal,
                })

        if self.scoring_method == "bayesian_survival":
            self.bs_packs_observed += 1
            for card in pack_cards:
                card_name = card.get(DATA_FIELD_NAME, "")
                # Cache rarity and ATA for absence calculation
                if card_name not in self._bs_card_rarity:
                    self._bs_card_rarity[card_name] = (card.get("rarity", "") or "").lower()
                    deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
                    all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
                    self._bs_card_ata[card_name] = all_decks.get(DATA_FIELD_ATA, 0.0)

                for archetype in self.archetypes:
                    if card_name in archetype.cards:
                        seen = self.bs_card_seen.get(archetype.name, {})
                        seen[card_name] = seen.get(card_name, 0) + 1
                        self.bs_card_seen[archetype.name] = seen

        logger.debug(
            "Openness pick %s.%s complete: %d signals recorded",
            pack_number + 1,
            pick_number,
            signal_count,
        )

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
        if self.scoring_method == "hmm_hybrid":
            return self._scores_hmm_hybrid()
        if self.scoring_method == "bayesian_survival":
            return self._scores_bayesian_survival()
        return self._scores_simple()


    def _hmm_pick_ramp_factor(self, pick_number: int) -> float:
        """Warm-up ramp: reduces early-pick emissions, full weight after hmm_pick_ramp picks."""
        ramp_picks = max(2, self.config.hmm_pick_ramp)
        return min(1.0, (pick_number - 1) / (ramp_picks - 1))

    def _hmm_emission(self, card: Dict, pick_number: int, ata: float,
                      card_weight: float, pack_weight: float) -> float:
        """Emission contribution to log-odds from one visible card.

        Uses geometric survival model: each drafter has hazard rate h = 1/ATA.
        Under the 'open' hypothesis, effective ATA = ATA * F (openness factor),
        so cards survive longer because fewer neighbors draft the archetype.

        Log Bayes factor = (p-1) * [log(1 - 1/(a*F)) - log(1 - 1/a)]

        This is always >= 0 when F >= 1: every observation weakly supports 'open'.
        Magnitude increases with pick position and decreases with ATA.
        """
        # Clamp ATA to minimum 1.5 to avoid log(0) when a <= 1
        a = max(1.5, ata)
        F = max(1.0, self.config.hmm_openness_factor)
        p = pick_number

        # Geometric survival log Bayes factor
        log_bf = (p - 1) * (math.log(1.0 - 1.0 / (a * F)) - math.log(1.0 - 1.0 / a))

        # Rarity reliability weight: rarer cards provide less reliable
        # table-behavior signals because fewer copies exist in the draft pool.
        common_odds = self.config.rarity_odds.get("common", 0.0899)
        card_rarity = (card.get("rarity", "") or "").lower()
        card_odds = self.config.rarity_odds.get(card_rarity, common_odds)
        if common_odds > 0:
            rarity_weight = math.sqrt(card_odds / common_odds)
        else:
            rarity_weight = 1.0

        scale = self.config.hmm_emission_scale
        ramp = self._hmm_pick_ramp_factor(pick_number)
        return log_bf * card_weight * pack_weight * rarity_weight * scale * ramp

    def _hmm_update_state(self, archetype_name: str, pick_number: int, emission: float) -> None:
        """One-step HMM-like state update in log-odds space."""
        prev_log_odds = self.hmm_log_odds.get(archetype_name, 0.0)
        last_pick = self.hmm_last_pick.get(archetype_name, 1)
        gap = max(0, pick_number - last_pick)

        decay = max(0.0, 1.0 - self.config.hmm_transition_decay) ** gap
        updated = (prev_log_odds * decay) + emission

        self.hmm_log_odds[archetype_name] = updated
        self.hmm_last_pick[archetype_name] = pick_number

        # Track decayed sum of squared emissions for variance estimation
        prev_sum_sq = self.hmm_sum_sq.get(archetype_name, 0.0)
        self.hmm_sum_sq[archetype_name] = (prev_sum_sq * (decay ** 2)) + (emission ** 2)

    def _bs_wheeling_emission(self, card: Dict, pick_number: int, ata: float,
                              card_weight: float, pack_weight: float) -> float:
        """Signal 1: Log Bayes factor for a card surviving to pick p.

        lambda = (p-1) * log(q_open / q_closed)
        where q_open = 1 - 1/(a*F), q_closed = 1 - 1/a.
        """
        a = max(1.5, ata)
        F = max(1.0, self.config.hmm_openness_factor)
        p = pick_number

        q_open = 1.0 - 1.0 / (a * F)
        q_closed = 1.0 - 1.0 / a
        log_bf = (p - 1) * math.log(q_open / q_closed)

        common_odds = self.config.rarity_odds.get("common", 0.0899)
        card_rarity = (card.get("rarity", "") or "").lower()
        card_odds = self.config.rarity_odds.get(card_rarity, common_odds)
        rarity_weight = math.sqrt(card_odds / common_odds) if common_odds > 0 else 1.0

        scale = self.config.hmm_emission_scale
        ramp = self._hmm_pick_ramp_factor(pick_number)
        return log_bf * card_weight * pack_weight * rarity_weight * scale * ramp

    def _bs_update_state(self, archetype_name: str, pick_number: int, emission: float) -> None:
        """Update bayesian_survival log-odds state with decay."""
        prev_log_odds = self.bs_log_odds.get(archetype_name, 0.0)
        last_pick = self.bs_last_pick.get(archetype_name, 1)
        gap = max(0, pick_number - last_pick)

        decay = max(0.0, 1.0 - self.config.hmm_transition_decay) ** gap
        self.bs_log_odds[archetype_name] = (prev_log_odds * decay) + emission
        self.bs_last_pick[archetype_name] = pick_number

        prev_sum_sq = self.bs_sum_sq.get(archetype_name, 0.0)
        self.bs_sum_sq[archetype_name] = (prev_sum_sq * (decay ** 2)) + (emission ** 2)

    def _bs_absence_signal(self, archetype: Archetype) -> float:
        """Signal 3: Draft-wide absence signal for all cards in an archetype.

        For each card, computes:
        lambda = k * log(see_open/see_closed) + (N - k) * log((1 - see_open)/(1 - see_closed))
        where see_H = r * q_H^(p_avg - 1).
        """
        if not self.config.absence_enabled or self.bs_packs_observed == 0:
            return 0.0

        N = self.bs_packs_observed
        p_avg = 7.5  # approximate midpoint of 1-14
        F = max(1.0, self.config.hmm_openness_factor)
        total_signal = 0.0

        for card_name, card_weight in archetype.cards.items():
            # Use cached rarity/ATA, with defaults for never-seen cards
            card_rarity = self._bs_card_rarity.get(card_name, "common")
            card_ata = self._bs_card_ata.get(card_name, 5.0)

            r_odds = self.config.rarity_odds.get(card_rarity, 0.0899)
            slots = self.config.slots_per_rarity.get(card_rarity, 0)
            r = r_odds * slots

            if r <= 0 or card_ata == 0.0:
                continue

            a = max(1.5, card_ata)
            q_open = 1.0 - 1.0 / (a * F)
            q_closed = 1.0 - 1.0 / a

            see_open = r * (q_open ** (p_avg - 1))
            see_closed = r * (q_closed ** (p_avg - 1))

            # Clamp to avoid log(0)
            see_open = min(max(see_open, 1e-10), 1.0 - 1e-10)
            see_closed = min(max(see_closed, 1e-10), 1.0 - 1e-10)

            k = self.bs_card_seen.get(archetype.name, {}).get(card_name, 0)

            signal = (k * math.log(see_open / see_closed)
                      + (N - k) * math.log((1 - see_open) / (1 - see_closed)))
            total_signal += signal * card_weight

        return total_signal

    def _scores_bayesian_survival(self) -> Dict[str, dict]:
        """Bayesian survival scoring — log-odds with absence signal and credible interval."""
        scores = {}
        for arch in self.archetypes:
            log_odds = self.bs_log_odds.get(arch.name, 0.0)

            # Add absence signal
            absence = self._bs_absence_signal(arch)
            total_log_odds = log_odds + absence

            # Variance estimation
            sum_sq = self.bs_sum_sq.get(arch.name, 0.0)
            if sum_sq > 0:
                sigma = math.sqrt(sum_sq)
                interval = (total_log_odds - 1.96 * sigma, total_log_odds + 1.96 * sigma)
            else:
                interval = None

            scores[arch.name] = {
                "score": total_log_odds,
                "confidence": self._confidence_level(arch.name),
                "interval": interval,
            }
        return scores

    def _bs_missing_emission(self, card: Dict, pick_number: int, ata: float,
                             card_weight: float, pack_weight: float) -> float:
        """Signal 2: Log Bayes factor for a missing card (taken before pick p).

        lambda = log((1 - S_open) / (1 - S_closed))
        where S_H = q_H^(p-1). Always <= 0.
        """
        a = max(1.5, ata)
        F = max(1.0, self.config.hmm_openness_factor)
        p = pick_number

        q_open = 1.0 - 1.0 / (a * F)
        q_closed = 1.0 - 1.0 / a

        S_open = q_open ** (p - 1)
        S_closed = q_closed ** (p - 1)

        taken_open = max(1e-10, 1.0 - S_open)
        taken_closed = max(1e-10, 1.0 - S_closed)
        log_bf = math.log(taken_open / taken_closed)

        common_odds = self.config.rarity_odds.get("common", 0.0899)
        card_rarity = (card.get("rarity", "") or "").lower()
        card_odds = self.config.rarity_odds.get(card_rarity, common_odds)
        rarity_weight = math.sqrt(card_odds / common_odds) if common_odds > 0 else 1.0

        scale = self.config.hmm_emission_scale
        ramp = self._hmm_pick_ramp_factor(pick_number)
        return log_bf * card_weight * pack_weight * rarity_weight * scale * ramp

    def _simple_alsa_missing_emission(self, ata: float, card_weight: float,
                                      pack_weight: float, pick_number: int) -> float:
        """Negative signal for a missing card in simple_alsa scoring.

        Cards taken by others indicate archetype competition.
        Lower ATA (stronger cards) produce stronger negative signals
        because early picks represent bigger archetype commitment.
        """
        raw_signal = -(1.0 / (ata + pick_number))
        return raw_signal * card_weight * pack_weight * 100

    def record_missing(self, missing_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record negative signals from missing cards.

        Active for bayesian_survival and simple_alsa scoring methods.

        Args:
            missing_cards: list of card dicts that were in original pack but are now gone
            pick_number: 1-based pick position within the pack
            pack_number: 0-indexed pack number
        """
        if self.scoring_method not in ("bayesian_survival", "simple_alsa"):
            return

        pack_weight = self.pack_weights[pack_number] if pack_number < len(self.pack_weights) else 1.0

        for card in missing_cards:
            card_name = card.get(DATA_FIELD_NAME, "")
            deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
            all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
            ata = all_decks.get(DATA_FIELD_ATA, 0.0)

            if ata == 0.0:
                continue

            for archetype in self.archetypes:
                if card_name not in archetype.cards:
                    continue

                card_weight = archetype.cards[card_name]

                if self.scoring_method == "simple_alsa":
                    emission = self._simple_alsa_missing_emission(ata, card_weight, pack_weight, pick_number)
                else:
                    emission = self._bs_missing_emission(card, pick_number, ata, card_weight, pack_weight)
                    self._bs_update_state(archetype.name, pick_number, emission)

                self.signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": emission,
                })

    def record_passed(self, passed_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record signals from cards the user passed (didn't pick).

        Uses formula: -(1/(ata + pick_number)) * card_weight * passed_pack_weight * 100

        Args:
            passed_cards: list of card dicts the user chose not to pick
            pick_number: 1-based pick position within the pack
            pack_number: 0-indexed pack number
        """
        pack_weight = self.passed_pack_weights[pack_number] if pack_number < len(self.passed_pack_weights) else 1.0

        for card in passed_cards:
            card_name = card.get(DATA_FIELD_NAME, "")
            deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
            all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
            ata = all_decks.get(DATA_FIELD_ATA, 0.0)

            if ata == 0.0:
                continue

            for archetype in self.archetypes:
                if card_name not in archetype.cards:
                    continue

                card_weight = archetype.cards[card_name]
                raw_signal = -(1.0 / (ata + pick_number))
                signal = raw_signal * card_weight * pack_weight * 100

                self.passed_signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": signal,
                })

    def get_passed_scores(self) -> Dict[str, dict]:
        """Get aggregated passed-cards scores for all archetypes.

        Returns dict of {archetype_name: {"score": float}}.
        Always negative (passing cards is always a cost).
        """
        scores = {}
        for arch in self.archetypes:
            total = sum(s["signal"] for s in self.passed_signals if s["archetype"] == arch.name)
            scores[arch.name] = {"score": total}
        return scores

    def get_top_passed(self, archetype_name: str, count: int = 3) -> List[Dict]:
        """Get top N passed cards by absolute signal for an archetype."""
        arch_signals = [s for s in self.passed_signals if s["archetype"] == archetype_name]
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

    def _scores_hmm_hybrid(self) -> Dict[str, dict]:
        """HMM-inspired hybrid score returned as posterior P(open).

        Also computes a 95% approximate credible interval via the delta method:
        sigma_logodds = sqrt(sum_sq_emissions), then propagate through sigmoid
        using d/dx sigmoid(x) = sigmoid(x)*(1 - sigmoid(x)).
        """
        scores = {}
        for arch in self.archetypes:
            log_odds = self.hmm_log_odds.get(arch.name, 0.0)
            p_open = 1.0 / (1.0 + math.exp(-log_odds))

            # Variance estimation via decayed sum-of-squared emissions
            sum_sq = self.hmm_sum_sq.get(arch.name, 0.0)
            if sum_sq > 0:
                sigma_logodds = math.sqrt(sum_sq)
                # Delta method: sigma_p ≈ p*(1-p) * sigma_logodds
                sigma_p = p_open * (1.0 - p_open) * sigma_logodds
                interval_low = max(0.0, p_open - 1.96 * sigma_p)
                interval_high = min(1.0, p_open + 1.96 * sigma_p)
                interval = (interval_low, interval_high)
            else:
                interval = None

            scores[arch.name] = {
                "score": p_open,
                "confidence": self._confidence_level(arch.name),
                "interval": interval,
            }
        return scores

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
        self.hmm_log_odds = {arch.name: 0.0 for arch in self.archetypes}
        self.hmm_last_pick = {arch.name: 1 for arch in self.archetypes}
        self.hmm_sum_sq = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_log_odds = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_sum_sq = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_last_pick = {arch.name: 1 for arch in self.archetypes}
        self.bs_card_seen = {arch.name: {} for arch in self.archetypes}
        self.bs_packs_observed = 0
        self._bs_card_rarity = {}
        self._bs_card_ata = {}
        self.passed_signals.clear()
