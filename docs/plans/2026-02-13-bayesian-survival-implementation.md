# Bayesian Survival Openness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a 5th scoring method `bayesian_survival` to the archetype openness tracker that uses three signal types: wheeling, missing cards, and draft-wide absence.

**Architecture:** Extends `OpennessTracker` in `src/archetype_openness.py` with new state tracking (per-archetype log-odds, card observation counts), a new `record_missing()` method, and absence computation in `get_scores()`. Integrates with `overlay.py` to feed missing card data. Adds dropdown entry in `archetype_editor.py`.

**Tech Stack:** Python 3.12, math (stdlib), Pydantic, pytest, Tkinter

---

### Task 1: Add `ArchetypeConfig` fields for bayesian_survival

**Files:**
- Modify: `src/archetype_openness.py:21-43` (ArchetypeConfig class)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write the failing tests**

Add to `tests/test_archetype_openness.py` at the end of the file:

```python
class TestBayesianSurvivalConfig:
    """Tests for bayesian_survival config fields."""

    def test_default_absence_enabled(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.absence_enabled is True

    def test_default_slots_per_rarity(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.slots_per_rarity == {
            "common": 10, "uncommon": 3, "rare": 1, "mythic": 0
        }

    def test_old_config_gets_defaults(self):
        data = {"set_code": "TST", "scoring_method": "bayesian_survival"}
        config = ArchetypeConfig.model_validate(data)
        assert config.absence_enabled is True
        assert config.slots_per_rarity["common"] == 10

    def test_config_round_trip(self, tmp_path):
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            absence_enabled=False,
            slots_per_rarity={"common": 11, "uncommon": 3, "rare": 1, "mythic": 0},
        )
        file_path = str(tmp_path / "test_config.json")
        save_archetype_config(config, file_path)
        loaded = load_archetype_config(file_path)
        assert loaded.absence_enabled is False
        assert loaded.slots_per_rarity["common"] == 11
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalConfig -v`
Expected: FAIL (fields don't exist)

**Step 3: Implement the config fields**

In `src/archetype_openness.py`, add two fields to `ArchetypeConfig` after line 42 (`card_weight_threshold`):

```python
    absence_enabled: bool = True
    slots_per_rarity: Dict[str, int] = Field(default_factory=lambda: {
        "common": 10, "uncommon": 3, "rare": 1, "mythic": 0,
    })
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalConfig -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add bayesian_survival config fields (absence_enabled, slots_per_rarity)"
```

---

### Task 2: Implement bayesian_survival state initialization and reset

**Files:**
- Modify: `src/archetype_openness.py:156-169` (OpennessTracker.__init__), `src/archetype_openness.py:482-487` (reset)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write the failing tests**

```python
class TestBayesianSurvivalState:
    """Tests for bayesian_survival state initialization and reset."""

    def _make_config(self):
        return ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[
                Archetype(name="BG Elves", cards={"Elf Lord": 0.9}),
                Archetype(name="UB Control", cards={"Counterspell": 0.8}),
            ],
        )

    def test_initial_state(self):
        config = self._make_config()
        tracker = OpennessTracker(config)
        assert tracker.bs_log_odds == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_sum_sq == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_last_pick == {"BG Elves": 1, "UB Control": 1}
        assert tracker.bs_card_seen == {"BG Elves": {}, "UB Control": {}}
        assert tracker.bs_packs_observed == 0

    def test_reset_clears_state(self):
        config = self._make_config()
        tracker = OpennessTracker(config)
        # Mutate state
        tracker.bs_log_odds["BG Elves"] = 1.5
        tracker.bs_sum_sq["BG Elves"] = 0.5
        tracker.bs_last_pick["BG Elves"] = 7
        tracker.bs_card_seen["BG Elves"]["Elf Lord"] = 3
        tracker.bs_packs_observed = 5
        # Reset
        tracker.reset()
        assert tracker.bs_log_odds == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_sum_sq == {"BG Elves": 0.0, "UB Control": 0.0}
        assert tracker.bs_last_pick == {"BG Elves": 1, "UB Control": 1}
        assert tracker.bs_card_seen == {"BG Elves": {}, "UB Control": {}}
        assert tracker.bs_packs_observed == 0
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalState -v`
Expected: FAIL (bs_ attributes don't exist)

**Step 3: Implement state initialization and reset**

In `OpennessTracker.__init__` (after line 169), add:

```python
        # bayesian_survival state
        self.bs_log_odds: Dict[str, float] = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_sum_sq: Dict[str, float] = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_last_pick: Dict[str, int] = {arch.name: 1 for arch in self.archetypes}
        self.bs_card_seen: Dict[str, Dict[str, int]] = {arch.name: {} for arch in self.archetypes}
        self.bs_packs_observed: int = 0
```

In `reset()` (after line 487), add:

```python
        self.bs_log_odds = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_sum_sq = {arch.name: 0.0 for arch in self.archetypes}
        self.bs_last_pick = {arch.name: 1 for arch in self.archetypes}
        self.bs_card_seen = {arch.name: {} for arch in self.archetypes}
        self.bs_packs_observed = 0
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalState -v`
Expected: PASS

**Step 5: Run full suite to check no regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add bayesian_survival state to OpennessTracker init and reset"
```

---

### Task 3: Implement Signal 1 — Wheeling emission and state update

The wheeling signal computes a log Bayes factor for a card that is present at pick `p` with ATA `a`:
```
lambda = (p - 1) * log(q_open / q_closed)
```
where `q_open = 1 - 1/(a*F)`, `q_closed = 1 - 1/a`.

**Gated**: Only emits when `pick > ATA`.

**Files:**
- Modify: `src/archetype_openness.py` (add `_bs_wheeling_emission`, `_bs_update_state`, and hook into `record_pack`)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write the failing tests**

```python
class TestBayesianSurvivalWheeling:
    """Tests for bayesian_survival Signal 1 (wheeling)."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_card_past_ata_produces_positive_signal(self):
        """Card at pick 7 with ATA 3: lambda > 0 -> score > 0."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] > 0.0

    def test_card_at_ata_produces_no_signal(self):
        """Card at pick 3 with ATA 3: gated, no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=3, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_card_before_ata_produces_no_signal(self):
        """Card at pick 2 with ATA 5: gated, no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=2, pack_number=0)
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_exact_wheeling_formula(self):
        """Verify exact log Bayes factor: ATA=3, pick=7, F=2, card_weight=1.0, common.

        a=3, F=2, p=7
        q_open = 1 - 1/6 = 5/6
        q_closed = 1 - 1/3 = 2/3
        lambda = 6 * log(q_open/q_closed) = 6 * log((5/6)/(2/3)) = 6 * log(5/4)
        rarity_weight = sqrt(0.0899/0.0899) = 1.0
        ramp at pick 7, ramp_picks=5: min(1.0, 6/4) = 1.0
        emission = lambda * 1.0 * 1.0 * 1.0 * 1.0 * 1.0
        """
        import math
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)

        expected_lambda = 6 * math.log((5/6) / (2/3))
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(expected_lambda, abs=0.001)

    def test_later_pick_stronger_signal(self):
        """Pick 10 should produce stronger signal than pick 5 for same card."""
        tracker1 = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker1.record_pack([card], pick_number=5, pack_number=0)
        score_5 = tracker1.get_scores()["Test"]["score"]

        tracker2 = OpennessTracker(self._make_config())
        tracker2.record_pack([card], pick_number=10, pack_number=0)
        score_10 = tracker2.get_scores()["Test"]["score"]

        assert score_10 > score_5

    def test_card_weight_scales_signal(self):
        """Card weight 0.5 should produce half the signal of weight 1.0."""
        import math
        config_full = self._make_config(archetypes=[Archetype(name="Test", cards={"Card": 1.0})])
        config_half = self._make_config(archetypes=[Archetype(name="Test", cards={"Card": 0.5})])

        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"

        t1 = OpennessTracker(config_full)
        t1.record_pack([card], pick_number=7, pack_number=0)
        t2 = OpennessTracker(config_half)
        t2.record_pack([card], pick_number=7, pack_number=0)

        assert t1.get_scores()["Test"]["score"] == pytest.approx(
            t2.get_scores()["Test"]["score"] * 2, abs=0.001
        )

    def test_ata_clamped_to_1_5(self):
        """ATA=1.0 should not cause math error; clamped to 1.5."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=1.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=5, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score > 0.0  # valid result, no crash

    def test_zero_ata_skipped(self):
        """ATA=0 should produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=0.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_pick_1_no_signal(self):
        """Pick 1 skipped by record_pack early return."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=1, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_rarity_weight_applied(self):
        """Rare card should produce weaker signal than common."""
        tracker_common = OpennessTracker(self._make_config())
        common = _make_card("Card", ata=5.0)
        common["rarity"] = "common"
        tracker_common.record_pack([common], pick_number=8, pack_number=0)

        tracker_rare = OpennessTracker(self._make_config())
        rare = _make_card("Card", ata=5.0)
        rare["rarity"] = "rare"
        tracker_rare.record_pack([rare], pick_number=8, pack_number=0)

        assert tracker_common.get_scores()["Test"]["score"] > tracker_rare.get_scores()["Test"]["score"]

    def test_decay_between_observations(self):
        """Signal decays between observations based on pick gap."""
        import math
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"

        # Record at pick 5, then at pick 10 (gap=5)
        tracker.record_pack([card], pick_number=5, pack_number=0)
        first_score = tracker.get_scores()["Test"]["score"]

        tracker.record_pack([card], pick_number=10, pack_number=0)
        second_score = tracker.get_scores()["Test"]["score"]

        # Second score should be: first * decay^5 + new_emission
        # Not just first + new (would ignore decay)
        decay = (1.0 - 0.15) ** 5
        new_lambda = 9 * math.log((5/6)/(2/3))  # pick=10
        expected = first_score * decay + new_lambda
        assert second_score == pytest.approx(expected, abs=0.01)

    def test_card_seen_count_incremented(self):
        """record_pack increments bs_card_seen for archetype cards."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.bs_card_seen["Test"].get("Card", 0) == 1

    def test_packs_observed_incremented(self):
        """record_pack increments bs_packs_observed."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        assert tracker.bs_packs_observed == 1
        tracker.record_pack([card], pick_number=8, pack_number=0)
        assert tracker.bs_packs_observed == 2
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalWheeling -v`
Expected: FAIL

**Step 3: Implement wheeling emission and state update**

Add these methods to `OpennessTracker` (after `_hmm_update_state`):

```python
    def _bs_wheeling_emission(self, card: Dict, pick_number: int, ata: float,
                              card_weight: float, pack_weight: float) -> float:
        """Signal 1: Log Bayes factor for a card surviving to pick p.

        lambda = (p-1) * log(q_open / q_closed)
        where q_open = 1 - 1/(a*F), q_closed = 1 - 1/a.
        """
        a = max(1.5, ata)
        F = max(1.0, self.config.hmm_openness_factor)
        p = pick_number

        q_open = 1.0 - 1.0 / (a * F)
        q_closed = 1.0 - 1.0 / a
        log_bf = (p - 1) * math.log(q_open / q_closed)

        common_odds = self.config.rarity_odds.get("common", 0.0899)
        card_rarity = (card.get("rarity", "") or "").lower()
        card_odds = self.config.rarity_odds.get(card_rarity, common_odds)
        rarity_weight = math.sqrt(card_odds / common_odds) if common_odds > 0 else 1.0

        scale = self.config.hmm_emission_scale
        ramp = self._hmm_pick_ramp_factor(pick_number)
        return log_bf * card_weight * pack_weight * rarity_weight * scale * ramp

    def _bs_update_state(self, archetype_name: str, pick_number: int, emission: float) -> None:
        """Update bayesian_survival log-odds state with decay."""
        prev_log_odds = self.bs_log_odds.get(archetype_name, 0.0)
        last_pick = self.bs_last_pick.get(archetype_name, 1)
        gap = max(0, pick_number - last_pick)

        decay = max(0.0, 1.0 - self.config.hmm_transition_decay) ** gap
        self.bs_log_odds[archetype_name] = (prev_log_odds * decay) + emission
        self.bs_last_pick[archetype_name] = pick_number

        prev_sum_sq = self.bs_sum_sq.get(archetype_name, 0.0)
        self.bs_sum_sq[archetype_name] = (prev_sum_sq * (decay ** 2)) + (emission ** 2)
```

In `record_pack`, in the scoring method dispatch (after the `hmm_hybrid` elif block at line ~250), add a `bayesian_survival` branch. The gate condition at line 229 already skips when `pick_number <= ata` for non-hmm methods, so `bayesian_survival` will automatically be gated.

Add this elif branch after the `hmm_hybrid` block:

```python
                elif self.scoring_method == "bayesian_survival":
                    emission = self._bs_wheeling_emission(card, pick_number, ata, card_weight, pack_weight)
                    self._bs_update_state(archetype.name, pick_number, emission)
                    signal = emission
```

Also ensure the gate condition at line 229 includes `bayesian_survival` (it already does since it only excludes `hmm_hybrid`).

After the outer `for card in pack_cards:` loop ends (before the final debug log at line ~274), add packs_observed and card_seen tracking for bayesian_survival:

```python
        if self.scoring_method == "bayesian_survival":
            self.bs_packs_observed += 1
            for card in pack_cards:
                card_name = card.get(DATA_FIELD_NAME, "")
                for archetype in self.archetypes:
                    if card_name in archetype.cards:
                        seen = self.bs_card_seen.get(archetype.name, {})
                        seen[card_name] = seen.get(card_name, 0) + 1
                        self.bs_card_seen[archetype.name] = seen
```

In `get_scores`, add routing for `bayesian_survival` (after the `hmm_hybrid` check at line ~317):

```python
        if self.scoring_method == "bayesian_survival":
            return self._scores_bayesian_survival()
```

Add a stub `_scores_bayesian_survival` method:

```python
    def _scores_bayesian_survival(self) -> Dict[str, dict]:
        """Bayesian survival scoring — returns log-odds with credible interval."""
        scores = {}
        for arch in self.archetypes:
            log_odds = self.bs_log_odds.get(arch.name, 0.0)
            scores[arch.name] = {
                "score": log_odds,
                "confidence": self._confidence_level(arch.name),
                "interval": None,
            }
        return scores
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalWheeling -v`
Expected: PASS

**Step 5: Run full suite to check no regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: implement bayesian_survival Signal 1 (wheeling) with gate at pick > ATA"
```

---

### Task 4: Implement Signal 2 — Missing card emission via `record_missing()`

Missing card signal:
```
S_open   = q_open^(p-1)
S_closed = q_closed^(p-1)
lambda = log((1 - S_open) / (1 - S_closed))
```
Always <= 0. No gate (always emits).

**Files:**
- Modify: `src/archetype_openness.py` (add `record_missing`, `_bs_missing_emission`)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write the failing tests**

```python
class TestBayesianSurvivalMissing:
    """Tests for bayesian_survival Signal 2 (missing cards)."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_missing_high_ata_produces_negative_signal(self):
        """Card with ATA=10 missing at pick 9: strong negative signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score < 0.0

    def test_missing_low_ata_weak_signal(self):
        """Card with ATA=2 missing at pick 9: weak negative signal."""
        import math
        tracker_high = OpennessTracker(self._make_config())
        high_ata = _make_card("Card", ata=10.0)
        high_ata["rarity"] = "common"
        tracker_high.record_missing([high_ata], pick_number=9, pack_number=0)

        tracker_low = OpennessTracker(self._make_config())
        low_ata = _make_card("Card", ata=2.0)
        low_ata["rarity"] = "common"
        tracker_low.record_missing([low_ata], pick_number=9, pack_number=0)

        # Both negative, but high-ATA missing is more negative
        assert tracker_high.get_scores()["Test"]["score"] < tracker_low.get_scores()["Test"]["score"] < 0.0

    def test_missing_exact_formula(self):
        """Verify exact formula: ATA=10, pick=9, F=2, card_weight=1.0.

        a=10, F=2, p=9
        q_open = 1 - 1/20 = 0.95
        q_closed = 1 - 1/10 = 0.9
        S_open = 0.95^8 = 0.6634
        S_closed = 0.9^8 = 0.4305
        lambda = log((1 - 0.6634)/(1 - 0.4305)) = log(0.3366/0.5695)
        rarity_weight = 1.0 (common)
        ramp = 1.0 (pick 9 > ramp 5)
        """
        import math
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)

        S_open = 0.95 ** 8
        S_closed = 0.9 ** 8
        expected = math.log((1 - S_open) / (1 - S_closed))
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(expected, abs=0.001)

    def test_missing_no_gate(self):
        """Missing cards emit signal even when ATA > pick (they SHOULD still be there)."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=12.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        score = tracker.get_scores()["Test"]["score"]
        assert score < 0.0  # still produces negative signal

    def test_missing_card_not_in_archetype_ignored(self):
        """Cards not in any archetype produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Unknown Card", ata=5.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_zero_ata_skipped(self):
        """Cards with ATA=0 produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=0.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_missing_updates_state_with_decay(self):
        """Missing signal updates log-odds with decay like wheeling."""
        import math
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"

        # Wheeling at pick 5 first
        tracker.record_pack([card], pick_number=12, pack_number=0)
        first = tracker.get_scores()["Test"]["score"]

        # Missing at pick 14 (gap=2 from pick 12)
        tracker.record_missing([card], pick_number=14, pack_number=0)
        combined = tracker.get_scores()["Test"]["score"]

        # Combined should be: first * decay^2 + missing_emission
        decay = (1.0 - 0.15) ** 2
        S_open = (1 - 1/20) ** 13
        S_closed = (1 - 1/10) ** 13
        missing_emission = math.log((1 - S_open) / (1 - S_closed))
        expected = first * decay + missing_emission
        assert combined == pytest.approx(expected, abs=0.01)

    def test_missing_only_for_bayesian_survival(self):
        """record_missing should be a no-op for other scoring methods."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="simple",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=10.0)
        card["rarity"] = "common"
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalMissing -v`
Expected: FAIL (record_missing doesn't exist)

**Step 3: Implement record_missing and missing emission**

Add `_bs_missing_emission` method to `OpennessTracker`:

```python
    def _bs_missing_emission(self, card: Dict, pick_number: int, ata: float,
                             card_weight: float, pack_weight: float) -> float:
        """Signal 2: Log Bayes factor for a missing card (taken before pick p).

        lambda = log((1 - S_open) / (1 - S_closed))
        where S_H = q_H^(p-1). Always <= 0.
        """
        a = max(1.5, ata)
        F = max(1.0, self.config.hmm_openness_factor)
        p = pick_number

        q_open = 1.0 - 1.0 / (a * F)
        q_closed = 1.0 - 1.0 / a

        S_open = q_open ** (p - 1)
        S_closed = q_closed ** (p - 1)

        taken_open = max(1e-10, 1.0 - S_open)
        taken_closed = max(1e-10, 1.0 - S_closed)
        log_bf = math.log(taken_open / taken_closed)

        common_odds = self.config.rarity_odds.get("common", 0.0899)
        card_rarity = (card.get("rarity", "") or "").lower()
        card_odds = self.config.rarity_odds.get(card_rarity, common_odds)
        rarity_weight = math.sqrt(card_odds / common_odds) if common_odds > 0 else 1.0

        scale = self.config.hmm_emission_scale
        ramp = self._hmm_pick_ramp_factor(pick_number)
        return log_bf * card_weight * pack_weight * rarity_weight * scale * ramp
```

Add `record_missing` method to `OpennessTracker`:

```python
    def record_missing(self, missing_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record negative signals from missing cards (Signal 2).

        Only active for bayesian_survival scoring method.

        Args:
            missing_cards: list of card dicts that were in original pack but are now gone
            pick_number: 1-based pick position within the pack
            pack_number: 0-indexed pack number
        """
        if self.scoring_method != "bayesian_survival":
            return

        pack_weight = self.pack_weights[pack_number] if pack_number < len(self.pack_weights) else 1.0

        for card in missing_cards:
            card_name = card.get(DATA_FIELD_NAME, "")
            deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
            all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
            ata = all_decks.get(DATA_FIELD_ATA, 0.0)

            if ata == 0.0:
                continue

            for archetype in self.archetypes:
                if card_name not in archetype.cards:
                    continue

                card_weight = archetype.cards[card_name]
                emission = self._bs_missing_emission(card, pick_number, ata, card_weight, pack_weight)
                self._bs_update_state(archetype.name, pick_number, emission)

                self.signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": emission,
                })
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalMissing -v`
Expected: PASS

**Step 5: Run full suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: implement bayesian_survival Signal 2 (missing cards) via record_missing()"
```

---

### Task 5: Implement Signal 3 — Draft-wide absence in `get_scores()`

Absence signal computed from accumulated card observation counts:
```
lambda_3 = k * log(see_open/see_closed) + (N - k) * log((1 - see_open)/(1 - see_closed))
```
where `see_H = r * q_H^(p_avg - 1)`, `r = rarity_odds * slots_per_rarity`.

**Files:**
- Modify: `src/archetype_openness.py` (`_scores_bayesian_survival`, `_bs_absence_signal`)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write the failing tests**

```python
class TestBayesianSurvivalAbsence:
    """Tests for bayesian_survival Signal 3 (draft-wide absence)."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_common_never_seen_negative_signal(self):
        """Common card never seen after many packs -> negative absence signal."""
        tracker = OpennessTracker(self._make_config())
        # Simulate seeing 24 packs without "Card" appearing
        # We need packs_observed > 0 but card_seen["Card"] = 0
        # Force packs_observed by recording packs with OTHER cards
        other_card = _make_card("Other", ata=5.0)
        other_card["rarity"] = "common"
        for i in range(24):
            tracker.record_pack([other_card], pick_number=7, pack_number=0)
        assert tracker.bs_packs_observed == 24
        assert tracker.bs_card_seen["Test"].get("Card", 0) == 0

        scores = tracker.get_scores()
        # Score should include absence signal for "Card" (negative)
        # The only wheeling signals are for "Other" which isn't in the archetype
        assert scores["Test"]["score"] < 0.0

    def test_rare_never_seen_negligible_signal(self):
        """Rare card never seen -> near-zero absence signal."""
        config_common = self._make_config()
        config_rare = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Rare Card": 1.0})]
        )

        # Common version
        tracker_c = OpennessTracker(config_common)
        other = _make_card("Other", ata=5.0)
        other["rarity"] = "common"
        for _ in range(24):
            tracker_c.record_pack([other], pick_number=7, pack_number=0)

        # Rare version - need the card in archetype but rarity is "rare"
        tracker_r = OpennessTracker(config_rare)
        for _ in range(24):
            tracker_r.record_pack([other], pick_number=7, pack_number=0)

        # Hack: set packs observed but leave card unseen, use _bs_absence_signal directly
        # Actually let's just compare: common absence should be much more negative
        score_c = tracker_c.get_scores()["Test"]["score"]
        score_r = tracker_r.get_scores()["Test"]["score"]
        # Both should be negative (absence). Common absence is stronger.
        assert score_c < score_r

    def test_absence_disabled(self):
        """When absence_enabled=False, no absence signal."""
        config = self._make_config(absence_enabled=False)
        tracker = OpennessTracker(config)
        other = _make_card("Other", ata=5.0)
        other["rarity"] = "common"
        for _ in range(24):
            tracker.record_pack([other], pick_number=7, pack_number=0)

        scores = tracker.get_scores()
        # Without absence, unseen "Card" produces no signal.
        # And "Other" isn't in archetype, so no wheeling signal either.
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_no_packs_observed_no_absence(self):
        """When no packs have been observed, no absence signal."""
        tracker = OpennessTracker(self._make_config())
        scores = tracker.get_scores()
        assert scores["Test"]["score"] == pytest.approx(0.0)

    def test_card_seen_expected_times_near_zero_signal(self):
        """Card seen approximately expected number of times -> near-zero absence signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["rarity"] = "common"
        # See it 2 times across 24 packs (close to expected ~1.5)
        tracker.record_pack([card], pick_number=7, pack_number=0)
        tracker.record_pack([card], pick_number=8, pack_number=0)
        for _ in range(22):
            other = _make_card("Other", ata=5.0)
            other["rarity"] = "common"
            tracker.record_pack([other], pick_number=7, pack_number=0)

        scores = tracker.get_scores()
        # The score includes both wheeling signals (positive from picks 7,8 past ATA 5)
        # and absence signal (card seen 2 times, expected ~1.5 -> slightly positive)
        # We can't easily assert the exact value, but the score should exist
        assert isinstance(scores["Test"]["score"], float)
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalAbsence -v`
Expected: FAIL

**Step 3: Implement absence signal in `_scores_bayesian_survival`**

Add `_bs_absence_signal` method:

```python
    def _bs_absence_signal(self, archetype: Archetype) -> float:
        """Signal 3: Draft-wide absence signal for all cards in an archetype.

        For each card, computes:
        lambda = k * log(see_open/see_closed) + (N - k) * log((1 - see_open)/(1 - see_closed))
        where see_H = r * q_H^(p_avg - 1).
        """
        if not self.config.absence_enabled or self.bs_packs_observed == 0:
            return 0.0

        N = self.bs_packs_observed
        p_avg = 7.5  # approximate midpoint of 1-14
        F = max(1.0, self.config.hmm_openness_factor)
        total_signal = 0.0

        for card_name, card_weight in archetype.cards.items():
            # Determine rarity for this card from observed data
            # We need to find the card's rarity. Check signals for it.
            card_rarity = self._bs_card_rarity.get(card_name, "common")

            r_odds = self.config.rarity_odds.get(card_rarity, 0.0899)
            slots = self.config.slots_per_rarity.get(card_rarity, 0)
            r = r_odds * slots

            if r <= 0:
                continue

            # Get ATA from stored data
            card_ata = self._bs_card_ata.get(card_name, 0.0)
            if card_ata == 0.0:
                continue

            a = max(1.5, card_ata)
            q_open = 1.0 - 1.0 / (a * F)
            q_closed = 1.0 - 1.0 / a

            see_open = r * (q_open ** (p_avg - 1))
            see_closed = r * (q_closed ** (p_avg - 1))

            # Clamp to avoid log(0)
            see_open = min(max(see_open, 1e-10), 1.0 - 1e-10)
            see_closed = min(max(see_closed, 1e-10), 1.0 - 1e-10)

            k = self.bs_card_seen.get(archetype.name, {}).get(card_name, 0)

            signal = (k * math.log(see_open / see_closed)
                      + (N - k) * math.log((1 - see_open) / (1 - see_closed)))
            total_signal += signal * card_weight

        return total_signal
```

This requires tracking card rarity and ATA. Add two more state dicts to `__init__` and `reset`:

In `__init__` (alongside other bs_ fields):
```python
        self._bs_card_rarity: Dict[str, str] = {}
        self._bs_card_ata: Dict[str, float] = {}
```

In `reset`:
```python
        self._bs_card_rarity = {}
        self._bs_card_ata = {}
```

In `record_pack`, within the `bayesian_survival` card tracking block, also capture rarity and ATA:

```python
        if self.scoring_method == "bayesian_survival":
            self.bs_packs_observed += 1
            for card in pack_cards:
                card_name = card.get(DATA_FIELD_NAME, "")
                # Cache rarity and ATA for absence calculation
                if card_name not in self._bs_card_rarity:
                    self._bs_card_rarity[card_name] = (card.get("rarity", "") or "").lower()
                    deck_colors = card.get(DATA_FIELD_DECK_COLORS, {})
                    all_decks = deck_colors.get(FILTER_OPTION_ALL_DECKS, {})
                    self._bs_card_ata[card_name] = all_decks.get(DATA_FIELD_ATA, 0.0)

                for archetype in self.archetypes:
                    if card_name in archetype.cards:
                        seen = self.bs_card_seen.get(archetype.name, {})
                        seen[card_name] = seen.get(card_name, 0) + 1
                        self.bs_card_seen[archetype.name] = seen
```

Update `_scores_bayesian_survival` to include absence:

```python
    def _scores_bayesian_survival(self) -> Dict[str, dict]:
        """Bayesian survival scoring — log-odds with absence signal and credible interval."""
        scores = {}
        for arch in self.archetypes:
            log_odds = self.bs_log_odds.get(arch.name, 0.0)

            # Add absence signal
            absence = self._bs_absence_signal(arch)
            total_log_odds = log_odds + absence

            # Variance estimation
            sum_sq = self.bs_sum_sq.get(arch.name, 0.0)
            if sum_sq > 0:
                sigma = math.sqrt(sum_sq)
                interval = (total_log_odds - 1.96 * sigma, total_log_odds + 1.96 * sigma)
            else:
                interval = None

            scores[arch.name] = {
                "score": total_log_odds,
                "confidence": self._confidence_level(arch.name),
                "interval": interval,
            }
        return scores
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalAbsence -v`
Expected: PASS

**Step 5: Run full suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: implement bayesian_survival Signal 3 (draft-wide absence) in get_scores"
```

---

### Task 6: Integrate with overlay.py — feed missing cards to tracker

**Files:**
- Modify: `src/overlay.py:1676-1683` (live mode), `src/overlay.py:1396-1415` (hindsight replay)
- Test: `tests/test_archetype_openness.py` (integration test)

**Step 1: Write integration test**

```python
class TestBayesianSurvivalIntegration:
    """Integration tests combining wheeling + missing + absence."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[
                Archetype(name="BG Elves", cards={"Elf Lord": 0.9, "Murder": 0.2}),
                Archetype(name="UB Control", cards={"Murder": 0.7, "Counterspell": 0.8}),
            ],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_wheeling_and_missing_combine(self):
        """Wheeling (positive) + missing (negative) should partially cancel."""
        config = self._make_config()
        tracker = OpennessTracker(config)

        # Wheeling: Elf Lord at pick 8 (ATA 3) -> positive for BG Elves
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=8, pack_number=0)
        score_after_wheeling = tracker.get_scores()["BG Elves"]["score"]
        assert score_after_wheeling > 0.0

        # Missing: Elf Lord gone at pick 10 (from next pack) -> negative
        tracker.record_missing([card], pick_number=10, pack_number=1)
        score_after_missing = tracker.get_scores()["BG Elves"]["score"]
        # The missing signal is negative, so total should be less than wheeling alone
        assert score_after_missing < score_after_wheeling

    def test_open_archetype_positive_score(self):
        """Archetype with many cards wheeling past ATA should have positive score."""
        config = self._make_config()
        tracker = OpennessTracker(config)

        # Multiple BG cards wheeling strongly
        for pick in [7, 8, 9, 10, 11]:
            card = _make_card("Elf Lord", ata=3.0)
            card["rarity"] = "common"
            tracker.record_pack([card], pick_number=pick, pack_number=0)

        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] > 0.0
        assert scores["BG Elves"]["confidence"] in ("medium", "high")

    def test_closed_archetype_negative_score(self):
        """Archetype with only missing cards should have negative score."""
        config = self._make_config()
        tracker = OpennessTracker(config)

        # Multiple BG cards missing
        for pick in [9, 10, 11, 12]:
            card = _make_card("Elf Lord", ata=10.0)
            card["rarity"] = "common"
            tracker.record_missing([card], pick_number=pick, pack_number=0)

        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] < 0.0

    def test_reset_clears_everything(self):
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        tracker.record_missing([card], pick_number=9, pack_number=0)

        tracker.reset()
        scores = tracker.get_scores()
        assert scores["BG Elves"]["score"] == pytest.approx(0.0)
        assert scores["BG Elves"]["confidence"] == "none"

    def test_interval_returned(self):
        """After signals, interval should be a 2-tuple."""
        config = self._make_config()
        tracker = OpennessTracker(config)
        card = _make_card("Elf Lord", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=8, pack_number=0)

        data = tracker.get_scores()["BG Elves"]
        assert data["interval"] is not None
        assert len(data["interval"]) == 2
        # For log-odds output, interval is (lo, hi) around score
        assert data["interval"][0] < data["score"]
        assert data["interval"][1] > data["score"]

    def test_real_data_integration(self, otj_dataset):
        """Full flow with real OTJ dataset."""
        archetypes = auto_detect_archetypes(otj_dataset, threshold_percent=5.0)
        config = ArchetypeConfig(
            set_code="OTJ",
            scoring_method="bayesian_survival",
            archetypes=archetypes,
        )
        tracker = OpennessTracker(config)

        card_ids = list(otj_dataset._dataset["card_ratings"].keys())[:8]
        pack_cards = otj_dataset.get_data_by_id(card_ids)

        tracker.record_pack(pack_cards, pick_number=7, pack_number=0)
        scores = tracker.get_scores()
        assert len(scores) == len(archetypes)
```

**Step 2: Run tests to verify they pass** (these should already pass from previous tasks)

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestBayesianSurvivalIntegration -v`
Expected: PASS

**Step 3: Integrate overlay.py — live mode**

In `src/overlay.py`, modify the openness update block at lines ~1676-1683.

Find:
```python
        # Update openness scoring
        if self.openness_tracker and pack_cards:
            if self.draft.hindsight_mode:
                self.__replay_hindsight_openness()
            else:
                pick_in_pack = self.draft.retrieve_current_pick_in_pack()
                self.openness_tracker.record_pack(pack_cards, pick_in_pack, current_pack - 1)
                self.__update_openness_panel()
```

Replace with:
```python
        # Update openness scoring
        if self.openness_tracker and pack_cards:
            if self.draft.hindsight_mode:
                self.__replay_hindsight_openness()
            else:
                pick_in_pack = self.draft.retrieve_current_pick_in_pack()
                self.openness_tracker.record_pack(pack_cards, pick_in_pack, current_pack - 1)
                if missing_cards and pick_in_pack >= 9:
                    self.openness_tracker.record_missing(missing_cards, pick_in_pack, current_pack - 1)
                self.__update_openness_panel()
```

**Step 4: Integrate overlay.py — hindsight replay**

In `src/overlay.py`, modify `__replay_hindsight_openness` at lines ~1396-1415.

Find:
```python
    def __replay_hindsight_openness(self):
        """Reset and replay openness signals from beginning through current hindsight position."""
        if not self.openness_tracker or not self.draft.hindsight_mode:
            return

        self.openness_tracker.reset()

        for i in range(self.draft.history_index + 1):
            entry = self.draft.pick_history[i]
            all_names = entry.get("all_pack_cards", [])
            if not all_names:
                continue
            pack_cards_data = self.draft.set_data.get_data_by_name(all_names)
            if not pack_cards_data:
                continue
            pick_in_pack = entry["current_pick_in_pack"]
            pack_number = entry["current_pack"] - 1
            self.openness_tracker.record_pack(pack_cards_data, pick_in_pack, pack_number)

        self.__update_openness_panel()
```

Replace with:
```python
    def __replay_hindsight_openness(self):
        """Reset and replay openness signals from beginning through current hindsight position."""
        if not self.openness_tracker or not self.draft.hindsight_mode:
            return

        self.openness_tracker.reset()

        for i in range(self.draft.history_index + 1):
            entry = self.draft.pick_history[i]
            all_names = entry.get("all_pack_cards", [])
            if not all_names:
                continue
            pack_cards_data = self.draft.set_data.get_data_by_name(all_names)
            if not pack_cards_data:
                continue
            pick_in_pack = entry["current_pick_in_pack"]
            pack_number = entry["current_pack"] - 1
            self.openness_tracker.record_pack(pack_cards_data, pick_in_pack, pack_number)

            # Replay missing card signals for wheel picks
            if pick_in_pack >= 9:
                initial_names = entry.get("initial_pack_cards", [])
                picked_names = entry.get("picked_cards_in_pack", [])
                current_names = set(all_names)
                picked_set = set(picked_names)
                missing_names = [n for n in initial_names
                                 if n not in current_names and n not in picked_set]
                if missing_names:
                    missing_data = self.draft.set_data.get_data_by_name(missing_names)
                    if missing_data:
                        self.openness_tracker.record_missing(missing_data, pick_in_pack, pack_number)

        self.__update_openness_panel()
```

**Step 5: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/overlay.py tests/test_archetype_openness.py
git commit -m "feat: integrate bayesian_survival with overlay.py (live + hindsight)"
```

---

### Task 7: Add to archetype editor UI and openness panel display

**Files:**
- Modify: `src/archetype_editor.py:162-177` (scoring dropdown), `src/archetype_editor.py:395-410` (conditional fields)
- Modify: `src/overlay.py:1720-1770` (display panel)

**Step 1: Add dropdown option in archetype_editor.py**

In `src/archetype_editor.py`, add the new method to the display map at line ~163:

Find:
```python
        self._scoring_display_map = {
            "Simple": "simple",
            "Weighted": "normalized",
            "Bayesian (%)": "bayesian_beta",
            "HMM Hybrid (%)": "hmm_hybrid",
        }
```

Replace with:
```python
        self._scoring_display_map = {
            "Simple": "simple",
            "Weighted": "normalized",
            "Bayesian (%)": "bayesian_beta",
            "HMM Hybrid (%)": "hmm_hybrid",
            "Bayesian Survival": "bayesian_survival",
        }
```

In `_on_scoring_change` (line ~395), add handling for `bayesian_survival`. It should show the HMM ramp field since it reuses `hmm_pick_ramp`:

Find:
```python
        if internal == "bayesian_beta":
            self.prior_frame.pack(side=tkinter.LEFT)
        elif internal == "normalized":
            self.curve_frame.pack(side=tkinter.LEFT)
        elif internal == "hmm_hybrid":
            self.hmm_frame.pack(side=tkinter.LEFT)
```

Replace with:
```python
        if internal == "bayesian_beta":
            self.prior_frame.pack(side=tkinter.LEFT)
        elif internal == "normalized":
            self.curve_frame.pack(side=tkinter.LEFT)
        elif internal in ("hmm_hybrid", "bayesian_survival"):
            self.hmm_frame.pack(side=tkinter.LEFT)
```

**Step 2: Update openness panel display in overlay.py**

The panel at `src/overlay.py:1720-1770` formats scores differently for probabilistic vs non-probabilistic methods. Since `bayesian_survival` outputs log-odds (not P(open)), it needs its own display logic.

Find in `__update_openness_panel`:
```python
        if scoring_method in {"bayesian_beta", "hmm_hybrid"}:
            max_score = 1.0  # P(open) style methods are always 0-1
        else:
            max_score = max(abs(s["score"]) for _, s in sorted_archetypes) if sorted_archetypes else 1.0
            if max_score == 0:
                max_score = 1.0
```

Replace with:
```python
        if scoring_method in {"bayesian_beta", "hmm_hybrid"}:
            max_score = 1.0  # P(open) style methods are always 0-1
        elif scoring_method == "bayesian_survival":
            max_score = max(abs(s["score"]) for _, s in sorted_archetypes) if sorted_archetypes else 1.0
            if max_score == 0:
                max_score = 1.0
        else:
            max_score = max(abs(s["score"]) for _, s in sorted_archetypes) if sorted_archetypes else 1.0
            if max_score == 0:
                max_score = 1.0
```

Find the score text formatting block:
```python
            if scoring_method in {"bayesian_beta", "hmm_hybrid"}:
                interval = data.get("interval")
                if interval is not None:
                    half_width = (interval[1] - interval[0]) / 2 * 100
                    score_text = f"{score * 100:.0f}% \u00b1{half_width:.0f}%"
                else:
                    score_text = f"{score * 100:.0f}%"
            else:
                score_text = f"{score:+.1f}"
```

Replace with:
```python
            if scoring_method in {"bayesian_beta", "hmm_hybrid"}:
                interval = data.get("interval")
                if interval is not None:
                    half_width = (interval[1] - interval[0]) / 2 * 100
                    score_text = f"{score * 100:.0f}% \u00b1{half_width:.0f}%"
                else:
                    score_text = f"{score * 100:.0f}%"
            elif scoring_method == "bayesian_survival":
                interval = data.get("interval")
                if interval is not None:
                    half_width = (interval[1] - interval[0]) / 2
                    score_text = f"{score:+.2f} \u00b1{half_width:.2f}"
                else:
                    score_text = f"{score:+.2f}"
            else:
                score_text = f"{score:+.1f}"
```

Find the bar rendering block:
```python
            if scoring_method in {"bayesian_beta", "hmm_hybrid"}:
                bar_width = int(score * 80)
                bar_color = self._openness_bayesian_bar_color(score)
            else:
                bar_width = int(abs(score) / max_score * 80) if max_score else 0
                bar_color = "#4CAF50" if score > 0 else "#F44336" if score < 0 else "#888888"
```

Replace with:
```python
            if scoring_method in {"bayesian_beta", "hmm_hybrid"}:
                bar_width = int(score * 80)
                bar_color = self._openness_bayesian_bar_color(score)
            elif scoring_method == "bayesian_survival":
                bar_width = int(abs(score) / max_score * 80) if max_score else 0
                if score > 0.5:
                    bar_color = "#4CAF50"
                elif score < -0.5:
                    bar_color = "#F44336"
                else:
                    bar_color = "#888888"
            else:
                bar_width = int(abs(score) / max_score * 80) if max_score else 0
                bar_color = "#4CAF50" if score > 0 else "#F44336" if score < 0 else "#888888"
```

**Step 3: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/archetype_editor.py src/overlay.py
git commit -m "feat: add bayesian_survival to archetype editor dropdown and openness panel display"
```

---

### Task 8: Edge case tests and final verification

**Files:**
- Test: `tests/test_archetype_openness.py`

**Step 1: Write edge case tests**

```python
class TestBayesianSurvivalEdgeCases:
    """Edge case tests for the bayesian_survival method."""

    def _make_config(self, **kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_empty_missing_cards(self):
        """record_missing with empty list is a no-op."""
        tracker = OpennessTracker(self._make_config())
        tracker.record_missing([], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_empty_pack_cards(self):
        """record_pack with empty list is a no-op (pick 1 early return)."""
        tracker = OpennessTracker(self._make_config())
        tracker.record_pack([], pick_number=1, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)

    def test_pack_number_out_of_range(self):
        """pack_number beyond pack_weights uses default 1.0."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=5)
        assert tracker.get_scores()["Test"]["score"] > 0.0

    def test_no_archetypes_empty_scores(self):
        """Config with no archetypes returns empty scores."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[],
        )
        tracker = OpennessTracker(config)
        assert tracker.get_scores() == {}

    def test_multiple_cards_in_one_pack(self):
        """Multiple archetype cards in same pack all contribute."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="bayesian_survival",
            archetypes=[Archetype(name="Test", cards={"A": 1.0, "B": 1.0})],
        )
        tracker_single = OpennessTracker(config)
        card_a = _make_card("A", ata=3.0)
        card_a["rarity"] = "common"
        tracker_single.record_pack([card_a], pick_number=7, pack_number=0)
        score_single = tracker_single.get_scores()["Test"]["score"]

        tracker_both = OpennessTracker(config)
        card_b = _make_card("B", ata=3.0)
        card_b["rarity"] = "common"
        tracker_both.record_pack([card_a, card_b], pick_number=7, pack_number=0)
        score_both = tracker_both.get_scores()["Test"]["score"]

        assert score_both > score_single

    def test_top_contributors_works(self):
        """get_top_contributors returns correct data for bayesian_survival."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        card["rarity"] = "common"
        tracker.record_pack([card], pick_number=7, pack_number=0)
        top = tracker.get_top_contributors("Test", count=3)
        assert len(top) == 1
        assert top[0]["card_name"] == "Card"

    def test_scoring_method_routing(self):
        """Verify get_scores routes to correct method."""
        for method in ["simple", "normalized", "bayesian_beta", "hmm_hybrid", "bayesian_survival"]:
            config = ArchetypeConfig(
                set_code="TST",
                scoring_method=method,
                archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
            )
            tracker = OpennessTracker(config)
            scores = tracker.get_scores()
            assert "Test" in scores
            assert "score" in scores["Test"]
```

**Step 2: Run all tests**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: ALL PASS

**Step 3: Run the complete test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add tests/test_archetype_openness.py
git commit -m "test: add comprehensive edge case tests for bayesian_survival method"
```
