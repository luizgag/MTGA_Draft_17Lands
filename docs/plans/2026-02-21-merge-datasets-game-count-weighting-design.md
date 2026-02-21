# Design: Fix `merge_datasets` — Game-Count Weighted Rates

**Date:** 2026-02-21
**Status:** Approved

## Problem

`merge_datasets` in `file_extractor.py` has two bugs:

1. **Meta `game_count` not aggregated**: The merged JSON inherits `meta` from the first source only, so the `game_count` field reflects only the first dataset (e.g., Premier Top's 59,529 games) even when 4 sources are merged.

2. **Win rates weighted by user-specified weights, not game counts**: The current formula for rate fields uses `user_weight` (e.g., 0.7/0.3) as the averaging weight. This over-represents small-sample sources. Example:
   - Premier Top: 10,000 games, gihwr = 55.0%, user weight = 0.5
   - Traditional Top: 500 games, gihwr = 60.0%, user weight = 0.5
   - Current result: (55 × 0.5 + 60 × 0.5) / 1.0 = **57.5%** (wrong)
   - Correct result: (55 × 10,000 + 60 × 500) / 10,500 ≈ **55.2%**

## Decisions

- **Rate weighting**: Replace user-specified weights with game-count weighting. Each source's rate is weighted by the number of games behind it.
- **`iwd` field**: Re-derive as `merged_gihwr − merged_gpwr` after computing other rates, since `iwd` is a derived stat.
- **`DatasetSource.weight`**: Replace with `DatasetSource.enabled: bool`. Fractional weights are removed. Sources are either included or excluded. Backward-compatible migration via Pydantic validator.
- **`merge_datasets` signature**: Remove `weights` parameter. Caller filters datasets to active-only before passing.

## Affected Files

| File | Changes |
|---|---|
| `src/file_extractor.py` | Remove `weights` param; fix `_merge_deck_colors` rate formula; aggregate meta |
| `src/configuration.py` | `DatasetSource.weight → enabled: bool` with backward-compat validator |
| `src/overlay.py` | Filter by `source.enabled`; remove weight from `all_weights`; update source editor UI |
| `tests/test_file_extractor.py` | Rewrite `TestMergeDatasets` with TDD for correct behavior |

## Merge Logic (Post-Fix)

### Rate field formula

For each win rate field `r` with corresponding count field `c`:

```
merged_r = Σ(r_i × c_i) / Σ(c_i)
```

| Rate field | Count field used as weight |
|---|---|
| `gihwr` | `gih` |
| `ohwr` | `ngoh` |
| `gpwr` | `ngp` |
| `gnswr` | `ngnd` |
| `gdwr` | `ngd` |
| `alsa`, `ata` | `ngp` |
| `iwd` | re-derived as `merged_gihwr − merged_gpwr` |

Filtering rules (unchanged):
- Skip a source's contribution if its count field is 0
- Skip a source's contribution if the rate is 0.0 (17Lands suppressed it)

### Meta aggregation

```python
result["meta"]["game_count"] = sum(
    ds.get("meta", {}).get("game_count", 0) for ds in datasets
)
```

Other meta fields (format, etc.) come from the first dataset.

### `DatasetSource` migration

```python
class DatasetSource(BaseModel):
    format: str = "PremierDraft"
    user_group: str = "All"
    enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def _migrate_weight(cls, data):
        if isinstance(data, dict) and "weight" in data and "enabled" not in data:
            data["enabled"] = float(data.pop("weight")) > 0
        else:
            data.pop("weight", None)
        return data
```

### `merge_datasets` new signature

```python
def merge_datasets(datasets: List[dict]) -> dict:
    """Merge datasets using game-count weighted rates. All passed datasets are merged."""
```

Caller (overlay.py) filters:
```python
active_pairs = [(ds, src) for ds, src in zip(all_datasets, active_sources) if src.enabled]
if len(active_pairs) > 1:
    merged = merge_datasets([ds for ds, _ in active_pairs])
```

### Source editor UI

Remove the "Weight" label and Entry widget. Add an "Enabled" checkbox (default checked).

## TDD Sequence

1. **Write failing tests** for:
   - `merge_datasets(datasets)` with no weights param (API change)
   - Game-count weighted rates (not equal-weight)
   - Meta `game_count` summed across sources
   - `iwd` re-derived from merged rates
   - Backward-compat migration of `DatasetSource.weight` field in config JSON

2. **Update/remove existing tests** that assert old (user-weight-based) behavior:
   - `test_merge_weighted_rates` — currently tests 0.6/0.4 user-weight skew; replace with game-count test
   - `test_merge_zero_weight_excludes_source` — becomes `test_merge_disabled_source_excluded`

3. **Implement** `_merge_deck_colors`, `merge_datasets`, `DatasetSource`, and `overlay.py` changes.

4. **Run full test suite** to confirm no regressions.
