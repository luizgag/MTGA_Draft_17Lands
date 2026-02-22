from src.trophy_analysis import (
    _canonicalize_pair,
    _extract_17lands_archetype,
    _extract_untapped_archetype,
    _parse_untapped_deck_blocks,
)


def test_canonicalize_pair_handles_order_and_splash():
    assert _canonicalize_pair("GW") == "WG"
    assert _canonicalize_pair("WBG") == "WB"
    assert _canonicalize_pair("UR") == "UR"


def test_extract_17lands_archetype_uses_uppercase_only():
    assert _extract_17lands_archetype("URw") == "UR"
    assert _extract_17lands_archetype("BGwur") == "BG"
    assert _extract_17lands_archetype("g") == ""


def test_extract_untapped_archetype_supports_splash_text():
    assert _extract_untapped_archetype("Golgari splashing white") == "BG"
    assert _extract_untapped_archetype("Azorius") == "WU"
    assert _extract_untapped_archetype("Unknown") == ""


def test_parse_untapped_deck_blocks_extracts_cards_and_archetype_text():
    html = """
    <div><span>Temur</span></div><div><div><label><div>RECORD 3-0</div></label></div></div>
    <a href="/profile/x/y/deck/abc-123/draft-replay">Replay</a>
    <li role="img" aria-label="Card A, 2x"></li>
    <li role="img" aria-label="Card B, 1x"></li>

    <div><span>Rakdos</span></div><div><div><label><div>RECORD 3–0</div></label></div></div>
    <a href="/profile/x/y/deck/def-456/draft-replay">Replay</a>
    <img alt="Card A, 1x" />
    """

    blocks = _parse_untapped_deck_blocks(html, ["abc-123", "def-456"])

    assert len(blocks) == 2
    assert blocks[0]["archetype_text"] == "Temur"
    assert blocks[0]["cards"]["Card A"] == 2
    assert blocks[0]["cards"]["Card B"] == 1
    assert blocks[0]["wins"] == 3
    assert blocks[1]["archetype_text"] == "Rakdos"
    assert blocks[1]["cards"]["Card A"] == 1
    assert blocks[1]["wins"] == 3
