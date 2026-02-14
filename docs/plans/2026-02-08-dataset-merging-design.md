# Dataset Merging Design

## Problem

The app downloads a single 17Lands dataset (one format, one user group, one date range). Users playing BO3 on MTGO want Traditional Draft win rates but need Premier Draft's larger sample for stable ATA values. There's no way to combine these — you pick one or the other.

## Solution

Download multiple 17Lands datasets with different filters and merge them into a single JSON file at download time. The rest of the application is unaware of the merge — it loads one file as always.

## Research Summary

Key findings from 17Lands community and statistical best practices:

- **ATA is similar across Premier/Traditional** since the draft portion is identical on Arena. The differences appear in win rates (sideboard cards, hand smoothing).
- **Top-player filtering reduces bias** at an acceptable sample cost (45% of games come from top-tier players). Top players pick complex cards earlier and achieve +0.4% win rate from card quality alone.
- **First 2 weeks of a format are noisy** — pick orders and archetypes are still stabilizing. Ryan Saxe's Statistical Drafting waits 2 weeks before publishing models.
- **Bias-variance tradeoff**: filtering reduces confounding bias but increases variance from smaller samples. Merging datasets with weights lets users tune this tradeoff.

## Architecture

### Current flow
```
Settings UI → FileExtractor downloads one source → single JSON → Dataset.open_file()
```

### New flow
```
Settings UI (multi-source) → FileExtractor downloads N sources → merge → single JSON → Dataset.open_file()
```

Only the download path changes. Overlay, openness tracker, card logic, and Dataset class remain untouched.

## Data Model

### New Pydantic model in `configuration.py`

```python
class DatasetSource(BaseModel):
    """A single 17Lands data source with filter configuration."""
    format: str = "PremierDraft"
    user_group: str = "All"
    start_date: str = ""      # YYYY-MM-DD, empty = set default
    end_date: str = ""        # YYYY-MM-DD, empty = today
    weight: float = 1.0       # relative weight for merging
```

Add to `Settings`:
```python
class Settings(BaseModel):
    ...
    dataset_sources: List[DatasetSource] = Field(
        default_factory=lambda: [DatasetSource()]
    )
```

Default: single Premier Draft / All players source with weight 1.0 — identical to current behavior. Backward-compatible with existing config.json files (Pydantic fills the default).

## Merge Function

New function in `file_extractor.py`:

```python
def merge_datasets(datasets: List[dict], weights: List[float]) -> dict:
    """Merge multiple 17Lands dataset JSON dicts into one using weighted averages.

    For each card (by Arena ID), for each numeric field in deck_colors:
        merged_value = sum(value_i * weight_i) / sum(weight_i)
        (only across datasets that contain this card)

    Non-numeric fields (name, types, colors, image, mana_cost, rarity) come
    from the first dataset that has the card.

    color_ratings section gets the same weighted-average treatment.
    """
```

### Merge rules

| Field type | Merge strategy |
|---|---|
| Numeric (gihwr, ohwr, gpwr, ata, alsa, iwd, ngp, etc.) | Weighted average across sources that have data |
| Non-numeric (name, types, colors, image, mana_cost, rarity, cmc) | First source that has the card |
| Card missing from a source | That source excluded from the average for that card |
| All sources have weight 0 | Error, no data produced |
| Field is 0.0 in a source | Treated as real data, included in average |

### Example

Two sources: Premier (weight=0.7) and Traditional (weight=0.3).

Card "Murder": Premier GIHWR=55.0, Traditional GIHWR=58.0

```
merged_gihwr = (55.0 * 0.7 + 58.0 * 0.3) / (0.7 + 0.3) = 55.9
```

Card "Obscure Mythic": only in Premier (Traditional has 0 games)

```
merged = Premier values at full weight (no renormalization needed)
```

## Download Orchestration

In `overlay.py __add_set`:

1. Read `dataset_sources` from configuration
2. For each source with weight > 0:
   - Create/configure a FileExtractor with that source's format, user_group, dates
   - Download card ratings and color ratings
   - Store the raw combined_data dict
3. Call `merge_datasets(all_dicts, all_weights)` to produce the final merged dict
4. Export the merged dict as the single JSON file (same path, same format as today)

If only one source is configured (the default), skip the merge step entirely — just download and export as before.

## UI

### Settings Window — Data Sources section

Add a section to the existing download popup (or a new tab/panel) with:

- A list of configured sources, each showing: Format, User Group, Date Range, Weight
- "Add Source" button (adds a new row with defaults)
- "Remove" button (removes selected source)
- Inline editing of format (combobox), user_group (combobox), dates, weight (entry)
- The "Download Dataset" button triggers the multi-source download + merge

### Archetype Editor

No changes needed — the openness tracker uses the same merged dataset that the overlay loads. The Archetype Editor's "Auto-Detect" already operates on whatever dataset is loaded.

## Implementation Plan

### Phase 1: Core merge logic (no UI changes)
1. Add `DatasetSource` model to `configuration.py`
2. Add `dataset_sources` field to `Settings` with backward-compatible default
3. Write `merge_datasets()` function in `file_extractor.py`
4. Write tests for merge_datasets (edge cases: single source, missing cards, zero weights)

### Phase 2: Download orchestration
5. Modify `__add_set` in `overlay.py` to loop over sources and call merge
6. Integration test with mock API responses

### Phase 3: UI
7. Add multi-source configuration UI to the download popup
8. Manual testing with real 17Lands data

### Phase 4: Polish
9. Display source info in the set list (show which sources were merged)
10. Logging of merge operations for debugging

## Testing Strategy

### Unit tests for merge_datasets
- Single dataset passthrough (no merge needed)
- Two datasets, equal weights → simple average
- Two datasets, unequal weights → weighted average
- Card present in only one dataset → uses that dataset's values
- Empty dataset → skipped
- All numeric fields are averaged (ata, gihwr, ohwr, gpwr, ngp, alsa, iwd)
- Non-numeric fields preserved from first dataset
- color_ratings section merged correctly
- Zero weight source is excluded
- Backward compatibility: old config without dataset_sources gets default

### Integration tests
- Download mock + merge + Dataset.open_file → verify card data accessible
- End-to-end with real OTJ test fixture

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Download takes too long with multiple sources | Progress bar shows per-source progress. Rate limiting per source. |
| API rate limiting from 17Lands | Existing retry logic applies per source. Add delay between sources. |
| Merged NGP is meaningless as weighted average | Document that NGP in merged datasets is approximate. Consider summing instead of averaging. |
| Old config.json without dataset_sources | Pydantic default fills single Premier source — fully backward compatible |
