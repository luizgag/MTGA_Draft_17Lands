"""Standalone Archetype Editor window for configuring draft archetypes."""

import os
import tkinter
from tkinter import ttk, messagebox
from typing import Optional

from src.archetype_openness import (
    ArchetypeConfig,
    Archetype,
    auto_detect_archetypes,
    calculate_card_weights,
    load_archetype_config,
    save_archetype_config,
)
from src.constants import (
    ARCHETYPES_FOLDER,
    COLOR_NAMES_DICT,
    DECK_COLORS,
    FILTER_OPTION_ALL_DECKS,
    DATA_FIELD_DECK_COLORS,
    DATA_FIELD_ATA,
    DATA_FIELD_NAME,
)
from src.logger import create_logger
from src.utils import AutocompleteEntry

logger = create_logger()


class ArchetypeEditor:
    """Standalone window for editing archetype configurations."""

    def __init__(self, scale_factor, fonts_dict, dataset, set_code, on_save_callback=None):
        """
        Args:
            scale_factor: UI scaling factor
            fonts_dict: fonts dictionary from overlay
            dataset: current Dataset instance
            set_code: current set code (e.g., "OTJ")
            on_save_callback: called after saving, so overlay can reload config
        """
        self.dataset = dataset
        self.set_code = set_code
        self.on_save_callback = on_save_callback
        self.selected_archetype_index = None
        self._dirty = False

        # Load existing config or create empty
        config_path = os.path.join(ARCHETYPES_FOLDER, f"{set_code}_archetypes.json")
        self.config = load_archetype_config(config_path) or ArchetypeConfig(set_code=set_code)

        # Build window
        self.window = tkinter.Toplevel()
        self.window.wm_title(f"Archetype Editor - {set_code}")
        self.window.attributes("-topmost", True)
        self.window.resizable(width=True, height=True)
        self.window.geometry("900x600")
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_archetype_list()

    def _build_ui(self):
        """Build the editor UI layout."""
        # Main horizontal panes
        paned = ttk.PanedWindow(self.window, orient=tkinter.HORIZONTAL)
        paned.pack(fill=tkinter.BOTH, expand=True, padx=4, pady=4)

        # --- Left panel: Archetype list ---
        left_frame = ttk.LabelFrame(paned, text="Archetypes")
        paned.add(left_frame, weight=1)

        # Auto-detect controls
        detect_frame = ttk.Frame(left_frame)
        detect_frame.pack(fill=tkinter.X, padx=4, pady=4)

        ttk.Label(detect_frame, text="Threshold %:").pack(side=tkinter.LEFT)
        self.threshold_var = tkinter.StringVar(value=str(self.config.detection_threshold))
        threshold_entry = ttk.Entry(detect_frame, textvariable=self.threshold_var, width=6)
        threshold_entry.pack(side=tkinter.LEFT, padx=4)

        ttk.Button(detect_frame, text="Auto-Detect", command=self._auto_detect).pack(side=tkinter.LEFT, padx=4)

        # Archetype listbox
        self.archetype_listbox = tkinter.Listbox(left_frame, width=25)
        self.archetype_listbox.pack(fill=tkinter.BOTH, expand=True, padx=4, pady=4)
        self.archetype_listbox.bind("<<ListboxSelect>>", self._on_archetype_select)

        # Add/Delete buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tkinter.X, padx=4, pady=4)
        ttk.Button(btn_frame, text="Add Custom", command=self._add_custom_archetype).pack(side=tkinter.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_archetype).pack(side=tkinter.LEFT, padx=2)

        # --- Right panel: Card editor ---
        right_frame = ttk.LabelFrame(paned, text="Cards")
        paned.add(right_frame, weight=3)

        # Archetype name and color pair
        top_frame = ttk.Frame(right_frame)
        top_frame.pack(fill=tkinter.X, padx=4, pady=4)

        ttk.Label(top_frame, text="Name:").pack(side=tkinter.LEFT)
        self.name_var = tkinter.StringVar()
        ttk.Entry(top_frame, textvariable=self.name_var, width=20).pack(side=tkinter.LEFT, padx=4)

        ttk.Label(top_frame, text="Color Pair:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.color_var = tkinter.StringVar()
        color_options = ["None"] + [c for c in DECK_COLORS if c != FILTER_OPTION_ALL_DECKS]
        self.color_combo = ttk.Combobox(top_frame, textvariable=self.color_var, values=color_options, width=8, state="readonly")
        self.color_combo.pack(side=tkinter.LEFT, padx=4)

        self.auto_weights_var = tkinter.BooleanVar(value=True)
        ttk.Checkbutton(top_frame, text="Auto Weights", variable=self.auto_weights_var).pack(side=tkinter.LEFT, padx=8)

        ttk.Button(top_frame, text="Recalculate", command=self._recalculate_weights).pack(side=tkinter.LEFT, padx=4)

        # Card table — use a custom style so text is visible in dark mode
        style = ttk.Style()
        style.configure("Editor.Treeview",
                        background="#3d3d3d",
                        foreground="#ffffff",
                        fieldbackground="#3d3d3d")
        style.configure("Editor.Treeview.Heading",
                        foreground="black")

        columns = ("card_name", "weight", "ata")
        self.card_tree = ttk.Treeview(right_frame, columns=columns, show="headings",
                                      height=20, style="Editor.Treeview")
        self.card_tree.heading("card_name", text="Card Name")
        self.card_tree.heading("weight", text="Weight")
        self.card_tree.heading("ata", text="ATA")
        self.card_tree.column("card_name", width=250)
        self.card_tree.column("weight", width=80)
        self.card_tree.column("ata", width=80)
        self.card_tree.pack(fill=tkinter.BOTH, expand=True, padx=4, pady=4)

        # Card editing buttons
        card_btn_frame = ttk.Frame(right_frame)
        card_btn_frame.pack(fill=tkinter.X, padx=4, pady=4)

        ttk.Label(card_btn_frame, text="Add card:").pack(side=tkinter.LEFT)
        self.add_card_entry = AutocompleteEntry(card_btn_frame, width=25)
        card_names = self.dataset.get_all_names() if self.dataset else []
        self.add_card_entry.initialize(card_names)
        self.add_card_entry.pack(side=tkinter.LEFT, padx=4)
        ttk.Button(card_btn_frame, text="Add", command=self._add_card).pack(side=tkinter.LEFT, padx=2)
        ttk.Button(card_btn_frame, text="Remove Selected", command=self._remove_card).pack(side=tkinter.LEFT, padx=2)

        # Enable editing weight on double-click
        self.card_tree.bind("<Double-1>", self._on_card_double_click)

        # --- Bottom bar: Global settings ---
        bottom_frame = ttk.Frame(self.window)
        bottom_frame.pack(fill=tkinter.X, padx=4, pady=8)

        ttk.Label(bottom_frame, text="Scoring:").pack(side=tkinter.LEFT)
        self.scoring_var = tkinter.StringVar(value=self.config.scoring_method)
        scoring_combo = ttk.Combobox(bottom_frame, textvariable=self.scoring_var,
                                      values=["simple", "normalized"], width=12, state="readonly")
        scoring_combo.pack(side=tkinter.LEFT, padx=4)

        ttk.Label(bottom_frame, text="Curve:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.weight_curve_var = tkinter.StringVar(value=self.config.weight_curve)
        curve_combo = ttk.Combobox(bottom_frame, textvariable=self.weight_curve_var,
                                    values=["linear", "sqrt", "squared"], width=8, state="readonly")
        curve_combo.pack(side=tkinter.LEFT, padx=4)

        ttk.Label(bottom_frame, text="Pack Weights:").pack(side=tkinter.LEFT, padx=(8, 0))
        self.pack_weight_vars = []
        for i, w in enumerate(self.config.pack_weights):
            ttk.Label(bottom_frame, text=f"P{i+1}:").pack(side=tkinter.LEFT, padx=(4, 0))
            var = tkinter.StringVar(value=str(w))
            self.pack_weight_vars.append(var)
            ttk.Entry(bottom_frame, textvariable=var, width=5).pack(side=tkinter.LEFT, padx=2)

        ttk.Button(bottom_frame, text="Save", command=self._save).pack(side=tkinter.RIGHT, padx=4)
        ttk.Button(bottom_frame, text="Reset to Auto", command=self._reset_to_auto).pack(side=tkinter.RIGHT, padx=4)

    def _refresh_archetype_list(self):
        """Refresh the archetype listbox from config."""
        self.archetype_listbox.delete(0, tkinter.END)
        for arch in self.config.archetypes:
            display = f"{arch.name} ({len(arch.cards)} cards)"
            self.archetype_listbox.insert(tkinter.END, display)

    def _on_archetype_select(self, event):
        """Load selected archetype into the card editor."""
        selection = self.archetype_listbox.curselection()
        if not selection:
            return
        self.selected_archetype_index = selection[0]
        arch = self.config.archetypes[self.selected_archetype_index]

        self.name_var.set(arch.name)
        self.color_var.set(arch.color_pair or "None")
        self.auto_weights_var.set(arch.auto_weights)

        self._refresh_card_table(arch)

    def _refresh_card_table(self, archetype):
        """Refresh the card table for the given archetype."""
        for row in self.card_tree.get_children():
            self.card_tree.delete(row)

        # Get ATA values from dataset
        card_ratings = self.dataset._dataset.get("card_ratings", {}) if self.dataset._dataset else {}

        ata_lookup = {}
        for card_id, card in card_ratings.items():
            name = card.get(DATA_FIELD_NAME, "")
            all_decks = card.get(DATA_FIELD_DECK_COLORS, {}).get(FILTER_OPTION_ALL_DECKS, {})
            ata_lookup[name] = all_decks.get(DATA_FIELD_ATA, 0.0)

        sorted_cards = sorted(archetype.cards.items(), key=lambda x: x[1], reverse=True)
        for card_name, weight in sorted_cards:
            ata = ata_lookup.get(card_name, 0.0)
            self.card_tree.insert("", tkinter.END, values=(card_name, f"{weight:.2f}", f"{ata:.1f}"))

    def _auto_detect(self):
        """Run auto-detection and populate archetypes."""
        try:
            threshold = float(self.threshold_var.get())
        except ValueError:
            messagebox.showerror("Error", "Threshold must be a number")
            return

        archetypes = auto_detect_archetypes(self.dataset, threshold)
        self.config.archetypes = archetypes
        self.config.detection_threshold = threshold
        self._refresh_archetype_list()

        # Auto-select the first archetype and show its cards
        if self.config.archetypes:
            self.archetype_listbox.selection_set(0)
            self._on_archetype_select(None)
        else:
            self.selected_archetype_index = None

        # Auto-save so archetypes persist between sessions
        self._save()

    def _add_custom_archetype(self):
        """Add a new empty custom archetype."""
        name = f"Custom {len(self.config.archetypes) + 1}"
        arch = Archetype(name=name, auto_weights=False)
        self.config.archetypes.append(arch)
        self._dirty = True
        self._refresh_archetype_list()
        self.archetype_listbox.selection_set(len(self.config.archetypes) - 1)
        self._on_archetype_select(None)

    def _delete_archetype(self):
        """Delete the selected archetype."""
        if self.selected_archetype_index is None:
            return
        del self.config.archetypes[self.selected_archetype_index]
        self.selected_archetype_index = None
        self._dirty = True
        self._refresh_archetype_list()
        for row in self.card_tree.get_children():
            self.card_tree.delete(row)

    def _add_card(self):
        """Add a card to the selected archetype."""
        if self.selected_archetype_index is None:
            return
        card_name = self.add_card_entry.get().strip()
        if not card_name:
            return
        arch = self.config.archetypes[self.selected_archetype_index]
        if card_name not in arch.cards:
            arch.cards[card_name] = 0.5
            self._dirty = True
        self.add_card_entry.delete(0, tkinter.END)
        self._refresh_card_table(arch)
        self._refresh_archetype_list()

    def _remove_card(self):
        """Remove selected card from the archetype."""
        if self.selected_archetype_index is None:
            return
        selection = self.card_tree.selection()
        if not selection:
            return
        arch = self.config.archetypes[self.selected_archetype_index]
        for item in selection:
            card_name = self.card_tree.item(item)["values"][0]
            arch.cards.pop(str(card_name), None)
        self._dirty = True
        self._refresh_card_table(arch)
        self._refresh_archetype_list()

    def _on_card_double_click(self, event):
        """Edit card weight on double-click."""
        if self.selected_archetype_index is None:
            return
        item = self.card_tree.identify_row(event.y)
        column = self.card_tree.identify_column(event.x)
        if not item or column != "#2":  # Only edit weight column
            return

        # Get current values
        values = self.card_tree.item(item)["values"]
        card_name = str(values[0])

        # Create inline edit
        bbox = self.card_tree.bbox(item, column)
        if not bbox:
            return
        entry = ttk.Entry(self.card_tree, width=8)
        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        entry.insert(0, str(values[1]))
        entry.select_range(0, tkinter.END)
        entry.focus()

        def on_confirm(e=None):
            try:
                new_weight = float(entry.get())
                new_weight = max(0.0, min(1.0, new_weight))
                arch = self.config.archetypes[self.selected_archetype_index]
                arch.cards[card_name] = round(new_weight, 4)
                self._dirty = True
                self._refresh_card_table(arch)
            except ValueError:
                pass
            entry.destroy()

        entry.bind("<Return>", on_confirm)
        entry.bind("<FocusOut>", on_confirm)

    def _recalculate_weights(self):
        """Recalculate weights from 17Lands data for selected archetype."""
        if self.selected_archetype_index is None:
            return
        arch = self.config.archetypes[self.selected_archetype_index]
        if not arch.color_pair:
            messagebox.showinfo("Info", "Set a color pair to auto-calculate weights")
            return
        arch.cards = calculate_card_weights(self.dataset, arch.color_pair)
        arch.auto_weights = True
        self._dirty = True
        self._refresh_card_table(arch)
        self._refresh_archetype_list()

    def _save(self):
        """Save current config to file and update archetype names/settings from UI."""
        # Update selected archetype from UI fields
        if self.selected_archetype_index is not None:
            arch = self.config.archetypes[self.selected_archetype_index]
            arch.name = self.name_var.get()
            color = self.color_var.get()
            arch.color_pair = None if color == "None" else color
            arch.auto_weights = self.auto_weights_var.get()

        # Update global settings
        self.config.scoring_method = self.scoring_var.get()
        self.config.weight_curve = self.weight_curve_var.get()
        try:
            self.config.pack_weights = [float(v.get()) for v in self.pack_weight_vars]
        except ValueError:
            messagebox.showerror("Error", "Pack weights must be numbers")
            return

        config_path = os.path.join(ARCHETYPES_FOLDER, f"{self.set_code}_archetypes.json")
        if save_archetype_config(self.config, config_path):
            self._dirty = False
            self._refresh_archetype_list()
            if self.on_save_callback:
                self.on_save_callback()
        else:
            messagebox.showerror("Error", "Failed to save archetype config")

    def _reset_to_auto(self):
        """Reset everything to auto-detected archetypes."""
        self._auto_detect()
        self._save()

    def _on_close(self):
        """Handle window close with unsaved changes warning."""
        if self._dirty:
            result = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Save before closing?",
                parent=self.window,
            )
            if result is None:  # Cancel
                return
            if result:  # Yes
                self._save()
        self.window.destroy()
