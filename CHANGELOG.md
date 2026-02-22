# Changelog

Versions follow the decimal convention documented in CLAUDE.md:
- **+0.01** — minor fixes, formula tweaks, small adjustments
- **+0.1** — new features, new scoring methods, new UI panels
- **+1.0** — breaking changes (removed/renamed API, incompatible config schema)

---

## 4.2 — 2026-02-22
- Add Card Data window (Cards menu): displays all set cards with filterable columns (GIHWR, OHWR, GPWR, GNSWR, GDWR, ATA, ALSA, IWD, WHEEL, COLORS, NGP, GIH, RARITY), deck color filter dropdown, and rarity filter checkboxes; all columns individually toggleable

## 4.1 — 2026-02-22
- Add Trophy Deck Analysis window: fetches trophy decks from 17Lands and Untapped.gg via Playwright scraping
- Store trophy deck data in `Trophy/` directory
- Support Traditional Draft and Premier Draft trophy deck views

## 4.0 — 2026-02-21
**Breaking**: `merge_datasets()` no longer accepts a `weights` parameter. Callers must filter to enabled sources before passing.

- Replace user-specified weight averaging with game-count weighted rates (`merged_r = Σ(r_i × c_i) / Σ(c_i)`)
- `iwd` is now re-derived as `merged_gihwr − merged_gnswr` after merging (no longer averaged)
- `meta.game_count` is summed across all merged sources
- `DatasetSource.weight: float` replaced by `DatasetSource.enabled: bool`; old `config.json` files auto-migrate (`weight > 0` → `enabled=True`)
- Source editor UI: "Weight" input replaced with "Enabled" checkbox
- `color_ratings` weighted by `meta.game_count` instead of equal weight

## 3.9 — 2026-02-20
- Add GoatBots price integration for MTGO: `retrieve_goatbots_prices()` fetches card prices during set download
- Display `$$$` prefix in pack table for expensive MTGO cards (configurable threshold)
- Add price settings (enabled toggle + price threshold) to Settings window

## 3.8 — 2026-02-15
- Add passed-cards tracking to `OpennessTracker`: `record_passed()` records negative signals for cards the drafter skips (uses inverted pack weights)
- Add `get_passed_scores()` and `get_combined_scores()` / `get_positive_scores()` to `OpennessTracker`
- Add `revert_returned()` to remove passed-card signals when a card wheels back
- Render passed-cards bars alongside wheeling bars in the openness panel
- Replay passed-card signals in MTGO hindsight mode

## 3.7 — 2026-02-14
- Add `bayesian_survival` scoring method: unified three-signal log-odds framework
  - Signal 1 (wheeling): `λ₁ = (p-1) * log(q_open/q_closed)` — card present at pick p
  - Signal 2 (missing at wheel): `λ₂ = log((1-S_open)/(1-S_closed))` — archetype card taken before returning
  - Signal 3 (draft-wide absence): `λ₃ = k*log(see_open/see_closed) + (N-k)*log(…)` — across all packs
- Add `record_missing()` to feed Signal 2 from pack diffs at wheel picks
- Add `absence_enabled` and `slots_per_rarity` config fields to `ArchetypeConfig`
- Add `bayesian_survival` to archetype editor dropdown
- Integrate with hindsight mode: replay missing-card signals from pick history

## 3.6 — 2026-02-11
- Add MTGO HindSight mode: load and replay completed draft logs pick-by-pick with `←`/`→` navigation
- Replay archetype openness signals through the current history position (`__replay_hindsight_openness()`)
- Add credible interval display (95% CI via delta method) to openness panel
- Add per-pick debug logging to `OpennessTracker`

## 3.5 — 2026-02-07
- Add archetype openness detection system (`archetype_openness.py`)
  - `simple` and `normalized` scoring methods
  - `bayesian_beta` scoring: Beta posterior returning P(open) with 95% credible interval
  - `hmm_hybrid` scoring: log-odds tracker with geometric survival model, rarity weighting, pick ramp, and exponential decay
- Add `auto_detect_archetypes()`: builds archetype configs from 17Lands `ngp` ratios
- Add Archetype Editor window: auto-detection sliders, per-card weight editing, pack weight controls
- Integrate openness panel into overlay UI with confidence-based opacity and color coding
- Add `ArchetypeConfig` with per-set JSON persistence in `Archetypes/`
- Make overlay window horizontally resizable with proportional columns

## 3.4 — 2026-02-07
- Add full MTGO support: `MtgoScanner` monitors a folder for MTGO draft log files
- Two-phase incremental parsing: pack shown (Phase 1) → pick made with `-->` marker (Phase 2)
- MTGO folder polling with mtime guard (matches Arena polling pattern, fixes unconditional CPU waste)
- Fix `set_arena_file()` semantic: accepts file paths and extracts parent directory for folder scanning
- Fix byte-vs-character offset in `__parse_header()` for non-ASCII card names (e.g. accented characters)
- Remove auto-update check on startup (infrastructure preserved)

## 3.35 — 2025-11-25
- Add "best in" columns to the draft overlay table

## 3.34 — 2025-11-03
- Baseline inherited from upstream (powered cube support, data source retrieval fixes)
