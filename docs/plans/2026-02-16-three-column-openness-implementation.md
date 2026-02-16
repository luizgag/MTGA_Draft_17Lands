# Three-Column Openness Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the 2-bar openness panel with a 3-column layout (positive / passed / combined) and remove missing-card signals from simple_alsa.

**Architecture:** Backend changes to `archetype_openness.py` add two new score methods and remove `simple_alsa` from `record_missing`. Frontend changes to `overlay.py` replace the 2-bar rendering with a 3-bar layout. TDD throughout.

**Tech Stack:** Python 3.12, Tkinter, pytest

---

### Task 1: Remove simple_alsa from record_missing and delete _simple_alsa_missing_emission

**Files:**
- Modify: `src/archetype_openness.py:569-578` (delete `_simple_alsa_missing_emission`)
- Modify: `src/archetype_openness.py:580-622` (update `record_missing` condition)
- Modify: `tests/test_archetype_openness.py:1906-1999` (delete `TestSimpleAlsaMissing`)

**Step 1: Delete `TestSimpleAlsaMissing` class**

Remove lines 1906-1999 from `tests/test_archetype_openness.py` (the entire `class TestSimpleAlsaMissing` block).

**Step 2: Write a test that verifies record_missing is a no-op for simple_alsa**

Add to end of `tests/test_archetype_openness.py`:

```python
class TestSimpleAlsaMissingRemoved:
    """Verify record_missing no longer fires for simple_alsa."""

    def test_record_missing_noop_for_simple_alsa(self):
        """record_missing should produce no signals for simple_alsa scoring."""
        config = ArchetypeConfig(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=5.0)
        tracker.record_missing([card], pick_number=9, pack_number=0)
        assert tracker.get_scores()["Test"]["score"] == pytest.approx(0.0)
        assert len(tracker.signals) == 0
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_archetype_openness.py::TestSimpleAlsaMissingRemoved -v`
Expected: FAIL (record_missing still produces signals for simple_alsa)

**Step 4: Implement the changes**

In `src/archetype_openness.py`:

1. Delete `_simple_alsa_missing_emission` method (lines 569-578).

2. In `record_missing`, change line 590 from:
   ```python
   if self.scoring_method not in ("bayesian_survival", "simple_alsa"):
   ```
   to:
   ```python
   if self.scoring_method != "bayesian_survival":
   ```

3. Remove the `simple_alsa` branch in `record_missing` (lines 610-611):
   ```python
   if self.scoring_method == "simple_alsa":
       emission = self._simple_alsa_missing_emission(ata, card_weight, pack_weight, pick_number)
   ```
   so only the `else` branch remains (rename to unconditional):
   ```python
   emission = self._bs_missing_emission(card, pick_number, ata, card_weight, pack_weight)
   self._bs_update_state(archetype.name, pick_number, emission)
   ```

**Step 5: Run tests**

Run: `pytest tests/test_archetype_openness.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "refactor: remove simple_alsa from record_missing"
```

---

### Task 2: Add get_positive_scores() method

**Files:**
- Modify: `src/archetype_openness.py` (add method after `get_scores`, ~line 373)
- Modify: `tests/test_archetype_openness.py` (add test class)

**Step 1: Write tests for get_positive_scores**

Add to `tests/test_archetype_openness.py`:

```python
class TestGetPositiveScores:
    """Tests for get_positive_scores() — returns only positive wheeling signals."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_positive_signals_only(self):
        """get_positive_scores returns sum of positive signals, ignores negative."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        # pick 5 > alsa 3.0 -> positive signal
        tracker.record_pack([card], pick_number=5, pack_number=0)
        positive = tracker.get_positive_scores()
        assert positive["Test"]["score"] > 0.0

    def test_no_signals_returns_zero(self):
        """No signals means zero positive score."""
        tracker = OpennessTracker(self._make_config())
        positive = tracker.get_positive_scores()
        assert positive["Test"]["score"] == pytest.approx(0.0)

    def test_passed_signals_not_included(self):
        """Passed signals should not appear in positive scores."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        positive = tracker.get_positive_scores()
        assert positive["Test"]["score"] == pytest.approx(0.0)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_archetype_openness.py::TestGetPositiveScores -v`
Expected: FAIL (method does not exist)

**Step 3: Implement get_positive_scores**

Add after `get_scores()` in `src/archetype_openness.py` (~line 373):

```python
def get_positive_scores(self) -> Dict[str, dict]:
    """Get sum of positive (wheeling) signals per archetype.

    Returns dict of {archetype_name: {"score": float}}.
    Only includes signals from record_pack (self.signals), not passed_signals.
    """
    scores = {}
    for arch in self.archetypes:
        total = sum(s["signal"] for s in self.signals if s["archetype"] == arch.name)
        scores[arch.name] = {"score": total}
    return scores
```

**Step 4: Run tests**

Run: `pytest tests/test_archetype_openness.py::TestGetPositiveScores -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add get_positive_scores method to OpennessTracker"
```

---

### Task 3: Add get_combined_scores() method

**Files:**
- Modify: `src/archetype_openness.py` (add method after `get_positive_scores`)
- Modify: `tests/test_archetype_openness.py` (add test class)

**Step 1: Write tests for get_combined_scores**

Add to `tests/test_archetype_openness.py`:

```python
class TestGetCombinedScores:
    """Tests for get_combined_scores() — positive + passed signals."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple_alsa",
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_combined_equals_positive_plus_passed(self):
        """Combined score = positive wheeling + passed card signals."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        tracker.record_pack([card], pick_number=5, pack_number=0)
        tracker.record_passed([card], pick_number=2, pack_number=0)

        positive = tracker.get_positive_scores()["Test"]["score"]
        passed = tracker.get_passed_scores()["Test"]["score"]
        combined = tracker.get_combined_scores()["Test"]["score"]
        assert combined == pytest.approx(positive + passed)

    def test_no_signals_returns_zero(self):
        """No signals means zero combined score."""
        tracker = OpennessTracker(self._make_config())
        combined = tracker.get_combined_scores()
        assert combined["Test"]["score"] == pytest.approx(0.0)

    def test_positive_only_equals_positive(self):
        """With no passed signals, combined == positive."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Card", ata=5.0)
        card["deck_colors"]["All Decks"]["alsa"] = 3.0
        tracker.record_pack([card], pick_number=5, pack_number=0)
        positive = tracker.get_positive_scores()["Test"]["score"]
        combined = tracker.get_combined_scores()["Test"]["score"]
        assert combined == pytest.approx(positive)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_archetype_openness.py::TestGetCombinedScores -v`
Expected: FAIL (method does not exist)

**Step 3: Implement get_combined_scores**

Add after `get_positive_scores()` in `src/archetype_openness.py`:

```python
def get_combined_scores(self) -> Dict[str, dict]:
    """Get combined score (positive wheeling + passed card signals) per archetype.

    Returns dict of {archetype_name: {"score": float}}.
    """
    positive = self.get_positive_scores()
    passed = self.get_passed_scores()
    scores = {}
    for arch in self.archetypes:
        p = positive.get(arch.name, {}).get("score", 0.0)
        n = passed.get(arch.name, {}).get("score", 0.0)
        scores[arch.name] = {"score": p + n}
    return scores
```

**Step 4: Run tests**

Run: `pytest tests/test_archetype_openness.py::TestGetCombinedScores -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add get_combined_scores method to OpennessTracker"
```

---

### Task 4: Replace 2-bar overlay rendering with 3-column layout

**Files:**
- Modify: `src/overlay.py:1779-1908` (`__update_openness_panel` method)

**Step 1: Replace the __update_openness_panel method**

Replace `__update_openness_panel` (lines 1779-1908) with the new 3-column layout. The layout is:

```
| Name (col 0) | Bar1-positive (col 1) | Score1 (col 2) | spacer (col 3) | Bar2-passed (col 4) | Score2 (col 5) | spacer (col 6) | Bar3-combined (col 7) | Score3 (col 8) |
```

Replace the entire method body with:

```python
def __update_openness_panel(self):
    """Update the archetype openness panel with current scores."""
    if not self.openness_tracker:
        return

    for widget in self.openness_frame.winfo_children():
        widget.destroy()

    positive_scores = self.openness_tracker.get_positive_scores()
    passed_scores = self.openness_tracker.get_passed_scores()
    combined_scores = self.openness_tracker.get_combined_scores()

    # Sort by combined score descending
    sorted_names = sorted(
        combined_scores.keys(),
        key=lambda n: combined_scores[n]["score"],
        reverse=True,
    )

    # Compute max values for bar scaling
    pos_max = max((abs(positive_scores.get(n, {}).get("score", 0.0)) for n in sorted_names), default=1.0) or 1.0
    pass_max = max((abs(passed_scores.get(n, {}).get("score", 0.0)) for n in sorted_names), default=1.0) or 1.0
    comb_max = max((abs(combined_scores.get(n, {}).get("score", 0.0)) for n in sorted_names), default=1.0) or 1.0

    for i, name in enumerate(sorted_names):
        pos_score = positive_scores.get(name, {}).get("score", 0.0)
        pass_score = passed_scores.get(name, {}).get("score", 0.0)
        comb_score = combined_scores.get(name, {}).get("score", 0.0)

        # Archetype name
        name_label = tkinter.Label(
            self.openness_frame, text=name, anchor=tkinter.W, width=15,
        )
        name_label.grid(row=i, column=0, sticky="w", padx=(4, 2))

        # --- Column 1: Positive bar (green, grows right) ---
        bar_w = 60
        pos_bar = tkinter.Canvas(self.openness_frame, width=bar_w, height=12, highlightthickness=0)
        pos_fill = int(abs(pos_score) / pos_max * bar_w) if pos_max else 0
        pos_bar.create_rectangle(0, 0, pos_fill, 12, fill="#4CAF50", outline="")
        pos_bar.grid(row=i, column=1, padx=(6, 0))

        pos_label = tkinter.Label(
            self.openness_frame, text=f"{pos_score:+.1f}" if pos_score != 0.0 else "",
            anchor=tkinter.W, width=6,
        )
        pos_label.grid(row=i, column=2, padx=(0, 4))

        # --- Column 2: Passed bar (orange, grows left from right edge) ---
        pass_bar = tkinter.Canvas(self.openness_frame, width=bar_w, height=12, highlightthickness=0)
        pass_fill = int(abs(pass_score) / pass_max * bar_w) if pass_max else 0
        pass_bar.create_rectangle(bar_w - pass_fill, 0, bar_w, 12, fill="#FFA726", outline="")
        pass_bar.grid(row=i, column=3, padx=(6, 0))

        pass_label = tkinter.Label(
            self.openness_frame, text=f"{pass_score:.1f}" if pass_score != 0.0 else "",
            anchor=tkinter.W, width=6,
        )
        pass_label.grid(row=i, column=4, padx=(0, 4))

        # --- Column 3: Combined bar (green/red) ---
        comb_bar = tkinter.Canvas(self.openness_frame, width=bar_w, height=12, highlightthickness=0)
        comb_fill = int(abs(comb_score) / comb_max * bar_w) if comb_max else 0
        comb_color = "#4CAF50" if comb_score > 0 else "#F44336" if comb_score < 0 else "#888888"
        comb_bar.create_rectangle(0, 0, comb_fill, 12, fill=comb_color, outline="")
        comb_bar.grid(row=i, column=5, padx=(6, 0))

        comb_label = tkinter.Label(
            self.openness_frame, text=f"{comb_score:+.1f}" if comb_score != 0.0 else "",
            anchor=tkinter.W, width=6,
        )
        comb_label.grid(row=i, column=6, padx=(0, 4))

        # Tooltips
        self.__bind_openness_tooltip(name_label, name)
        self.__bind_openness_tooltip(pos_bar, name)
        self.__bind_passed_tooltip(pass_bar, name)
        self.__bind_passed_tooltip(pass_label, name)
        self.__bind_openness_tooltip(comb_bar, name)
```

**Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add src/overlay.py
git commit -m "feat: replace 2-bar openness panel with 3-column layout"
```

---

### Task 5: Run full test suite and verify

**Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: ALL PASS, no regressions

**Step 2: Manual verification**

Start the application and verify the 3-column layout renders correctly with proper spacing.
