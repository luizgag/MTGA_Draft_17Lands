# Bayesian (%) Archetype Openness — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Bayesian Beta scoring method to the archetype openness system that outputs P(open) as a 0-100% value with confidence levels, using the existing card weight system (ngp(color_pair) / ngp(All Decks)) to weight each signal's contribution.

**Architecture:** The existing `OpennessTracker` gains a new `bayesian_beta` scoring mode. Signals are classified as positive/negative based on whether a card appears later/earlier than its ATA. Each signal's magnitude is weighted by the existing `card_weight` (archetype affinity) and `pack_weight`, then accumulated into per-archetype Beta posteriors. The `get_scores()` return type changes from `Dict[str, float]` to `Dict[str, dict]` with `score`, `confidence`, and `interval` keys. All existing scoring methods are updated to use the same return shape.

**Tech Stack:** Python 3.12, Pydantic, pytest. No new dependencies — Beta math is `alpha/(alpha+beta)`, using `math.sqrt` from stdlib.

---

### Task 1: Add `bayesian_prior` field to ArchetypeConfig

This task adds the new config field with a default so existing JSON configs remain backward compatible.

**Files:**
- Modify: `src/archetype_openness.py:20-27`
- Test: `tests/test_archetype_openness.py`

**Step 1: Write failing tests for the new config field**

Add at the bottom of `tests/test_archetype_openness.py`, after the `TestMtgoPickConversion` class:

```python
class TestBayesianConfig:
    """Tests for bayesian_prior configuration field."""

    def test_default_bayesian_prior(self):
        """Default bayesian_prior is 1.0."""
        config = ArchetypeConfig(set_code="TST")
        assert config.bayesian_prior == 1.0

    def test_bayesian_prior_round_trip(self, tmp_path):
        """bayesian_prior persists through save/load cycle."""
        config = ArchetypeConfig(set_code="TST", bayesian_prior=2.5)
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.bayesian_prior == 2.5

    def test_old_config_without_bayesian_prior_gets_default(self):
        """Config JSON missing bayesian_prior field gets 1.0 default."""
        data = {"set_code": "TST", "scoring_method": "simple"}
        config = ArchetypeConfig.model_validate(data)
        assert config.bayesian_prior == 1.0
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianConfig -v`
Expected: FAIL — `bayesian_prior` doesn't exist on `ArchetypeConfig`.

**Step 3: Add `bayesian_prior` to ArchetypeConfig**

In `src/archetype_openness.py`, line 26, add a new field after `pack_weights`:

```python
class ArchetypeConfig(BaseModel):
    """Full archetype configuration for a set."""
    set_code: str
    detection_threshold: float = 5.0
    scoring_method: str = "simple"
    weight_curve: str = "linear"
    pack_weights: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    bayesian_prior: float = 1.0
    archetypes: List[Archetype] = Field(default_factory=list)
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianConfig -v`
Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add bayesian_prior field to ArchetypeConfig"
```

---

### Task 2: Change `get_scores()` return type to `Dict[str, dict]`

This task changes the return shape for all existing scoring methods (simple, normalized) from `Dict[str, float]` to `Dict[str, dict]` with keys `score`, `confidence`, and `interval`. It also updates all existing test assertions.

**Files:**
- Modify: `src/archetype_openness.py:133-232` (OpennessTracker class)
- Modify: `tests/test_archetype_openness.py` (all existing `get_scores()` assertions)
- Modify: `src/overlay.py:1631-1675` (__update_openness_panel)

**Step 1: Write a test enforcing the new return shape**

Add this class to `tests/test_archetype_openness.py` before `TestBayesianConfig`:

```python
class TestGetScoresReturnShape:
    """Tests for unified get_scores return shape."""

    def test_simple_returns_dict_with_keys(self):
        """Simple scoring returns {name: {score, confidence, interval}}."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        result = scores["BG Elves"]
        assert "score" in result
        assert "confidence" in result
        assert "interval" in result
        assert isinstance(result["score"], float)

    def test_simple_no_signals_confidence_none(self):
        """With no signals, confidence should be 'none'."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "none"
        assert scores["BG Elves"]["score"] == 0.0

    def test_simple_interval_is_none(self):
        """Simple scoring doesn't produce credible intervals."""
        tracker = OpennessTracker(SIMPLE_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["interval"] is None
```

**Step 2: Run to verify failure**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestGetScoresReturnShape -v`
Expected: FAIL — `get_scores()` returns float, not dict.

**Step 3: Update `get_scores()` and add confidence helper**

In `src/archetype_openness.py`, add `import math` at the top (line 5), then replace the `get_scores` method and add a helper:

```python
    def _confidence_level(self, archetype_name: str) -> str:
        """Determine confidence level based on signal count for an archetype."""
        count = sum(1 for s in self.signals if s["archetype"] == archetype_name)
        if count == 0:
            return "none"
        elif count < 5:
            return "low"
        elif count < 15:
            return "medium"
        else:
            return "high"

    def get_scores(self) -> Dict[str, dict]:
        """Get aggregated openness scores for all archetypes.

        Positive score = archetype is OPEN (cards wheeling later than ATA).
        Negative score = archetype is CLOSED (cards taken earlier than ATA).

        Returns dict of {archetype_name: {"score": float, "confidence": str, "interval": tuple|None}}.
        Archetypes with no signals return score 0.0, confidence "none".
        """
        if self.scoring_method == "bayesian_beta":
            return self._scores_bayesian_beta()
        return self._scores_simple()

    def _scores_simple(self) -> Dict[str, dict]:
        """Simple/normalized scoring — sum of signals, no credible interval."""
        scores = {}
        for arch in self.archetypes:
            total = sum(s["signal"] for s in self.signals if s["archetype"] == arch.name)
            scores[arch.name] = {
                "score": total,
                "confidence": self._confidence_level(arch.name),
                "interval": None,
            }
        return scores
```

This replaces the old `get_scores` (lines 198-210). Remove the old method entirely.

**Step 4: Run new shape tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestGetScoresReturnShape -v`
Expected: 3 PASSED.

**Step 5: Update all existing test assertions**

Every test that accesses `scores["Name"]` as a float must change to `scores["Name"]["score"]`. Here is the complete list:

In `TestOpennessTrackerSimple`:
- `test_single_card_positive_signal`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`
- `test_single_card_negative_signal`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`
- `test_multi_archetype_card`: both `scores["BG Elves"]` and `scores["UB Control"]` → `["score"]`
- `test_card_not_in_any_archetype`: both `scores["BG Elves"]` and `scores["UB Control"]` → `["score"]`
- `test_accumulation_across_packs`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`
- `test_pack_weights_applied`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`
- `test_reset_clears_signals`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`
- `test_empty_pack`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`

In `TestOpennessTrackerNormalized`:
- `test_normalized_scoring`: `scores["BG Elves"]` → `scores["BG Elves"]["score"]`
- `test_normalized_emphasizes_low_ata`: `scores["Test"]` → `scores["Test"]["score"]`
- `test_normalized_zero_ata_skipped`: `scores["Test"]` → `scores["Test"]["score"]`

In `TestEndToEnd`:
- `test_full_flow_with_real_data`: `any(s != 0.0 for s in scores.values())` → `any(s["score"] != 0.0 for s in scores.values())`
- `test_normalized_with_real_data`: no assertion on values, just `len(scores)` — no change needed

In `TestPickWeight`:
- `test_p1p1_normalized_produces_zero_signal`: `scores["Test"]` → `scores["Test"]["score"]`
- `test_late_pick_high_quality_card_strong_signal`: `scores["Test"]` → `scores["Test"]["score"]`

**Step 6: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All existing tests pass with the new return shape.

**Step 7: Update overlay.py to consume new return shape**

In `src/overlay.py`, method `__update_openness_panel` (lines 1631-1675), change:

Line 1641 — sorting: `sorted(scores.items(), key=lambda x: x[1], reverse=True)` → `sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)`

Line 1642 — max_score: `max(abs(s) for _, s in sorted_archetypes)` → `max(abs(s["score"]) for _, s in sorted_archetypes)`

Line 1646 — loop unpacking: `for i, (name, score) in enumerate(sorted_archetypes):` — score is now a dict.

Lines 1657, 1664, 1665 — score references:
- `text=f"{score:+.1f}"` → `text=f"{score['score']:+.1f}"`
- `bar_width = int(abs(score) / max_score * 80)` → `bar_width = int(abs(score["score"]) / max_score * 80)`
- `bar_color = "#4CAF50" if score > 0 else "#F44336" if score < 0 else "#888888"` → `bar_color = "#4CAF50" if score["score"] > 0 else "#F44336" if score["score"] < 0 else "#888888"`

**Step 8: Run all tests to confirm nothing broken**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

**Step 9: Commit**

```bash
git add src/archetype_openness.py src/overlay.py tests/test_archetype_openness.py
git commit -m "refactor: change get_scores return type to Dict[str, dict] with score/confidence/interval"
```

---

### Task 3: Implement Bayesian Beta scoring engine

This is the core task — the `_scores_bayesian_beta` method that computes P(open) per archetype using Beta posteriors. The card weight system is preserved: each signal's contribution to alpha/beta is weighted by the card's archetype affinity (`card_weight` from `archetype.cards[card_name]`) and by `pack_weight`.

**How card weights integrate:** When a card with weight 0.85 (strong archetype signal) appears late, it pushes alpha by `0.85 * abs(raw_signal)`. A card with weight 0.2 (weak archetype signal — the card appears in many decks) only pushes alpha by `0.2 * abs(raw_signal)`. This means archetype-specific cards have ~4x more influence on the posterior than generic cards, exactly as intended.

**Files:**
- Modify: `src/archetype_openness.py:133+` (OpennessTracker class)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write failing tests for Bayesian Beta scoring**

Add to `tests/test_archetype_openness.py`:

```python
BAYESIAN_CONFIG = ArchetypeConfig(
    set_code="TST",
    scoring_method="bayesian_beta",
    bayesian_prior=1.0,
    pack_weights=[1.0, 1.0, 1.0],
    archetypes=[
        Archetype(
            name="BG Elves",
            color_pair="BG",
            auto_weights=False,
            cards={
                "Elf Lord": 0.9,
                "Llanowar Elves": 0.5,
                "Murder": 0.2,
            },
        ),
        Archetype(
            name="UB Control",
            color_pair="UB",
            auto_weights=False,
            cards={
                "Murder": 0.7,
                "Counterspell": 0.8,
            },
        ),
    ],
)


class TestBayesianBetaScoring:
    """Tests for Bayesian (%) scoring with Beta posteriors."""

    def test_no_signals_returns_prior_mean(self):
        """With no signals, P(open) = prior / (2*prior) = 0.5."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.5)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_positive_signal_increases_probability(self):
        """Card seen later than ATA → P(open) > 0.5."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        # Elf Lord: ata=3.0, pick=7 → raw = (7-3) * 0.9 * 1.0 = 3.6 (positive)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] > 0.5

    def test_negative_signal_decreases_probability(self):
        """Card seen earlier than ATA → P(open) < 0.5."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        # Elf Lord: ata=7.0, pick=3 → raw = (3-7) * 0.9 * 1.0 = -3.6 (negative)
        tracker.record_pack([_make_card("Elf Lord", ata=7.0)], pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] < 0.5

    def test_exact_posterior_calculation(self):
        """Verify exact alpha/beta math for a known signal.

        Elf Lord: ata=3.0, pick=7, card_weight=0.9
        raw_signal = (7 - 3) * 0.9 * 1.0 = 3.6 (positive)
        alpha = 1.0 + 3.6 = 4.6
        beta = 1.0
        P(open) = 4.6 / (4.6 + 1.0) = 0.8214
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(4.6 / 5.6, abs=0.001)

    def test_card_weight_affects_magnitude(self):
        """Higher card_weight → stronger push on posterior.

        Murder in BG Elves has weight=0.2, in UB Control has weight=0.7.
        Same signal (pick=8, ata=4) should push UB Control more.
        raw = (8-4) = 4
        BG: alpha = 1.0 + 4*0.2 = 1.8, beta = 1.0 → P = 1.8/2.8 = 0.6429
        UB: alpha = 1.0 + 4*0.7 = 3.8, beta = 1.0 → P = 3.8/4.8 = 0.7917
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Murder", ata=4.0)], pick_number=8, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(1.8 / 2.8, abs=0.001)
        assert scores["UB Control"]["score"] == pytest.approx(3.8 / 4.8, abs=0.001)

    def test_mixed_signals_intermediate(self):
        """Positive then negative signals produce an intermediate value.

        Elf Lord pick=7 ata=3 → positive, raw=4*0.9=3.6 → alpha += 3.6
        Elf Lord pick=2 ata=5 → negative, raw=-3*0.9=2.7 → beta += 2.7
        alpha = 1.0 + 3.6 = 4.6, beta = 1.0 + 2.7 = 3.7
        P = 4.6 / 8.3 = 0.5542
        """
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        tracker.record_pack([_make_card("Elf Lord", ata=5.0)], pick_number=2, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(4.6 / 8.3, abs=0.001)

    def test_pack_weight_scales_signal(self):
        """Pack weight multiplies the signal contribution.

        Same card/pick but pack_weight=0.5 halves the contribution.
        Elf Lord pick=7 ata=3 → raw = (7-3) * 0.9 * 0.5 = 1.8
        alpha = 1.0 + 1.8 = 2.8, beta = 1.0 → P = 2.8/3.8 = 0.7368
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            bayesian_prior=1.0,
            pack_weights=[1.0, 0.5, 0.75],
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=1)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(2.8 / 3.8, abs=0.001)

    def test_prior_parameter_effect(self):
        """Larger prior pulls P(open) closer to 0.5.

        prior=5.0, same signal as test_exact:
        alpha = 5.0 + 3.6 = 8.6, beta = 5.0
        P = 8.6 / 13.6 = 0.6324  (closer to 0.5 than with prior=1.0)
        """
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_beta",
            bayesian_prior=5.0,
            archetypes=[Archetype(name="BG Elves", cards={"Elf Lord": 0.9})],
        )
        tracker = OpennessTracker(config)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(8.6 / 13.6, abs=0.001)

    def test_confidence_level_none(self):
        """Zero signals → confidence 'none'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "none"

    def test_confidence_level_low(self):
        """1-4 signals → confidence 'low'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "low"

    def test_confidence_level_medium(self):
        """5-14 signals → confidence 'medium'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        # Record 5 signals for BG Elves (Elf Lord appears in BG Elves)
        for i in range(5):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "medium"

    def test_confidence_level_high(self):
        """15+ signals → confidence 'high'."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        for i in range(15):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["BG Elves"]["confidence"] == "high"

    def test_interval_is_tuple(self):
        """Bayesian scoring provides a credible interval as a 2-tuple."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        interval = scores["BG Elves"]["interval"]
        assert interval is not None
        assert len(interval) == 2
        assert interval[0] < scores["BG Elves"]["score"] < interval[1]

    def test_interval_narrows_with_more_signals(self):
        """More signals → narrower credible interval."""
        tracker = OpennessTracker(BAYESIAN_CONFIG)
        tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores_early = tracker.get_scores()
        width_early = scores_early["BG Elves"]["interval"][1] - scores_early["BG Elves"]["interval"][0]

        for _ in range(10):
            tracker.record_pack([_make_card("Elf Lord", ata=3.0)], pick_number=7, pack_number=0)
        scores_late = tracker.get_scores()
        width_late = scores_late["BG Elves"]["interval"][1] - scores_late["BG Elves"]["interval"][0]

        assert width_late < width_early
```

**Step 2: Run to verify failure**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianBetaScoring -v`
Expected: FAIL — `_scores_bayesian_beta` not implemented (returns something wrong or raises).

**Step 3: Implement `_scores_bayesian_beta`**

In `src/archetype_openness.py`, add `import math` to the imports at line 5. Add `self.bayesian_prior = config.bayesian_prior` to `__init__` after `self.archetypes = config.archetypes` (line 140).

Then add the `_scores_bayesian_beta` method to the `OpennessTracker` class, right after `_scores_simple`:

```python
    def _scores_bayesian_beta(self) -> Dict[str, dict]:
        """Bayesian Beta scoring — P(open) as posterior mean with credible interval.

        For each archetype, signals are classified as positive (card seen later than ATA,
        archetype is open) or negative (card seen earlier than ATA, archetype is closed).
        Signal magnitude is weighted by card_weight (archetype affinity) and pack_weight,
        preserving the existing weight system.

        Returns {name: {"score": P(open), "confidence": str, "interval": (low, high)}}.
        """
        prior = self.bayesian_prior
        scores = {}

        for arch in self.archetypes:
            alpha = prior
            beta_param = prior

            for sig in self.signals:
                if sig["archetype"] != arch.name:
                    continue
                # Signal already incorporates card_weight and pack_weight
                # from record_pack: signal = raw * card_weight * pack_weight
                magnitude = abs(sig["signal"])
                if sig["signal"] > 0:
                    alpha += magnitude
                elif sig["signal"] < 0:
                    beta_param += magnitude

            total = alpha + beta_param
            p_open = alpha / total if total > 0 else 0.5

            # 95% credible interval approximation using Normal approximation to Beta
            variance = (alpha * beta_param) / (total * total * (total + 1))
            stderr = math.sqrt(variance) if variance > 0 else 0.0
            interval_low = max(0.0, p_open - 1.96 * stderr)
            interval_high = min(1.0, p_open + 1.96 * stderr)

            scores[arch.name] = {
                "score": p_open,
                "confidence": self._confidence_level(arch.name),
                "interval": (interval_low, interval_high),
            }

        return scores
```

**Step 4: Run Bayesian tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianBetaScoring -v`
Expected: All 14 tests PASSED.

**Step 5: Run full archetype test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All tests pass.

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: implement Bayesian Beta scoring with card-weight-aware posteriors"
```

---

### Task 4: Add "Bayesian (%)" to Archetype Editor dropdown

This task adds the new scoring method to the editor UI and shows a conditional "Prior:" spinbox when Bayesian is selected.

**Files:**
- Modify: `src/archetype_editor.py:154-179`

**Step 1: Update scoring dropdown values**

In `src/archetype_editor.py`, line 160-162, change the scoring combo values from `["simple", "normalized"]` to include `"bayesian_beta"`:

```python
        # Display name → internal value mapping
        self._scoring_display_map = {
            "Simple": "simple",
            "Weighted": "normalized",
            "Bayesian (%)": "bayesian_beta",
        }
        self._scoring_internal_map = {v: k for k, v in self._scoring_display_map.items()}

        ttk.Label(bottom_frame, text="Scoring:").pack(side=tkinter.LEFT)
        display_name = self._scoring_internal_map.get(self.config.scoring_method, "Simple")
        self.scoring_var = tkinter.StringVar(value=display_name)
        scoring_combo = ttk.Combobox(bottom_frame, textvariable=self.scoring_var,
                                      values=list(self._scoring_display_map.keys()), width=12, state="readonly")
        scoring_combo.pack(side=tkinter.LEFT, padx=4)
        scoring_combo.bind("<<ComboboxSelected>>", self._on_scoring_change)
```

**Step 2: Add conditional Prior spinbox and Curve combo**

After the scoring combo, add the conditional fields:

```python
        # Conditional fields frame
        self.conditional_frame = ttk.Frame(bottom_frame)
        self.conditional_frame.pack(side=tkinter.LEFT)

        # Prior field (shown for Bayesian)
        self.prior_frame = ttk.Frame(self.conditional_frame)
        ttk.Label(self.prior_frame, text="Prior:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.prior_var = tkinter.StringVar(value=str(self.config.bayesian_prior))
        ttk.Entry(self.prior_frame, textvariable=self.prior_var, width=5).pack(side=tkinter.LEFT, padx=2)

        # Curve field (shown for Weighted)
        self.curve_frame = ttk.Frame(self.conditional_frame)
        ttk.Label(self.curve_frame, text="Curve:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.weight_curve_var = tkinter.StringVar(value=self.config.weight_curve)
        curve_combo = ttk.Combobox(self.curve_frame, textvariable=self.weight_curve_var,
                                    values=["linear", "sqrt", "squared"], width=8, state="readonly")
        curve_combo.pack(side=tkinter.LEFT, padx=4)

        # Show correct conditional field on startup
        self._on_scoring_change()
```

**Step 3: Add the `_on_scoring_change` handler**

Add this method to the `ArchetypeEditor` class:

```python
    def _on_scoring_change(self, event=None):
        """Show/hide conditional fields based on selected scoring method."""
        display_name = self.scoring_var.get()
        internal = self._scoring_display_map.get(display_name, "simple")

        # Hide all conditional fields
        self.prior_frame.pack_forget()
        self.curve_frame.pack_forget()

        if internal == "bayesian_beta":
            self.prior_frame.pack(side=tkinter.LEFT)
        elif internal == "normalized":
            self.curve_frame.pack(side=tkinter.LEFT)
```

**Step 4: Update `_save` to persist new fields**

In the `_save` method (around line 358), update the scoring_method assignment to use the display→internal mapping, and add bayesian_prior persistence:

```python
        # Update global settings
        display_name = self.scoring_var.get()
        self.config.scoring_method = self._scoring_display_map.get(display_name, "simple")
        self.config.weight_curve = self.weight_curve_var.get()
        try:
            self.config.bayesian_prior = float(self.prior_var.get())
        except ValueError:
            self.config.bayesian_prior = 1.0
```

**Step 5: Remove the old standalone Curve label/combo**

The old curve combo (lines 164-168) is now inside `self.curve_frame`. Remove the old standalone `ttk.Label(bottom_frame, text="Curve:")` and its combobox since they've been replaced by the conditional frame approach.

**Step 6: Run all tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

**Step 7: Commit**

```bash
git add src/archetype_editor.py
git commit -m "feat: add Bayesian (%) scoring option to Archetype Editor with conditional Prior field"
```

---

### Task 5: Update overlay panel to display Bayesian (%) format with opacity

This task makes the overlay panel display P(open) as a percentage for Bayesian mode and applies opacity based on confidence.

**Files:**
- Modify: `src/overlay.py:1631-1675`

**Step 1: Update `__update_openness_panel` for method-aware display**

Replace the panel rendering logic to handle both score formats. The method needs to know the current scoring method, which can be read from `self.openness_tracker.scoring_method`.

In `src/overlay.py`, replace `__update_openness_panel` (lines 1631-1675):

```python
    def __update_openness_panel(self):
        """Update the archetype openness panel with current scores."""
        if not self.openness_tracker:
            return

        # Clear existing labels
        for widget in self.openness_frame.winfo_children():
            widget.destroy()

        scores = self.openness_tracker.get_scores()
        sorted_archetypes = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
        scoring_method = self.openness_tracker.scoring_method

        # Opacity map for confidence levels
        opacity_map = {"none": 0.4, "low": 0.6, "medium": 0.8, "high": 1.0}

        if scoring_method == "bayesian_beta":
            max_score = 1.0  # P(open) is always 0-1
        else:
            max_score = max(abs(s["score"]) for _, s in sorted_archetypes) if sorted_archetypes else 1.0
            if max_score == 0:
                max_score = 1.0

        for i, (name, data) in enumerate(sorted_archetypes):
            score = data["score"]
            confidence = data.get("confidence", "high")
            opacity = opacity_map.get(confidence, 1.0)

            # Compute foreground color with opacity
            fg_color = self._openness_fg_with_opacity(opacity)

            name_label = tkinter.Label(
                self.openness_frame,
                text=name,
                anchor=tkinter.W,
                width=15,
                fg=fg_color,
            )
            name_label.grid(row=i, column=0, sticky="w", padx=(4, 2))

            # Format score based on method
            if scoring_method == "bayesian_beta":
                score_text = f"{score * 100:.0f}%"
            else:
                score_text = f"{score:+.1f}"

            score_label = tkinter.Label(
                self.openness_frame,
                text=score_text,
                anchor=tkinter.E,
                width=6,
                fg=fg_color,
            )
            score_label.grid(row=i, column=1, padx=2)

            # Visual bar
            if scoring_method == "bayesian_beta":
                bar_width = int(score * 80)
                bar_color = self._openness_bayesian_bar_color(score)
            else:
                bar_width = int(abs(score) / max_score * 80) if max_score else 0
                bar_color = "#4CAF50" if score > 0 else "#F44336" if score < 0 else "#888888"

            bar_canvas = tkinter.Canvas(
                self.openness_frame, width=80, height=12, highlightthickness=0
            )
            bar_canvas.create_rectangle(0, 0, bar_width, 12, fill=bar_color, outline="")
            bar_canvas.grid(row=i, column=2, padx=(2, 4))

            # Tooltip binding for top contributors
            self.__bind_openness_tooltip(name_label, name)
            self.__bind_openness_tooltip(score_label, name)
            self.__bind_openness_tooltip(bar_canvas, name)
```

**Step 2: Add helper methods for opacity and bar color**

Add these two methods to the overlay class, near `__update_openness_panel`:

```python
    @staticmethod
    def _openness_fg_with_opacity(opacity: float) -> str:
        """Compute a foreground color with the given opacity (0-1) against a dark background.

        Blends white toward dark background. opacity=1.0 → white, opacity=0.4 → dim gray.
        """
        bg = 30  # dark background ~#1e1e1e
        fg = 255  # white text
        blended = int(bg + (fg - bg) * opacity)
        return f"#{blended:02x}{blended:02x}{blended:02x}"

    @staticmethod
    def _openness_bayesian_bar_color(p_open: float) -> str:
        """Color for Bayesian bar: green > 0.5, red < 0.5, gray at 0.5."""
        if p_open > 0.55:
            return "#4CAF50"
        elif p_open < 0.45:
            return "#F44336"
        else:
            return "#888888"
```

**Step 3: Run all tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All tests pass.

**Step 4: Commit**

```bash
git add src/overlay.py
git commit -m "feat: display Bayesian P(open) as percentage with confidence opacity in overlay"
```

---

### Task 6: Integration test with real dataset

This task adds an end-to-end test using the real OTJ dataset to verify Bayesian scoring works through the full data flow.

**Files:**
- Modify: `tests/test_archetype_openness.py`

**Step 1: Write integration test**

Add to the `TestEndToEnd` class:

```python
    def test_bayesian_with_real_data(self, otj_dataset):
        """Bayesian scoring with real OTJ data produces valid probabilities."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="bayesian_beta",
            bayesian_prior=1.0,
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        tracker.record_pack(pack_cards, pick_number=5, pack_number=0)

        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)
        for name, data in scores.items():
            assert 0.0 <= data["score"] <= 1.0
            assert data["confidence"] in ("none", "low", "medium", "high")
            if data["interval"] is not None:
                assert data["interval"][0] <= data["score"] <= data["interval"][1]
```

**Step 2: Run the integration test**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestEndToEnd::test_bayesian_with_real_data -v`
Expected: PASSED.

**Step 3: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All tests pass (no regressions).

**Step 4: Commit**

```bash
git add tests/test_archetype_openness.py
git commit -m "test: add Bayesian integration test with real OTJ data"
```

---

## Files Modified Summary

| File | Change |
|------|--------|
| `src/archetype_openness.py` | Add `bayesian_prior` field, `import math`, `_confidence_level` helper, change `get_scores` return type, add `_scores_simple` and `_scores_bayesian_beta` methods, store `self.bayesian_prior` in `__init__` |
| `src/overlay.py` | Update `__update_openness_panel` for dict scores, Bayesian % display, opacity, two new static helper methods |
| `src/archetype_editor.py` | Display↔internal name mapping, expand scoring dropdown, conditional Prior/Curve fields, `_on_scoring_change` handler |
| `tests/test_archetype_openness.py` | Add `TestGetScoresReturnShape` (3 tests), `TestBayesianConfig` (3 tests), `TestBayesianBetaScoring` (14 tests), 1 integration test, update ~15 existing assertions |

## Verification Checklist

- [ ] `bayesian_prior` field persists through save/load
- [ ] Old config files without `bayesian_prior` load with default 1.0
- [ ] `get_scores()` returns `Dict[str, dict]` for all methods
- [ ] Bayesian P(open) is bounded 0-1
- [ ] Card weights correctly scale signal magnitude in posteriors
- [ ] Confidence levels match signal count thresholds
- [ ] Credible intervals narrow with more signals
- [ ] Overlay displays `XX%` for Bayesian, `+X.X` for simple/normalized
- [ ] Opacity gradient visible in overlay (dim → bright)
- [ ] Editor dropdown shows friendly names, persists internal values
- [ ] Prior spinbox appears only for Bayesian mode
- [ ] Curve dropdown appears only for Weighted mode
- [ ] All existing tests pass with updated assertions
- [ ] Full test suite passes (312+ tests)
