# Bayesian Survival Openness Method

**Date**: 2026-02-13
**Status**: Design approved

## Problem

The current openness methods work on a single signal type: cards wheeling past their ATA. They ignore two sources of information that are available during a draft:

1. **Missing cards** (picks 9+): When a pack wheels back and a card is gone, someone picked it. High-ATA cards disappearing is a signal the archetype is being drafted.
2. **Draft-wide absence**: A common card that should appear ~1.5 times across 24 packs but never does suggests someone is snapping it up.

## Approach: Unified Log-Odds Framework

All three signal types are instances of the same Bayesian hypothesis test using a geometric survival model. Under H_open, archetype cards have stretched ATA (survive longer). Under H_closed, they have baseline ATA.

Each observation produces a log Bayes factor. These add together in log-odds space because observations are conditionally independent given the hypothesis.

### Core definitions

```
a = max(1.5, ATA)             # card's average taken at (clamped)
F = openness_factor            # config parameter (default 2.0)
q_open   = 1 - 1/(a * F)      # per-pick survival under open
q_closed = 1 - 1/a             # per-pick survival under closed
```

### Signal 1: Wheeling (card present at pick p)

**Gated**: Only emits when `pick > ATA`.

```
lambda_1 = (p - 1) * log(q_open / q_closed)
```

Always >= 0. Card survived past ATA -> supports "open".

### Signal 2: Missing card (card gone at wheel pick p >= 9)

**Always emits** (no gate). The card was in the original pack but is missing when the pack returns.

```
S_open   = q_open^(p-1)
S_closed = q_closed^(p-1)
lambda_2 = log((1 - S_open) / (1 - S_closed))
```

Always <= 0. Card was taken -> supports "closed". Strength depends on ATA:
- ATA=10, missing at pick 9, F=2: lambda = -0.53 (strong closed signal)
- ATA=2, missing at pick 9, F=2: lambda = -0.10 (weak, expected)

### Signal 3: Draft-wide absence (cumulative)

For a card with rarity probability `r = rarity_odds[rarity] * slots_for_rarity[rarity]`, observed `k` times across `N` packs:

```
p_avg = average pick position when we see packs (approx 7.5)
see_open   = r * q_open^(p_avg - 1)
see_closed = r * q_closed^(p_avg - 1)
lambda_3 = k * log(see_open/see_closed) + (N - k) * log((1 - see_open)/(1 - see_closed))
```

When k=0: negative (supports "closed"). Primarily useful for commons (~1.5 expected copies per draft). Negligible for rares/mythics.

### Weight chain (same as hmm_hybrid)

```
lambda_effective = lambda_raw * w_card * w_pack * w_rarity * w_ramp * scale
```

### State accumulation with decay

```
gap = pick - last_pick
decay = (1 - transition_decay)^gap
log_odds = log_odds * decay + lambda_effective
sum_sq = sum_sq * decay^2 + lambda_effective^2
```

## State per archetype

```python
log_odds: float = 0.0
sum_sq: float = 0.0
last_pick: int = 1
signal_count: int = 0
card_seen_counts: Dict[str, int] = {}  # for absence tracking
packs_observed: int = 0
```

## Config parameters

Reuses existing HMM parameters. New additions:

```python
absence_enabled: bool = True
slots_per_rarity: Dict[str, int] = {
    "common": 10, "uncommon": 3, "rare": 1, "mythic": 0
}
```

Method name: `"bayesian_survival"` (5th scoring_method option).

## Integration points

1. **record_pack()** (existing call): Generates Signal 1 for archetype cards present. Also increments card_seen_counts and packs_observed.

2. **record_missing()** (new call): Called at wheel picks (9+). Generates Signal 2 for each archetype card that was in the original pack but is now gone. Data comes from `retrieve_current_missing_cards()` which already exists on both scanners.

3. **Absence signals**: Computed inside `get_scores()` from accumulated card_seen_counts. No separate entry point.

4. **Hindsight replay**: Replay missing cards from pick history entries (they store `initial_pack_cards` and `picked_cards_in_pack`).

## Output

Log-odds per archetype. UI mapping:
- log_odds > 0.5: green (open)
- log_odds < -0.5: red (closed)
- in between: gray (uncertain)

Credible intervals via delta method on sigmoid(log_odds).

## Testing

- Signal 1: gate at pick > ATA, formula verification, scaling with pick number
- Signal 2: high-ATA missing = strong negative, low-ATA missing = weak, formula verification
- Signal 3: common never seen = negative, rare never seen = near-zero
- Integration: full draft sim, open/closed scenarios, decay, reset
- Edge cases: ATA clamp, empty packs, zero rarity_odds
