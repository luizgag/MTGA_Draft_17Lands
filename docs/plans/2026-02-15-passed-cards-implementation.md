# Passed Cards Tracking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Track cards the user passes during a draft and display per-archetype "passed" scores alongside the existing Archetype Openness panel.

**Architecture:** Extend `OpennessTracker` with `passed_signals` list, `record_passed()` method, and inverted pack weights. The overlay detects picks via `taken_cards` growth, computes passed cards, and renders amber bars on the right side of the openness panel.

**Tech Stack:** Python 3.12, Tkinter, pytest

---

### Task 1: Add `record_passed()` and `get_passed_scores()` to OpennessTracker

**Files:**
- Modify: `src/archetype_openness.py` (OpennessTracker class)
- Test: `tests/test_archetype_openness.py`

**Step 1: Write failing tests**

Add to the bottom of `tests/test_archetype_openness.py`:

```python
class TestPassedCardsTracking:
    """Tests for passed cards tracking: cards the user doesn't pick."""

    @staticmethod
    def _make_config(**kwargs):
        defaults = dict(
            set_code="TST",
            scoring_method="simple",
            pack_weights=[1.0, 0.66, 1.0],
            archetypes=[Archetype(name="Goblins", cards={"Goblin Guide": 0.8, "Lightning Bolt": 0.3})],
        )
        defaults.update(kwargs)
        return ArchetypeConfig(**defaults)

    def test_pack_weight_inversion(self):
        """Passed pack weights swap indices 0 and 1."""
        tracker = OpennessTracker(self._make_config())
        assert tracker.passed_pack_weights == [0.66, 1.0, 1.0]

    def test_record_passed_produces_negative_score(self):
        """Passing a card produces a negative passed score."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        scores = tracker.get_passed_scores()
        assert scores["Goblins"]["score"] < 0.0

    def test_record_passed_exact_formula(self):
        """Verify formula: -(1/(ata + pick)) * card_weight * passed_pack_weight * 100."""
        config = self._make_config(
            pack_weights=[1.0, 0.5, 1.0],
            archetypes=[Archetype(name="Test", cards={"Card": 1.0})],
        )
        tracker = OpennessTracker(config)
        card = _make_card("Card", ata=4.0)
        tracker.record_passed([card], pick_number=6, pack_number=0)
        # passed_pack_weights = [0.5, 1.0, 1.0], pack 0 weight = 0.5
        expected = -(1.0 / (4.0 + 6)) * 1.0 * 0.5 * 100  # -5.0
        assert tracker.get_passed_scores()["Test"]["score"] == pytest.approx(expected)

    def test_card_not_in_archetype_ignored(self):
        """Cards not in any archetype produce no passed signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Random Card", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_zero_ata_skipped(self):
        """Cards with ATA=0 produce no signal."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=0.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_card_weight_scales_signal(self):
        """Higher card_weight produces stronger passed signal."""
        config_low = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Card": 0.2})])
        tracker_low = OpennessTracker(config_low)
        card = _make_card("Card", ata=5.0)
        tracker_low.record_passed([card], pick_number=3, pack_number=0)

        config_high = self._make_config(
            archetypes=[Archetype(name="Test", cards={"Card": 0.9})])
        tracker_high = OpennessTracker(config_high)
        tracker_high.record_passed([card], pick_number=3, pack_number=0)

        assert tracker_high.get_passed_scores()["Test"]["score"] < tracker_low.get_passed_scores()["Test"]["score"]

    def test_passed_pack_weight_applied(self):
        """Passed uses inverted pack weights (P2 gets P1's weight)."""
        config = self._make_config(pack_weights=[1.0, 0.5, 1.0])
        tracker = OpennessTracker(config)
        card = _make_card("Goblin Guide", ata=5.0)

        # Pack 1 (index 0): passed_weight = 0.5
        tracker.record_passed([card], pick_number=3, pack_number=0)
        score_p1 = tracker.get_passed_scores()["Goblins"]["score"]

        tracker2 = OpennessTracker(config)
        # Pack 2 (index 1): passed_weight = 1.0
        tracker2.record_passed([card], pick_number=3, pack_number=1)
        score_p2 = tracker2.get_passed_scores()["Goblins"]["score"]

        # P2 should have stronger (more negative) signal
        assert score_p2 < score_p1

    def test_accumulation_across_picks(self):
        """Passed scores accumulate across multiple picks."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=5.0)
        tracker.record_passed([card], pick_number=2, pack_number=0)
        score_1 = tracker.get_passed_scores()["Goblins"]["score"]
        tracker.record_passed([card], pick_number=3, pack_number=0)
        score_2 = tracker.get_passed_scores()["Goblins"]["score"]
        assert score_2 < score_1 < 0.0

    def test_reset_clears_passed(self):
        """Reset clears all passed signals."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0
        tracker.reset()
        assert tracker.get_passed_scores()["Goblins"]["score"] == pytest.approx(0.0)

    def test_get_top_passed(self):
        """Top passed returns highest absolute signals."""
        tracker = OpennessTracker(self._make_config())
        guide = _make_card("Goblin Guide", ata=2.0)
        bolt = _make_card("Lightning Bolt", ata=8.0)
        tracker.record_passed([guide, bolt], pick_number=5, pack_number=0)
        top = tracker.get_top_passed("Goblins", count=1)
        assert len(top) == 1
        # Goblin Guide has lower ATA and higher card_weight -> strongest signal
        assert top[0]["card_name"] == "Goblin Guide"

    def test_passed_independent_from_openness(self):
        """Passed scores don't affect openness scores and vice versa."""
        tracker = OpennessTracker(self._make_config())
        card = _make_card("Goblin Guide", ata=3.0)
        tracker.record_passed([card], pick_number=5, pack_number=0)
        # Openness score should still be 0
        assert tracker.get_scores()["Goblins"]["score"] == pytest.approx(0.0)
        # Passed score should be negative
        assert tracker.get_passed_scores()["Goblins"]["score"] < 0.0
```

**Step 2: Run tests to verify they fail**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestPassedCardsTracking -v`
Expected: FAIL (AttributeError: 'OpennessTracker' has no attribute 'passed_pack_weights')

**Step 3: Implement in `src/archetype_openness.py`**

In `OpennessTracker.__init__` (after line 182), add:

```python
        # Passed cards tracking state
        self.passed_signals: List[Dict] = []
        # Invert pack weights: swap P1 and P2 weights
        if len(self.pack_weights) >= 2:
            self.passed_pack_weights = [self.pack_weights[1], self.pack_weights[0]] + list(self.pack_weights[2:])
        else:
            self.passed_pack_weights = list(self.pack_weights)
```

Add new methods after `record_missing` (after line 615):

```python
    def record_passed(self, passed_cards: List[Dict], pick_number: int, pack_number: int) -> None:
        """Record signals from cards the user passed (didn't pick).

        Uses formula: -(1/(ata + pick_number)) * card_weight * passed_pack_weight * 100

        Args:
            passed_cards: list of card dicts the user chose not to pick
            pick_number: 1-based pick position within the pack
            pack_number: 0-indexed pack number
        """
        pack_weight = self.passed_pack_weights[pack_number] if pack_number < len(self.passed_pack_weights) else 1.0

        for card in passed_cards:
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
                raw_signal = -(1.0 / (ata + pick_number))
                signal = raw_signal * card_weight * pack_weight * 100

                self.passed_signals.append({
                    "archetype": archetype.name,
                    "card_name": card_name,
                    "pick_number": pick_number,
                    "ata": ata,
                    "signal": signal,
                })

    def get_passed_scores(self) -> Dict[str, dict]:
        """Get aggregated passed-cards scores for all archetypes.

        Returns dict of {archetype_name: {"score": float}}.
        Always negative (passing cards is always a cost).
        """
        scores = {}
        for arch in self.archetypes:
            total = sum(s["signal"] for s in self.passed_signals if s["archetype"] == arch.name)
            scores[arch.name] = {"score": total}
        return scores

    def get_top_passed(self, archetype_name: str, count: int = 3) -> List[Dict]:
        """Get top N passed cards by absolute signal for an archetype."""
        arch_signals = [s for s in self.passed_signals if s["archetype"] == archetype_name]
        arch_signals.sort(key=lambda s: abs(s["signal"]), reverse=True)
        return [
            {
                "card_name": s["card_name"],
                "pick_number": s["pick_number"],
                "ata": s["ata"],
                "signal": s["signal"],
            }
            for s in arch_signals[:count]
        ]
```

In `reset()` (line 722), add after `self._bs_card_ata = {}`:

```python
        self.passed_signals.clear()
```

**Step 4: Run tests to verify they pass**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py::TestPassedCardsTracking -v`
Expected: All PASS

**Step 5: Run full test suite to check for regressions**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/test_archetype_openness.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/archetype_openness.py tests/test_archetype_openness.py
git commit -m "feat: add record_passed() and get_passed_scores() to OpennessTracker"
```

---

### Task 2: Add passed-cards detection and recording in overlay

**Files:**
- Modify: `src/overlay.py` (init, `__update_widgets`, `__init_openness_tracker`)

**Step 1: Add state variables in `__init__`**

After line 420 (`self._openness_tooltip = None`), add:

```python
        self._prev_pack_for_passed = []
        self._prev_pick_for_passed = 0
        self._prev_pack_number_for_passed = 0
        self._prev_taken_count = 0
```

**Step 2: Reset state in `__init_openness_tracker`**

In `__init_openness_tracker` (around line 1380), after creating the tracker or setting it to None, add:

```python
            self._prev_pack_for_passed = []
            self._prev_pick_for_passed = 0
            self._prev_pack_number_for_passed = 0
            self._prev_taken_count = 0
```

**Step 3: Add passed-cards detection in `__update_widgets`**

In the openness section of `__update_widgets` (around line 1688-1697), modify to:

```python
        # Update openness scoring
        if self.openness_tracker and pack_cards:
            if self.draft.hindsight_mode:
                self.__replay_hindsight_openness()
            else:
                pick_in_pack = self.draft.retrieve_current_pick_in_pack()

                # Detect passed cards: when taken_cards grows, a pick was made
                current_taken_count = len(taken_cards)
                if (current_taken_count > self._prev_taken_count
                        and self._prev_pack_for_passed):
                    # Compute passed = previous pack minus newly picked card(s)
                    new_picks = taken_cards[self._prev_taken_count:]
                    picked_names = {c.get(constants.DATA_FIELD_NAME, "") for c in new_picks}
                    passed = [c for c in self._prev_pack_for_passed
                              if c.get(constants.DATA_FIELD_NAME, "") not in picked_names]
                    if passed:
                        self.openness_tracker.record_passed(
                            passed, self._prev_pick_for_passed,
                            self._prev_pack_number_for_passed)

                self._prev_pack_for_passed = pack_cards
                self._prev_pick_for_passed = pick_in_pack
                self._prev_pack_number_for_passed = current_pack - 1
                self._prev_taken_count = current_taken_count

                self.openness_tracker.record_pack(pack_cards, pick_in_pack, current_pack - 1)
                if missing_cards and pick_in_pack >= 9:
                    self.openness_tracker.record_missing(missing_cards, pick_in_pack, current_pack - 1)
                self.__update_openness_panel()
```

**Step 4: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All PASS (no regressions)

**Step 5: Commit**

```bash
git add src/overlay.py
git commit -m "feat: detect passed cards and record them in openness tracker"
```

---

### Task 3: Render passed-cards bars in the openness panel

**Files:**
- Modify: `src/overlay.py` (`__update_openness_panel`, `__bind_openness_tooltip`)

**Step 1: Add passed-cards bars to `__update_openness_panel`**

Replace the `__update_openness_panel` method (lines 1718-1810) with updated version that adds columns 3-4 for passed bars. After the existing bar rendering (column 2), add:

After `bar_canvas.grid(row=i, column=2, padx=(2, 4))` (line 1805), add columns 3-4:

```python
            # Passed-cards bar (right side, grows left)
            passed_bar_canvas = tkinter.Canvas(
                self.openness_frame, width=80, height=12, highlightthickness=0
            )
            if passed_max > 0:
                passed_bar_width = int(abs(passed_score) / passed_max * 80)
            else:
                passed_bar_width = 0
            # Draw bar from right edge, growing left
            passed_bar_canvas.create_rectangle(
                80 - passed_bar_width, 0, 80, 12,
                fill="#FFA726", outline=""
            )
            passed_bar_canvas.grid(row=i, column=3, padx=(4, 2))

            passed_score_label = tkinter.Label(
                self.openness_frame,
                text=f"{passed_score:.1f}" if passed_score != 0.0 else "",
                anchor=tkinter.W,
                width=6,
                fg=fg_color,
            )
            passed_score_label.grid(row=i, column=4, padx=(2, 4))

            # Tooltip for passed bars
            self.__bind_passed_tooltip(passed_bar_canvas, name)
            self.__bind_passed_tooltip(passed_score_label, name)
```

Before the loop, compute passed scores and max:

```python
        passed_scores = self.openness_tracker.get_passed_scores()
        passed_max = max(
            (abs(passed_scores.get(name, {}).get("score", 0.0))
             for name, _ in sorted_archetypes), default=1.0
        )
        if passed_max == 0:
            passed_max = 1.0
```

Inside the loop, get the passed score for this archetype:

```python
            passed_score = passed_scores.get(name, {}).get("score", 0.0)
```

**Step 2: Add `__bind_passed_tooltip` method**

After `__bind_openness_tooltip` (around line 1860), add:

```python
    def __bind_passed_tooltip(self, widget, archetype_name):
        """Bind hover tooltip showing top passed cards for an archetype."""
        def on_enter(event):
            if not self.openness_tracker:
                return
            contributors = self.openness_tracker.get_top_passed(archetype_name, count=3)
            if not contributors:
                return
            lines = []
            for c in contributors:
                lines.append(f"{c['card_name']}: pick {c['pick_number']}, ATA {c['ata']:.1f} -> {c['signal']:.1f}")
            tooltip_text = "\n".join(lines)
            self.__show_openness_tooltip(event, tooltip_text)

        def on_leave(event):
            self.__hide_openness_tooltip()

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
```

**Step 3: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add src/overlay.py
git commit -m "feat: render passed-cards bars in archetype openness panel"
```

---

### Task 4: Add hindsight mode support for passed cards

**Files:**
- Modify: `src/overlay.py` (`__replay_hindsight_openness`)

**Step 1: Update `__replay_hindsight_openness` to replay passed cards**

In `__replay_hindsight_openness` (around line 1396-1427), after the existing `record_pack` and `record_missing` calls, add passed-cards replay:

After the `record_missing` block (line 1425), add:

```python
            # Replay passed card signals
            picked_card = entry.get("picked_card", "")
            if picked_card and all_names:
                passed_names = [n for n in all_names if n != picked_card]
                if passed_names:
                    passed_data = self.draft.set_data.get_data_by_name(passed_names)
                    if passed_data:
                        self.openness_tracker.record_passed(
                            passed_data, pick_in_pack, pack_number)
```

**Step 2: Run full test suite**

Run: `Xvfb :99 & export DISPLAY=:99 && .venv/bin/pytest tests/ -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add src/overlay.py
git commit -m "feat: replay passed cards in hindsight mode"
```

---

### Task 5: Manual visual testing

**Steps:**
1. Run the application: `python main.py`
2. Start a draft (or use MTGO hindsight mode to load a saved draft log)
3. Verify the Archetype Openness panel shows:
   - Left side: existing openness scores + green/red bars (unchanged)
   - Right side: amber bars growing left + negative scores
4. Verify tooltips work on both sides
5. Navigate hindsight mode forward/backward and verify passed scores update
6. Verify scores reset when starting a new draft

**Commit (if any fixes needed):**

```bash
git add src/overlay.py src/archetype_openness.py
git commit -m "fix: visual adjustments for passed cards panel"
```
