# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MTGA_Draft_17Lands is a Python 3.12 desktop application (Tkinter) that assists Magic: The Gathering Arena and Magic Online (MTGO) drafters by overlaying 17Lands statistical data. It monitors Arena's Player.log or MTGO's draft log files, parses draft events in real-time, and displays card ratings/grades/win rates. Supported events: Premier Draft, Traditional Draft, Quick Draft, Sealed, Traditional Sealed, and MTGO Draft.

## Commands

### Running the application
```bash
pip install -r requirements.txt
python main.py
```

### Running tests

#### Windows
```bash
pytest tests/

# Single test file
pytest tests/test_card_logic.py

# Single test function
pytest tests/test_card_logic.py::test_tier_results
```

#### WSL (Linux)
WSL has no display server, so Xvfb is required for tests that import Tkinter. The project uses a virtual environment at `.venv/` (Ubuntu 24.04+ enforces PEP 668).

```bash
# Prerequisites (one-time setup)
sudo apt install -y python3-tk python3-venv xvfb
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install scipy

# Run all tests (use .venv/bin/pytest or activate the venv first)
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/

# Single test file
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_card_logic.py

# Single test function
Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_card_logic.py::test_tier_results
```

### Building Windows executable
```bash
pip install pywin32==306 pyinstaller==6.7.0
python -m PyInstaller main.py --onefile --noconsole -n MTGA_Draft_Tool --clean
```

### JavaScript tests (Chrome extension in Tools/TierScraper17Lands)
```bash
cd Tools/TierScraper17Lands && npm install --save-dev jest-environment-jsdom && npm test
```

## Architecture

### Entry point and data flow
`main.py` calls `src.overlay.start_overlay()` which initializes the full application. The core data flow is:

**Arena Player.log → ArenaScanner (log_scanner.py) → Dataset (dataset.py) → CardResult (card_logic.py) → Overlay UI (overlay.py)**

**MTGO draft logs → MtgoScanner (mtgo_scanner.py) → Dataset (dataset.py) → CardResult (card_logic.py) → Overlay UI (overlay.py)**

**Dataset merging flow (multi-source downloads):**
**Settings (per-set DatasetSources) → FileExtractor downloads N sources → merge_datasets() → single {SET}_Data.json → Dataset.open_file()**

### Key modules

- **overlay.py** (~4300 lines): Main application class. Tkinter UI, event loop, table rendering, tooltips, menus, and all user-facing windows (Taken Cards, Suggested Decks, Card Compare, Settings). This is the orchestrator that ties all other modules together.
- **log_scanner.py** (~1237 lines): `ArenaScanner` watches Arena's Player.log for draft events. Parses JSON log entries for pack contents, picks, and event detection. Handles multiple Arena log formats (the format has changed across Arena updates).
- **card_logic.py** (~1167 lines): `CardResult` processes card ratings. Calculates win rates, letter grades (A+ to F based on standard deviations), and 5-point ratings. Implements deck suggestions (Aggro/Mid/Control archetypes) and color filtering.
- **file_extractor.py** (~1092 lines): Downloads card data from the 17Lands API and extracts card databases from Arena's SQLite data files.
- **dataset.py** (~316 lines): `Dataset` class loads and provides card lookup (by Arena ID or name) from JSON data files stored in `Sets/`.
- **configuration.py** (~200 lines): Pydantic-based configuration system. Models: `Configuration`, `Settings`, `CardLogic`, `Features`, `CardData`, `DatasetSource`. Persists to `config.json`. Key settings: `Settings.platform` (`"MTGA"` or `"MTGO"`), `Settings.mtgo_log_folder`, `Settings.set_sources: Dict[str, List[DatasetSource]]` for per-set multi-source merging, `Features.archetype_openness_enabled`.
- **limited_sets.py** (~431 lines): Manages set information, fetches set lists from Scryfall API.
- **tier_list.py** (~372 lines): Downloads tier lists from 17Lands API. Pydantic models: `TierList`, `Meta`, `Rating`. Stores as JSON in `Tier/`.
- **set_metrics.py** (98 lines): `SetMetrics` calculates mean/standard deviation for win rate fields. Uses scipy's normal distribution for grade/rating conversions.
- **constants.py** (~600 lines): All configuration constants — 17Lands field mappings, Arena log patterns, color definitions, UI defaults, URLs.
- **mtgo_scanner.py** (~655 lines): `MtgoScanner` watches a folder for MTGO draft log files (plain text). Implements two-phase incremental parsing: Phase 1 detects pack shown (cards without pick marker), Phase 2 detects pick made (`-->` marker). Shares the same public interface as `ArenaScanner` so overlay code is platform-agnostic. MTGO filenames encode set codes (e.g., `ECLECLECL` = 3 packs of ECL).
- **archetype_openness.py** (~487 lines): `OpennessTracker` scores how "open" each archetype is during a draft. Supports four scoring methods: `simple`, `normalized`, `bayesian_beta`, and `hmm_hybrid`. Card weights from 17Lands `ngp` ratios distinguish archetype-specific cards from generics. `auto_detect_archetypes()` builds archetype configs from dataset data. `ArchetypeConfig` holds tuning parameters including HMM-specific fields (`hmm_transition_decay`, `hmm_emission_scale`, `hmm_openness_factor`, `hmm_pick_ramp`, `rarity_odds`).
- **archetype_editor.py**: Tkinter editor for archetype configurations. Auto-detection with threshold/weight sliders, per-archetype card lists with editable weights, scoring method selection (Simple/Weighted/Bayesian %), and pack weight controls. Configs persist to `Archetypes/{SET}_archetypes.json`.

### Key subsystems

**Dataset merging**: `merge_datasets()` in `file_extractor.py` combines multiple 17Lands sources with weighted averaging. `COUNT_FIELDS` (ngp, ngoh, gih, ngnd, ngd) are summed; win rate fields are weighted-averaged with zero-count and zero-rate filtering. Per-set sources configured via `DatasetSource` model. Merged files use 2-segment naming (`{SET}_Data.json`); old 4-segment files auto-deleted by `delete_old_set_files()`.

**Archetype openness**: `OpennessTracker` supports four scoring methods configured via `ArchetypeConfig.scoring_method`:
- **simple/normalized**: Sum-of-signals scoring. Signal = `(pick - ata) / (ata + pick)^2` scaled by card/pack weights.
- **bayesian_beta**: Beta(alpha, beta) posteriors per archetype. Signal magnitude `(pick - ata) / (pick + ata)` updates alpha (positive) or beta (negative). Returns P(open) as posterior mean with 95% credible interval.
- **hmm_hybrid**: HMM-inspired log-odds tracker using a geometric survival model. Emission = log Bayes factor `(p-1) * [log(1 - 1/(a*F)) - log(1 - 1/a)]` where F is the openness factor. Features: rarity-weighted reliability (rarer cards = weaker signal), pick ramp (reduced early-pick weight), exponential decay between observations (`hmm_transition_decay`), and variance tracking via decayed sum-of-squared emissions for 95% credible intervals. Returns sigmoid(log_odds) as P(open).

Confidence shown via opacity: none (0 signals, 40%), low (1-4, 60%), medium (5-14, 80%), high (15+, 100%). Green/gray/red bar colors based on P(open) thresholds (0.55/0.45).

**MTGO scanner**: Monitors a folder for `.txt` draft logs. Two-phase incremental parsing: file grows when pack is shown (overlay displays ratings), then again when pick is made (`-->` marker + `Picked:` line). Filename format: `{user}-{date}-{event}-{id}-{setcodes}.txt`. Set codes parsed as 3-char chunks from the suffix.

**MTGO HindSight mode**: MTGO-only feature (`Settings.mtgo_hindsight_enabled`) that lets users load and review completed draft logs pick-by-pick. Core flow:
1. `MtgoScanner.load_draft_file(filepath)` parses the header and calls `__build_pick_history(content)` to build an immutable list of pick state snapshots.
2. Each history entry stores: `current_pack`, `current_pick_in_pack`, `current_pick`, `pack_cards` (display list minus picked card), `all_pack_cards` (full pack including picked card), `picked_card` (name of the card picked, empty for PACK_SHOWN), `initial_pack_cards`, `picked_cards_in_pack`, `taken_cards`, `state`.
3. `navigate_history(offset)` moves forward/backward through the history, calling `__apply_history_state()` which copies the snapshot onto the scanner's live fields. In hindsight mode, `pack_cards` is set from `all_pack_cards` so the picked card is visible. `hindsight_picked_card` tracks which card was picked at the current position.
4. `draft_data_search()` returns `False` immediately when `hindsight_mode=True` (no live scanning during review).
5. The overlay UI shows a file dropdown and `←`/`→` arrow buttons (in `mtgo_hindsight_frame`). The pack table marks the picked card with a `→` prefix.
6. **Archetype openness integration**: When enabled, the overlay replays all openness signals from pick 1 through the current history position on each navigation (`__replay_hindsight_openness()`), giving a "what would openness have shown at this point" view. The tracker is reset before each replay to avoid stale accumulation.

### Runtime directories (gitignored)
`Archetypes/` (per-set archetype configs as JSON), `Debug/` (logs), `Downloads/`, `Logs/` (draft logs), `Screenshots/` (P1P1 OCR), `Sets/` (17Lands datasets as JSON), `Temp/`, `Tier/` (tier list data).

### External services
- **17Lands API**: Card ratings, tier lists, color ratings
- **Scryfall API**: Card images and set metadata
- **Google Cloud Function**: OCR for P1P1 detection (sends screenshot, returns card names)
- **GitHub Releases API**: Auto-update checking

## Testing

- Framework: pytest 8.2.0
- Test fixtures in `tests/data/` contain real 17Lands data snapshots (JSON)
- Tests use `pytest.fixture`, `@pytest.mark.parametrize`, and `tmp_path` for file I/O
- `test_log_scanner.py` is the largest test file (~3478 lines) with extensive Arena log format coverage
- CI runs on all three platforms (Linux, Windows, macOS) on PRs that modify `.py` files

## Code Conventions

- Constants: `UPPER_SNAKE_CASE` in `constants.py`
- Classes: `PascalCase`, functions/methods: `snake_case`, private: `_leading_underscore`
- Logging via `src.logger` → writes to `Debug/debug.log` (7-day rotation)
- No enforced formatter or linter — no pyproject.toml, .flake8, or pre-commit hooks
- Configuration uses Pydantic models with field validators for type safety
