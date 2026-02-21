# GoatBots MTGO Card Price Integration

## Summary

Integrate GoatBots card price data into the MTGO draft overlay. Cards above a configurable ticket threshold show a `$$$` prefix in the pack table, alerting drafters to high-value picks.

## Decisions

- **Platform**: MTGO only (GoatBots prices are MTGO event tickets)
- **Display**: `$$$` prefix on card name in pack table only (not taken cards or other views)
- **Format**: `$$$` indicator only, no numeric price shown
- **Download timing**: Automatic during set download, after 17Lands data
- **Data source**: GoatBots official downloadable price files (not scraping)

## Data Source

GoatBots provides two daily-updated ZIP files at `https://www.goatbots.com/download-prices`:

1. **`card-definitions.zip`** (~15.7 MB): JSON keyed by MTGO card ID
   - Fields: `name`, `cardset`, `rarity`, `version`, `foil`
2. **`price-history.zip`** (~2 MB): JSON `{mtgo_id: sell_price}`
   - Prices are daily average sell prices in MTGO event tickets

Cards matched to 17Lands data by **card name + set code**, filtering `foil: 0`.

## Architecture

### Data Fetching (file_extractor.py)

New function `retrieve_goatbots_prices(set_code: str) -> Dict[str, float]`:
1. Download both GoatBots ZIPs
2. Parse card-definitions to build lookup: `{(name_lower, set_code): [mtgo_ids]}`
3. Parse price-history to get prices by MTGO ID
4. For cards with multiple regular versions, use highest price
5. Return `{card_name: price}` dict

### Data Integration (overlay.py __add_set)

After 17Lands download/merge and before `export_card_data()`:
- Call `retrieve_goatbots_prices(set_code)`
- Inject `"price"` field into each card in `combined_data["card_ratings"]`
- Cards without a match get `price: 0.0`

### Data Storage (Sets/{SET}_Data.json)

Price stored at card top level (not inside `deck_colors`):
```json
"card_ratings": {
  "12345": {
    "name": "Moonshadow",
    "price": 27.12,
    ...
  }
}
```

### UI Display (overlay.py __update_pack_table)

After `return_results()` and hindsight arrow prefix, add price prefix:
```python
if platform == PLATFORM_MTGO:
    for card in result_list:
        if card.get("price", 0.0) >= threshold:
            card["results"][0] = f"$$$ {card['results'][0]}"
```

### Configuration (configuration.py Settings)

Two new fields:
- `price_enabled: bool = True` - enable/disable price fetching
- `price_threshold: float = 3.0` - minimum ticket price for `$$$` display

### Error Handling

- GoatBots download failure: log warning, continue without prices (non-blocking)
- No name match: card gets `price: 0.0`
- Multiple regular versions: use highest price

## Testing

- `retrieve_goatbots_prices()` with mock ZIP data
- `$$$` prefix logic in pack table rendering
- Price injection into card data
- Feature gated to MTGO platform only
