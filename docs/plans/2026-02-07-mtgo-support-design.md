# MTGO Draft Support - Design Document

## Goal

Extend the application to support MTGO (Magic Online) drafts alongside MTGA, reusing the existing overlay, card_logic, dataset, and 17Lands data. The only new component is an MTGO log parser.

## Approach

Create a new `MtgoScanner` class that implements the same public interface as `ArenaScanner`. The overlay instantiates the correct scanner based on a platform setting in the configuration.

## MTGO Draft Log Format

MTGO writes draft logs to a user-configured folder (e.g., `C:\Users\Luiz\Documents\MTGO Draft Logs`). Each draft creates a separate `.txt` file that grows incrementally during drafting.

### Filename format
```
<username>-<date>-<event_num>-<event_id>-<set_codes>.txt
Example: luluch1-2026.2.6-10252-34431293-ECLECLECL.txt
```
The set codes suffix encodes the set for each pack (e.g., `ECLECLECL` = 3 packs of ECL).

### File structure
```
Event #: 10252
Time:    2/6/2026 8:14:11 PM
Players:
    Player1
    Player2
    ...
--> HeroPlayer        (hero identified by --> prefix)

------ Pack 1: Lorwyn Eclipsed ------

Pack 1 pick 1:
    Card A
    Card B
    Card C             (cards appear FIRST while player views pack)
--> Picked Card        (pick marker added AFTER player picks)
    Card D
    ...

Picked: Picked Card    (confirmation line)
```

### Two-phase write (critical)
The log file grows in two phases per pick:
1. **Phase 1 - Pack shown**: `Pack X pick Y:` header + card names written to file. No `-->` yet. Player is viewing the pack. **This is when the overlay must display ratings.**
2. **Phase 2 - Pick made**: `-->` marker and `Picked:` confirmation appended after the player clicks.

### Pick numbering
The pick numbers in the log (`pick 1`, `pick 2`, etc.) are unreliable and may repeat. The scanner must count picks sequentially within each pack instead.

### Pack transitions
New packs are detected by:
- `------ Pack N: <Set Name> ------` header lines
- Alternatively, a new `Pack X pick Y:` block where the card count is larger than the previous pack's card count (same heuristic as `modo.py:parse_draft_log`)

## Architecture

### Scanner interface (shared between ArenaScanner and MtgoScanner)

Both scanners expose these public methods:

**Lifecycle:**
- `draft_start_search() -> bool` - Detect draft start. Returns True if new draft found.
- `draft_data_search(use_ocr=False, save_screenshot=False) -> bool` - Scan for new pack/pick data. Returns True if new data found. (OCR params ignored by MtgoScanner.)
- `clear_draft(full_clear=False)` - Reset draft state.

**Data retrieval:**
- `retrieve_current_pack_and_pick() -> (int, int)` - Current pack/pick numbers.
- `retrieve_current_limited_event() -> (str, str)` - Set code and event type.
- `retrieve_current_pack_cards() -> list[dict]` - Cards visible in current pack.
- `retrieve_current_picked_cards() -> list[dict]` - Cards picked in current pack.
- `retrieve_current_missing_cards() -> list[dict]` - Cards that wheeled.
- `retrieve_taken_cards() -> list[dict]` - All cards picked during the draft.
- `retrieve_data_sources() -> dict` - Available 17Lands datasets for the current set.
- `retrieve_set_data(file) -> None` - Load a 17Lands dataset.
- `retrieve_set_metrics() -> SetMetrics` - Mean/std statistics.
- `retrieve_color_win_rate(label_type) -> dict` - Color combination win rates.

**Configuration:**
- `log_enable(enable)` - Enable/disable draft logging.
- `log_suspend(suspended)` - Suspend draft logging.

### MtgoScanner state machine

```
WAITING ──(file grows with pack block)──> PACK_SHOWN
PACK_SHOWN ──(file grows with --> marker)──> PICK_MADE
PICK_MADE ──(process pick, clear pack)──> WAITING
```

- **WAITING**: Polling for file changes. No new content.
- **PACK_SHOWN**: Pack cards parsed, no pick yet. `retrieve_current_pack_cards()` returns the visible cards. `draft_data_search()` returned True.
- **PICK_MADE**: Pick marker found. Move picked card to `taken_cards`. Transition to WAITING.

### Card lookup

ArenaScanner uses Arena card IDs (`set_data.get_data_by_id()`). MtgoScanner uses card names (`set_data.get_data_by_name()`) since MTGO logs only contain card names.

### File monitoring

MtgoScanner watches the configured folder for the most recently modified `.txt` file. It tracks `file_size` and reads from the last offset when the file grows. The overlay's existing 1-second polling loop works unchanged.

## Configuration Changes

### New settings in `configuration.py` (Settings model)
- `platform: str = "MTGA"` - Platform selection: `"MTGA"` or `"MTGO"`
- `mtgo_log_folder: str = ""` - Path to MTGO draft log folder

### New constants in `constants.py`
- `PLATFORM_MTGA = "MTGA"`
- `PLATFORM_MTGO = "MTGO"`

## Overlay Changes (Minimal)

1. **Scanner factory**: Based on `configuration.settings.platform`, instantiate `ArenaScanner` or `MtgoScanner`.
2. **Settings UI**: Add platform dropdown and MTGO log folder path field to Settings window.
3. **Polling**: Same `__arena_log_check()` logic works for both scanners. MtgoScanner's `draft_start_search()` and `draft_data_search()` handle file monitoring internally.

## Files Changed

| File | Change |
|------|--------|
| `src/mtgo_scanner.py` | **New** - MtgoScanner class (~300-400 lines) |
| `src/configuration.py` | **Edit** - Add `platform` and `mtgo_log_folder` settings |
| `src/constants.py` | **Edit** - Add MTGO platform constants |
| `src/overlay.py` | **Edit** - Scanner factory logic, Settings UI additions |
| `tests/test_mtgo_scanner.py` | **New** - Tests using the example draft log |

## What stays unchanged

- `src/card_logic.py` - All card rating/grading logic
- `src/dataset.py` - Card data loading and lookup
- `src/set_metrics.py` - Statistical calculations
- `src/file_extractor.py` - 17Lands data downloading
- `src/tier_list.py` - Tier list management
- `src/limited_sets.py` - Set metadata

## Edge Cases

- **Split/double-faced cards**: MTGO may use different naming conventions (e.g., `Card A / Card B` vs `Card A // Card B`). The `modo.py` example shows handling for SPLIT, MDFC, and ADVENTURE cards. MtgoScanner should normalize card names to match 17Lands format.
- **Empty folder**: If no `.txt` files exist in the MTGO log folder, `draft_start_search()` returns False.
- **Multiple drafts**: If multiple draft files exist, always watch the most recently modified one.
- **Basic lands in packs**: MTGO packs include basic lands. These appear in the log but have no 17Lands data. The scanner should handle them gracefully (they'll show "NA" for all metrics).
