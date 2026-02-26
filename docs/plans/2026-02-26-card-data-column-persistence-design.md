# Card Data Column Persistence — Design

**Date:** 2026-02-26

## Problem

The Card Data window's 13 column visibility checkboxes (RARITY, GIHWR, OHWR, GPWR, GNSWR, GDWR, ATA, ALSA, IWD, WHEEL, COLORS, NGP, GIH) are reset to hardcoded defaults every time the application restarts. The user's selections are not persisted.

## Goal

Persist the column visibility state across sessions. Rarity filters (COMMON/UNCOMMON/RARE/MYTHIC) and the deck filter dropdown are intentionally excluded.

## Decision

Save on window close only. Do not save on every checkbox change.

## Design

### New `CardDataSettings` model (`src/configuration.py`)

```python
class CardDataSettings(BaseModel):
    col_rarity: bool = True
    col_gihwr: bool = True
    col_ohwr: bool = False
    col_gpwr: bool = False
    col_gnswr: bool = False
    col_gdwr: bool = False
    col_ata: bool = True
    col_alsa: bool = True
    col_iwd: bool = False
    col_wheel: bool = False
    col_colors: bool = True
    col_ngp: bool = False
    col_gih: bool = False
```

Add to `Configuration`:

```python
card_data_settings: CardDataSettings = Field(default_factory=lambda: CardDataSettings())
```

### Overlay changes (`src/overlay.py`)

1. **Initialization** — Replace hardcoded `value=0`/`value=1` in the 13 `tkinter.IntVar` constructors with values read from `self.configuration.card_data_settings`.
2. **Save on close** — In `__close_card_data_window`, write each checkbox's `.get()` value back to `self.configuration.card_data_settings`, then call `write_configuration(self.configuration)`.

## Testing

- `CardDataSettings` defaults match current hardcoded defaults.
- Closing the window writes changed values to `configuration.card_data_settings` and calls `write_configuration`.
- Re-opening the window reads from saved configuration (IntVars initialized with persisted values).
