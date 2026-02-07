# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MTGA_Draft_17Lands is a Python 3.12 desktop application (Tkinter) that assists Magic: The Gathering Arena drafters by overlaying 17Lands statistical data. It monitors Arena's Player.log file, parses draft events in real-time, and displays card ratings/grades/win rates. Supported events: Premier Draft, Traditional Draft, Quick Draft, Sealed, and Traditional Sealed.

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

### Key modules

- **overlay.py** (~4300 lines): Main application class. Tkinter UI, event loop, table rendering, tooltips, menus, and all user-facing windows (Taken Cards, Suggested Decks, Card Compare, Settings). This is the orchestrator that ties all other modules together.
- **log_scanner.py** (~1237 lines): `ArenaScanner` watches Arena's Player.log for draft events. Parses JSON log entries for pack contents, picks, and event detection. Handles multiple Arena log formats (the format has changed across Arena updates).
- **card_logic.py** (~1167 lines): `CardResult` processes card ratings. Calculates win rates, letter grades (A+ to F based on standard deviations), and 5-point ratings. Implements deck suggestions (Aggro/Mid/Control archetypes) and color filtering.
- **file_extractor.py** (~1092 lines): Downloads card data from the 17Lands API and extracts card databases from Arena's SQLite data files.
- **dataset.py** (~316 lines): `Dataset` class loads and provides card lookup (by Arena ID or name) from JSON data files stored in `Sets/`.
- **configuration.py** (176 lines): Pydantic-based configuration system. Models: `Configuration`, `Settings`, `CardLogic`, `Features`, `CardData`. Persists to `config.json`.
- **limited_sets.py** (~431 lines): Manages set information, fetches set lists from Scryfall API.
- **tier_list.py** (~372 lines): Downloads tier lists from 17Lands API. Pydantic models: `TierList`, `Meta`, `Rating`. Stores as JSON in `Tier/`.
- **set_metrics.py** (98 lines): `SetMetrics` calculates mean/standard deviation for win rate fields. Uses scipy's normal distribution for grade/rating conversions.
- **constants.py** (~600 lines): All configuration constants — 17Lands field mappings, Arena log patterns, color definitions, UI defaults, URLs.

### Runtime directories (gitignored)
`Debug/` (logs), `Downloads/`, `Logs/` (draft logs), `Screenshots/` (P1P1 OCR), `Sets/` (17Lands datasets as JSON), `Temp/`, `Tier/` (tier list data).

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
