# Three-Column Openness Panel for simple_alsa

## Goal

Replace the current 2-bar openness panel layout with a 3-column bar layout that separates positive signals, negative (passed) signals, and combined score. Remove missing-card signals from `simple_alsa` scoring entirely.

## Current State

- `record_pack` produces positive wheeling signals (cards still in pack later than expected)
- `record_missing` produces negative signals for `simple_alsa` and `bayesian_survival`
- `record_passed` / `revert_returned` tracks user-passed cards separately
- Overlay shows 2 bars: openness score (green/red) + passed cards (orange)
- All signals (positive + missing negative) are mixed into `self.signals` and `get_scores()`

## Changes

### Backend (`archetype_openness.py`)

1. **Remove `simple_alsa` from `record_missing`**: Change condition from `not in ("bayesian_survival", "simple_alsa")` to `!= "bayesian_survival"`. Delete `_simple_alsa_missing_emission`.

2. **New `get_positive_scores()`**: Returns sum of positive `record_pack` signals per archetype (wheeling only). Reuses `self.signals` filtered to positive values.

3. **Existing `get_passed_scores()`**: No changes. Already returns passed-card negative signals with revert support.

4. **New `get_combined_scores()`**: Returns `positive + passed` per archetype. Single method that calls the other two internally.

### Frontend (`overlay.py` - `__update_openness_panel`)

Replace the 2-bar layout with 3 bar+score groups per row:

```
| Name (col 0) | Bar1 (col 1) | Score1 (col 2) | Bar2 (col 3) | Score2 (col 4) | Bar3 (col 5) | Score3 (col 6) |
```

- **Column 1** (green bar, grows right): Positive wheeling signals from `get_positive_scores()`
- **Column 2** (orange bar, grows left): Passed cards from `get_passed_scores()` (always negative)
- **Column 3** (green/red bar): Combined sum, green if positive, red if negative
- Each bar has a small numeric score label beside it
- `padx` spacing between groups for visual separation

### Tests

- Delete `TestSimpleAlsaMissing` class
- Add tests for `get_positive_scores()` and `get_combined_scores()`
- Verify `record_missing` no longer fires for `simple_alsa`

### What Gets Removed

- `_simple_alsa_missing_emission` method
- `"simple_alsa"` from `record_missing` condition
- Old 2-bar rendering in `__update_openness_panel`
- `TestSimpleAlsaMissing` test class
