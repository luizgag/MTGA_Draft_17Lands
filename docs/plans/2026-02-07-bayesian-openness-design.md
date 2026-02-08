# Bayesian Archetype Openness Scoring — Design Document

## Problem

Archetype openness signals are weakest in Pack 1 (where decisions matter most) and strongest in Pack 3 (where you're already locked in). The current system has no way to express *confidence* in a signal — a score of +3.0 from 2 observations looks identical to +3.0 from 20 observations.

Drafters need to know: "Is this score trustworthy enough to commit to this archetype?"

## Solution

Add three new scoring methods alongside the existing Simple and Weighted methods. Each addresses the uncertainty problem differently:

1. **Bayesian (%)** — Thompson Sampling with Beta posteriors. Outputs P(open) as 0-100%.
2. **Bayesian (Score)** — Normal posterior. Outputs mean score with credible intervals.
3. **UCB Exploration** — Upper Confidence Bound bonus for under-observed archetypes.

All methods provide a confidence level (`none | low | medium | high`) displayed via opacity gradient in the overlay panel.

## Scoring Methods

### 1. Bayesian (%) — `bayesian_beta`

For each archetype, classify each signal as positive or negative:
- Card seen later than ATA → positive (archetype is open)
- Card seen earlier than ATA → negative (archetype is closed)

Signal weight = `abs(signal_value)` where signal_value = `(pick - ATA) * card_weight * pack_weight`.

Maintain a Beta distribution:
- `alpha = prior + sum(positive signal weights)`
- `beta = prior + sum(negative signal weights)`
- Score = `alpha / (alpha + beta)` (posterior mean, displayed as percentage)
- Variance = `alpha * beta / ((alpha + beta)^2 * (alpha + beta + 1))`

Default prior: `Beta(1, 1)` (uniform — no initial bias). Configurable via `bayesian_prior` field.

### 2. Bayesian (Score) — `bayesian_normal`

Keep raw signal values. For each archetype, compute:
- `n` = number of signals
- `sample_mean` = mean of signal values
- `sample_var` = variance of signal values

Normal posterior with conjugate prior `Normal(mu_0=0, kappa_0)`:
- Posterior mean: `(kappa_0 * mu_0 + n * sample_mean) / (kappa_0 + n)`
- Posterior precision increases with n
- 95% credible interval: `mean +/- 1.96 * sqrt(sample_var / (kappa_0 + n))`

Default `kappa_0 = bayesian_prior` (default 1.0).

### 3. UCB Exploration — `ucb`

Use existing signal accumulation (simple raw scores), then add exploration bonus:

```
ucb_score = raw_score + c * sqrt(log(total_signals) / archetype_signals)
```

Where:
- `raw_score` = sum of signals for this archetype
- `total_signals` = total signals across all archetypes
- `archetype_signals` = signals for this specific archetype
- `c` = tunable exploration parameter (`ucb_exploration`, default 1.0)

Archetypes with few observations get a larger bonus, naturally promoting exploration when data is scarce.

## Signal Input

Bayesian and UCB methods use **raw signals**: `(pick_number - ATA) * card_weight * pack_weight`. No pick-position weighting is applied — the probabilistic framework handles uncertainty natively.

Only the existing `normalized` (Weighted) method uses pick-position weighting with configurable curves.

## Confidence Levels

Derived from weighted observation count per archetype:
- `"none"` — 0 signals (prior only)
- `"low"` — 1-4 weighted observations
- `"medium"` — 5-14 weighted observations
- `"high"` — 15+ weighted observations

These roughly map to: early Pack 1 = low, late Pack 1 = medium, Pack 2+ = high.

## Return Type Change

`get_scores()` changes from `Dict[str, float]` to `Dict[str, dict]`:

```python
{
    "Boros": {
        "score": 0.72,          # P(open) for beta, raw for others
        "confidence": "low",    # none | low | medium | high
        "interval": (0.45, 0.99),  # credible interval bounds
    },
    ...
}
```

All five methods use this same return shape. Simple/Weighted have `interval = None`.

## UI Changes

### Overlay Panel (overlay.py)

Score display adapts per method:
- Simple / Weighted: `+3.2`
- Bayesian (%): `72%`
- Bayesian (Score): `+3.2 +/-4.1`
- UCB Exploration: `+5.1`

Confidence communicated via **opacity gradient**:
- `"none"` = 40% opacity
- `"low"` = 60% opacity
- `"medium"` = 80% opacity
- `"high"` = 100% opacity

Bar visualization:
- Simple/Weighted/UCB: green (positive) / red (negative) proportional bar
- Bayesian (%): green gradient bar from 0-100%
- Bayesian (Score): green/red bar with whisker lines at interval bounds

### Archetype Editor

Scoring dropdown expands:
- Display labels: `Simple | Weighted | Bayesian (%) | Bayesian (Score) | UCB Exploration`
- Internal values: `simple | normalized | bayesian_beta | bayesian_normal | ucb`

Conditional fields:
- `Bayesian (%)` or `Bayesian (Score)` → show "Prior:" spinbox (default 1.0)
- `UCB Exploration` → show "Explore:" spinbox (default 1.0)
- `Weighted` → show "Curve:" dropdown (linear/sqrt/squared)

## Config Model Changes

```python
class ArchetypeConfig(BaseModel):
    set_code: str
    detection_threshold: float = 5.0
    scoring_method: str = "simple"
    weight_curve: str = "linear"
    pack_weights: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    ucb_exploration: float = 1.0        # NEW
    bayesian_prior: float = 1.0         # NEW
    archetypes: List[Archetype] = Field(default_factory=list)
```

Both new fields have defaults, ensuring backward compatibility with existing config files.

## Files Modified

| File | Change |
|------|--------|
| `src/archetype_openness.py` | New fields on ArchetypeConfig, three new scoring methods on OpennessTracker, updated get_scores return type |
| `src/overlay.py` | Update `__update_openness_panel` for rich score display, opacity, method-specific formatting |
| `src/archetype_editor.py` | Expand scoring dropdown, conditional Prior/Explore fields |
| `tests/test_archetype_openness.py` | ~22 new tests, update ~20 existing assertions for new return shape |

## Test Plan

### TestBayesianBetaScoring (~8 tests)
- No signals → prior mean 0.5, confidence "none"
- All positive → P(open) > 0.5
- All negative → P(open) < 0.5
- Mixed signals → intermediate
- Confidence level thresholds (0/3/10/20 signals)
- Prior parameter effect
- Strong vs weak signal magnitude
- Pack weight effect

### TestBayesianNormalScoring (~6 tests)
- No signals → mean 0.0, wide interval
- Signals shrink interval
- Consistent signals → tight interval
- Confidence level thresholds
- Interval symmetry

### TestUCBScoring (~5 tests)
- No signals → high exploration bonus
- Many signals → bonus shrinks
- Under-observed gets higher bonus
- exploration=0 disables bonus
- Equal raw scores → fewer signals ranks higher

### TestGetScoresReturnShape (~3 tests)
- All methods return dict with score/confidence/interval keys
- Simple/normalized backward compat
- Score ranges correct per method

### Existing test updates (~20 assertions)
- Change `scores["Name"]` to `scores["Name"]["score"]`

## No New Dependencies

Beta distribution: `alpha/(alpha+beta)` — basic arithmetic.
Normal CI: `mean +/- 1.96 * sqrt(var/n)` — basic arithmetic.
UCB: `score + c * sqrt(log(total)/n)` — math.log and math.sqrt from stdlib.
