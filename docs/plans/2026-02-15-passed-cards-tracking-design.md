# Passed Cards Tracking Design

## Problem

During a draft, the user passes cards to opponents but has no visibility into the cumulative "damage" per archetype. Knowing which strong archetype cards you've been feeding to neighbors helps make informed decisions about contested lanes.

## Solution

Add a "Passed Cards" score to the Archetype Openness panel, displayed as amber bars on the right side (pointing left). This is a separate, informational score — not mixed into the openness signal.

## Data Model (`archetype_openness.py`)

### New fields on `OpennessTracker`

- `passed_signals: List[Dict]` — same shape as `signals` (`archetype`, `card_name`, `pick_number`, `ata`, `signal`)
- `passed_pack_weights: List[float]` — inverted from `pack_weights` (e.g., `[1.0, 0.66, 1.0]` becomes `[0.66, 1.0, 0.66]`)

Inversion logic: swap weights at indices 0 and 1. Pack 2 (index 1) feeds the right neighbor who feeds you in P1/P3, so it gets higher weight for passed-cards scoring.

### New methods

**`record_passed(passed_cards, pick_number, pack_number)`**
- For each card, for each archetype where card has a weight:
  - `raw_signal = -(1.0 / (ata + pick_number))`
  - `signal = raw_signal * card_weight * passed_pack_weight * 100`
  - Appended to `passed_signals`

**`get_passed_scores() -> Dict[str, dict]`**
- Sums `passed_signals` per archetype (simple sum, always negative)
- Returns `{archetype_name: {"score": float}}`

**`get_top_passed(archetype_name, count=3) -> List[Dict]`**
- Top N passed cards by absolute signal (for tooltips)

**`reset()`** — also clears `passed_signals`

### Scoring formula

Same as `_simple_alsa_missing_emission`:
```
raw_signal = -(1.0 / (ata + pick_number))
signal = raw_signal * card_weight * passed_pack_weight * 100
```

### Pack weight inversion

Openness pack_weights `[w0, w1, w2]` become passed_pack_weights `[w1, w0, w2]`.

Rationale:
- P1 passes left, P2 passes right, P3 passes left
- Openness reads signals FROM the right (P1/P3 weighted high)
- Passed cards go TO the right neighbor in P2 (who feeds you), so P2 gets the P1 weight

## Overlay Integration (`overlay.py`)

### Detecting passed cards

Store previous state:
- `self._prev_pack_data = None` — tuple `(pack_cards, pick_in_pack, pack_number)`
- `self._prev_taken_count = 0`

Each update cycle in `__update_widgets`:
1. Compare `len(taken_cards)` with `_prev_taken_count`
2. If grown: pick was made. Passed = `prev_pack_cards` minus newly picked card(s)
3. Call `record_passed(passed_cards, prev_pick_in_pack, prev_pack_number)`
4. Update stored state

### UI layout

The openness panel row:
```
| Name (col 0) | Score (col 1) | [-> bar] (col 2) |  | [bar <-] (col 3) | Passed (col 4) |
```

- Left side (cols 0-2): existing openness display (unchanged)
- Right side (cols 3-4): passed-cards bars + score
- Bar color: single amber/orange (`#FFA726`)
- Bar grows LEFT from right edge, length proportional to abs(score) / max_abs_score
- Rows sorted by openness score (left side); right side follows same row order
- Tooltips on passed bars show top 3 passed cards per archetype

### Hindsight mode

`__replay_hindsight_openness` also replays passed cards:
- For each history entry with a `picked_card`, compute passed = `all_pack_cards` minus `picked_card`
- Call `record_passed()` with the appropriate pick/pack numbers

## Testing

- Unit tests for `record_passed()` scoring formula
- Unit tests for `get_passed_scores()` aggregation
- Unit tests for pack weight inversion
- Unit tests for `reset()` clearing passed state
- Integration test: replay a sequence of packs/picks and verify passed scores
