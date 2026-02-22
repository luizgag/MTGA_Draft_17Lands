import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import requests
import tkinter
from pydantic import BaseModel, Field
from tkinter.ttk import Label, OptionMenu, Button

from src import constants
from src.logger import create_logger
from src.scaled_window import ScaledWindow, identify_safe_coordinates

logger = create_logger()

_PLAYWRIGHT_UNAVAILABLE_LOGGED = False
_PLAYWRIGHT_RUNTIME_FAILURE_LOGGED = False

TROPHY_FOLDER = os.path.join(os.getcwd(), "Trophy")

UNTAPPED_URL_TEMPLATE = "https://mtga.untapped.gg/limited/draft/{set_slug}/trophy-decks?eventType={event_type}"
SEVENTEENLANDS_URL_TEMPLATE = "https://www.17lands.com/trophy_decks?expansion={set_code}&format={event_type}"

FORMAT_OPTIONS = {
    "Traditional Draft": {
        "17lands": constants.LIMITED_TYPE_STRING_DRAFT_TRAD,
        "untapped": "TRADITIONAL_HUMAN_DRAFT",
    },
    "Premier Draft": {
        "17lands": constants.LIMITED_TYPE_STRING_DRAFT_PREMIER,
        "untapped": "PREMIER_HUMAN_DRAFT",
    },
}

GUILD_NAME_TO_CODE = {
    name.lower(): code
    for code, name in constants.COLOR_NAMES_DICT.items()
    if len(code) == 2
}

ARCHETYPE_NAME_TO_CODE = {
    name.lower(): code
    for code, name in constants.COLOR_NAMES_DICT.items()
    if len(code) >= 2
}

if not os.path.exists(TROPHY_FOLDER):
    os.makedirs(TROPHY_FOLDER)


class TrophyDeckEntry(BaseModel):
    source: str = ""
    archetype: str = ""
    wins: int = 0
    cards: Dict[str, int] = Field(default_factory=dict)


class TrophySummaryItem(BaseModel):
    name: str = ""
    trophy_wins: int = 0
    trophy_count: int = 0
    total_games: int = 0


class TrophyAnalysisMeta(BaseModel):
    set_code: str = ""
    format_name: str = ""
    generated_at: str = ""
    source_urls: Dict[str, str] = Field(default_factory=dict)


class TrophyAnalysisResult(BaseModel):
    meta: TrophyAnalysisMeta = TrophyAnalysisMeta()
    archetypes: List[TrophySummaryItem] = Field(default_factory=list)
    cards: List[TrophySummaryItem] = Field(default_factory=list)


def _canonicalize_pair(code: str) -> str:
    if not code:
        return ""

    order = {"W": 0, "U": 1, "B": 2, "R": 3, "G": 4}
    colors = [c for c in code if c in order]
    unique_colors = []
    for color in colors:
        if color not in unique_colors:
            unique_colors.append(color)

    if len(unique_colors) < 2:
        return ""

    pair = sorted(unique_colors[:2], key=lambda c: order[c])
    return "".join(pair)


def _extract_17lands_archetype(colors: str) -> str:
    if not colors:
        return ""

    primary = "".join([c for c in colors if c.isupper()])
    return _canonicalize_pair(primary)


def _extract_untapped_archetype(archetype_text: str) -> str:
    if not archetype_text:
        return ""

    normalized = archetype_text.strip().lower()
    normalized = normalized.split("splashing")[0].strip()

    if normalized in ARCHETYPE_NAME_TO_CODE:
        return _canonicalize_pair(ARCHETYPE_NAME_TO_CODE[normalized])

    for archetype_name, archetype_code in ARCHETYPE_NAME_TO_CODE.items():
        if archetype_name in normalized:
            return _canonicalize_pair(archetype_code)

    return ""


def _to_slug(set_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", set_name.lower()).strip("-")
    return slug


def _extract_next_data_trophy_rows(html_text: str) -> List[Dict]:
    next_data_match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html_text,
        flags=re.S,
    )
    if not next_data_match:
        return []

    try:
        next_data = json.loads(next_data_match.group(1))
    except json.JSONDecodeError:
        return []

    return (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("ssrProps", {})
        .get("trophyDecksByEvent", {})
        .get("data", [])
    )


def _fetch_untapped_html_with_playwright(url: str) -> str:
    global _PLAYWRIGHT_UNAVAILABLE_LOGGED
    global _PLAYWRIGHT_RUNTIME_FAILURE_LOGGED

    try:
        from playwright.sync_api import sync_playwright
    except Exception as error:
        if not _PLAYWRIGHT_UNAVAILABLE_LOGGED:
            logger.warning(
                f"Playwright unavailable ({error}); falling back to non-browser Untapped fetch."
            )
            _PLAYWRIGHT_UNAVAILABLE_LOGGED = True
        return ""

    html_text = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)

            last_count = 0
            stalled_scrolls = 0
            max_scrolls = 80

            for _ in range(max_scrolls):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1200)

                current_count = page.locator('a[href*="/deck/"][href*="/draft-replay"]').count()
                if current_count > last_count:
                    last_count = current_count
                    stalled_scrolls = 0
                else:
                    stalled_scrolls += 1

                if stalled_scrolls >= 4:
                    break

            html_text = page.content()
            browser.close()
    except Exception as error:
        if not _PLAYWRIGHT_RUNTIME_FAILURE_LOGGED:
            logger.warning(
                f"Playwright scraping failed ({error}); falling back to non-browser Untapped fetch."
            )
            _PLAYWRIGHT_RUNTIME_FAILURE_LOGGED = True

    return html_text


def _parse_untapped_deck_blocks(html_text: str, deck_ids: List[str]) -> List[Dict]:
    blocks = []
    markers = []
    for deck_id in deck_ids:
        marker = f"/deck/{deck_id}/draft-replay"
        idx = html_text.find(marker)
        if idx >= 0:
            markers.append((deck_id, idx))

    markers.sort(key=lambda item: item[1])

    for index, (deck_id, start) in enumerate(markers):
        end = len(html_text) if index == len(markers) - 1 else markers[index + 1][1]
        segment = html_text[start:end]
        prefix = html_text[max(0, start - 1500):start]
        combined = f"{prefix} {segment}"

        span_matches = re.findall(r"<span[^>]*>([^<]+)</span>", prefix)
        archetype_text = ""
        fallback_text = ""
        for candidate in reversed(span_matches):
            if candidate and not fallback_text:
                fallback_text = candidate.strip()
            if any(k in candidate.lower() for k in list(GUILD_NAME_TO_CODE.keys()) + ["splash"]):
                archetype_text = candidate.strip()
                break
        if not archetype_text:
            archetype_text = fallback_text

        cards = defaultdict(int)
        for card_name, card_count in re.findall(r'(?:aria-label|alt)="([^\"]+?),\s*(\d+)x"', segment):
            cleaned = card_name.strip()
            if not cleaned:
                continue
            cards[cleaned] += int(card_count)

        wins = None
        record_match = re.search(r'(\d+)\s*[\-–]\s*(\d+)', combined)
        if record_match:
            wins = int(record_match.group(1))

        blocks.append({
            "deck_id": deck_id,
            "archetype_text": archetype_text,
            "cards": dict(cards),
            "wins": wins,
        })

    return blocks


def _fetch_17lands_trophy_decks(set_code: str, event_type: str, max_decks: int = 30) -> List[TrophyDeckEntry]:
    payload = {
        "expansion": set_code,
        "event_type": event_type,
        "card_names": [],
        "ranks": [],
        "deck_colors": [],
    }

    response = requests.post("https://www.17lands.com/data/trophies/", json=payload, timeout=20)
    response.raise_for_status()
    trophies = response.json()[:max_decks]

    entries: List[TrophyDeckEntry] = []
    for trophy in trophies:
        aggregate_id = trophy.get("aggregate_id", "")
        deck_index = trophy.get("deck_index", 0)
        wins = int(trophy.get("wins", 0))
        archetype = _extract_17lands_archetype(trophy.get("colors", ""))
        if not aggregate_id:
            continue

        try:
            preview_resp = requests.get(
                "https://www.17lands.com/data/event_preview",
                params={"draft_id": aggregate_id},
                timeout=20,
            )
            preview_resp.raise_for_status()
            preview = preview_resp.json()

            decks = preview.get("decks", [])
            card_lookup = preview.get("cards", {})
            if not isinstance(card_lookup, dict) or deck_index >= len(decks):
                continue

            groups = decks[deck_index].get("groups", [])
            main_deck = next((g for g in groups if g.get("name") == "Maindeck"), None)
            if not main_deck:
                continue

            cards = defaultdict(int)
            for card_id in main_deck.get("cards", []):
                card_data = card_lookup.get(str(card_id)) or card_lookup.get(card_id)
                if card_data and "name" in card_data:
                    cards[card_data["name"]] += 1

            entries.append(
                TrophyDeckEntry(
                    source="17Lands",
                    archetype=archetype,
                    wins=wins,
                    cards=dict(cards),
                )
            )
        except Exception as error:
            logger.error(error)

    return entries


def _fetch_untapped_trophy_decks(set_name: str, event_type: str) -> List[TrophyDeckEntry]:
    set_slug = _to_slug(set_name)
    url = UNTAPPED_URL_TEMPLATE.format(set_slug=set_slug, event_type=event_type)
    html_text = _fetch_untapped_html_with_playwright(url)
    if not html_text:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        html_text = response.text

    trophy_rows = _extract_next_data_trophy_rows(html_text)
    trophy_wins = {}
    for row in trophy_rows:
        deck_id = row.get("di", "")
        if deck_id:
            trophy_wins[deck_id] = int(row.get("wi", 0) or 0)

    html_deck_ids = re.findall(r'/deck/([A-Za-z0-9\-]+)/draft-replay', html_text)
    deck_ids = [row.get("di", "") for row in trophy_rows if row.get("di")]
    deck_ids.extend(html_deck_ids)
    deck_ids = list(dict.fromkeys([deck_id for deck_id in deck_ids if deck_id]))

    if not deck_ids:
        return []

    deck_blocks = _parse_untapped_deck_blocks(html_text, deck_ids)
    deck_map = {deck["deck_id"]: deck for deck in deck_blocks if deck.get("cards")}

    default_wins_by_event = {
        "TRADITIONAL_HUMAN_DRAFT": 3,
        "PREMIER_HUMAN_DRAFT": 7,
    }
    default_wins = default_wins_by_event.get(event_type, 3)

    entries: List[TrophyDeckEntry] = []
    for deck_id in deck_ids:
        deck_data = deck_map.get(deck_id)
        if not deck_data:
            continue

        archetype_code = _extract_untapped_archetype(deck_data.get("archetype_text", ""))
        wins = trophy_wins.get(deck_id)
        if wins is None:
            wins = deck_data.get("wins")
        if wins is None:
            wins = default_wins

        entries.append(
            TrophyDeckEntry(
                source="Untapped.gg",
                archetype=archetype_code,
                wins=wins,
                cards=deck_data.get("cards", {}),
            )
        )

    return entries


def _fetch_17lands_archetype_games(set_code: str, event_type: str, start_date: str, end_date: str) -> Dict[str, int]:
    url = "https://www.17lands.com/color_ratings/data"
    response = requests.get(
        url,
        params={
            "expansion": set_code,
            "event_type": event_type,
            "start_date": start_date,
            "end_date": end_date,
            "combine_splash": "true",
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    archetype_games = {}
    for row in data:
        if row.get("is_summary"):
            continue
        color_name = row.get("color_name", "")
        match = re.search(r"\(([WUBRG]{2,5})\)", color_name)
        if not match:
            continue
        pair = _canonicalize_pair(match.group(1))
        if len(pair) == 2:
            archetype_games[pair] = int(row.get("games", 0) or 0)

    return archetype_games


def _load_dataset_totals(set_code: str) -> Dict[str, Dict[str, int]]:
    result = {
        "cards": {},
        "meta": {
            "game_count": 0,
        },
    }

    file_path = os.path.join(constants.SETS_FOLDER, f"{set_code}_{constants.SET_FILE_SUFFIX}")
    if not os.path.exists(file_path):
        return result

    with open(file_path, "r", encoding="utf8", errors="replace") as data_file:
        data = json.load(data_file)

    result["meta"]["game_count"] = int(data.get("meta", {}).get("game_count", 0) or 0)

    card_totals = {}
    for card in data.get("card_ratings", {}).values():
        deck_colors = card.get("deck_colors", {})
        total_games = 0

        if "All Decks" in deck_colors and isinstance(deck_colors["All Decks"], dict):
            total_games = int(deck_colors["All Decks"].get("ngp", 0) or 0)
        else:
            for color_data in deck_colors.values():
                if isinstance(color_data, dict):
                    total_games += int(color_data.get("ngp", 0) or 0)

        card_totals[card.get("name", "")] = total_games

    result["cards"] = card_totals
    return result


def analyze_trophy_decks(set_code: str, set_name: str, format_name: str, start_date: Optional[str] = None,
                         end_date: Optional[str] = None) -> TrophyAnalysisResult:
    if format_name not in FORMAT_OPTIONS:
        raise ValueError("Invalid format")

    format_data = FORMAT_OPTIONS[format_name]
    format_17lands = format_data["17lands"]
    format_untapped = format_data["untapped"]
    analysis_start_date = start_date if start_date else "2019-01-01"
    analysis_end_date = end_date if end_date else datetime.now().strftime("%Y-%m-%d")

    source_urls = {
        "Untapped.gg": UNTAPPED_URL_TEMPLATE.format(set_slug=_to_slug(set_name), event_type=format_untapped),
        "17Lands Color Ratings": f"https://www.17lands.com/color_ratings/data?expansion={set_code}&event_type={format_17lands}",
    }

    all_entries: List[TrophyDeckEntry] = []
    try:
        all_entries.extend(_fetch_untapped_trophy_decks(set_name, format_untapped))
    except Exception as error:
        logger.error(error)

    archetype_trophy_wins = defaultdict(int)
    archetype_trophy_count = defaultdict(int)
    card_trophy_wins = defaultdict(int)
    card_trophy_copies = defaultdict(int)

    for entry in all_entries:
        if entry.archetype:
            archetype_trophy_wins[entry.archetype] += entry.wins
            archetype_trophy_count[entry.archetype] += 1

        for card_name, card_count in entry.cards.items():
            card_trophy_copies[card_name] += card_count
            card_trophy_wins[card_name] += card_count * entry.wins

    dataset_totals = _load_dataset_totals(set_code)
    archetype_games = _fetch_17lands_archetype_games(set_code, format_17lands, analysis_start_date, analysis_end_date)

    archetype_rows = []
    for archetype, trophy_wins in archetype_trophy_wins.items():
        archetype_rows.append(
            TrophySummaryItem(
                name=archetype,
                trophy_wins=trophy_wins,
                trophy_count=archetype_trophy_count[archetype],
                total_games=int(archetype_games.get(archetype, 0)),
            )
        )

    card_rows = []
    for card_name, trophy_wins in card_trophy_wins.items():
        card_rows.append(
            TrophySummaryItem(
                name=card_name,
                trophy_wins=trophy_wins,
                trophy_count=card_trophy_copies[card_name],
                total_games=int(dataset_totals["cards"].get(card_name, 0)),
            )
        )

    archetype_rows.sort(key=lambda item: item.trophy_wins, reverse=True)
    card_rows.sort(key=lambda item: item.trophy_wins, reverse=True)

    result = TrophyAnalysisResult(
        meta=TrophyAnalysisMeta(
            set_code=set_code,
            format_name=format_name,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source_urls=source_urls,
        ),
        archetypes=archetype_rows,
        cards=card_rows,
    )

    output_file = os.path.join(
        TROPHY_FOLDER,
        f"Trophy_{set_code}_{format_data['17lands']}.json",
    )
    with open(output_file, "w", encoding="utf8", errors="replace") as analysis_file:
        json.dump(result.model_dump(), analysis_file, ensure_ascii=False, indent=4)

    return result


class TrophyAnalysisWindow(ScaledWindow):
    _instance_open = False

    def __init__(self, scale_factor: int, fonts_dict: Dict, set_info: Dict):
        if TrophyAnalysisWindow._instance_open:
            return
        TrophyAnalysisWindow._instance_open = True

        super().__init__()
        self.scale_factor = scale_factor
        self.fonts_dict = fonts_dict
        self.set_info = set_info
        self.window = None
        self.set_selection = None
        self.format_selection = None
        self.status_text = None
        self.archetype_table = None
        self.card_table = None

        self.__enter()

    def __enter(self):
        self.window = tkinter.Toplevel()
        self.window.wm_title("Trophy Deck Analysis")
        self.window.protocol("WM_DELETE_WINDOW", lambda window=self.window: self.__exit(window))
        self.window.resizable(width=False, height=True)
        self.window.attributes("-topmost", True)

        location_x, location_y = identify_safe_coordinates(
            self.window,
            self._scale_value(1100),
            self._scale_value(600),
            self._scale_value(250),
            self._scale_value(20),
        )
        self.window.wm_geometry(f"+{location_x}+{location_y}")

        try:
            headers_archetype = {
                "Archetype": {"width": .18, "anchor": tkinter.W},
                "Trophy Wins": {"width": .13, "anchor": tkinter.CENTER},
                "Trophy Decks": {"width": .13, "anchor": tkinter.CENTER},
                "17Lands Games": {"width": .18, "anchor": tkinter.CENTER},
                "Trophy Win %": {"width": .13, "anchor": tkinter.CENTER},
                "Games %": {"width": .13, "anchor": tkinter.CENTER},
                "Index": {"width": .12, "anchor": tkinter.CENTER},
            }

            headers_cards = {
                "Card": {"width": .34, "anchor": tkinter.W},
                "Trophy Wins": {"width": .13, "anchor": tkinter.CENTER},
                "Copies": {"width": .13, "anchor": tkinter.CENTER},
                "Dataset Games": {"width": .18, "anchor": tkinter.CENTER},
                "Win/Copies": {"width": .11, "anchor": tkinter.CENTER},
                "Copies/Games": {"width": .11, "anchor": tkinter.CENTER},
            }

            set_label = Label(self.window, text="Set:", style="SetOptions.TLabel", anchor="e")
            format_label = Label(self.window, text="Format:", style="SetOptions.TLabel", anchor="e")

            set_choices = list(self.set_info.keys())
            default_set = set_choices[0] if set_choices else ""

            self.set_selection = tkinter.StringVar(self.window)
            self.set_selection.set(default_set)

            self.format_selection = tkinter.StringVar(self.window)
            self.format_selection.set("Traditional Draft")

            set_entry = OptionMenu(self.window, self.set_selection, default_set, *set_choices)
            format_entry = OptionMenu(self.window, self.format_selection,
                                      self.format_selection.get(), *FORMAT_OPTIONS.keys())

            menu = self.window.nametowidget(set_entry['menu'])
            menu.config(font=self.fonts_dict["All.TMenubutton"])
            menu = self.window.nametowidget(format_entry['menu'])
            menu.config(font=self.fonts_dict["All.TMenubutton"])

            analyze_button = Button(self.window, text="ANALYZE", command=self.__analyze)

            self.status_text = tkinter.StringVar()
            self.status_text.set("Choose set/format and click ANALYZE")
            status_label = Label(self.window, textvariable=self.status_text, style="Status.TLabel", anchor="w")

            archetype_frame = tkinter.Frame(self.window)
            card_frame = tkinter.Frame(self.window)

            self.archetype_table = self._create_header(
                "trophy_archetype_table",
                archetype_frame,
                12,
                self.fonts_dict["Sets.TableRow"],
                headers_archetype,
                self._scale_value(760),
                True,
                True,
                "Set.Treeview",
                True,
            )

            self.card_table = self._create_header(
                "trophy_card_table",
                card_frame,
                16,
                self.fonts_dict["Sets.TableRow"],
                headers_cards,
                self._scale_value(760),
                True,
                True,
                "Set.Treeview",
                True,
            )

            set_label.grid(row=0, column=0, sticky="nsew")
            set_entry.grid(row=0, column=1, sticky="nsew")
            format_label.grid(row=0, column=2, sticky="nsew")
            format_entry.grid(row=0, column=3, sticky="nsew")
            analyze_button.grid(row=0, column=4, sticky="nsew")
            status_label.grid(row=1, column=0, columnspan=5, sticky="nsew")

            archetype_frame.grid(row=2, column=0, columnspan=5, sticky="nsew")
            card_frame.grid(row=3, column=0, columnspan=5, sticky="nsew")

            self.archetype_table.pack(expand=True, fill="both")
            self.card_table.pack(expand=True, fill="both")
        except Exception as error:
            logger.error(error)

    def __exit(self, window):
        TrophyAnalysisWindow._instance_open = False
        window.destroy()

    def __clear_tables(self):
        for row in self.archetype_table.get_children():
            self.archetype_table.delete(row)
        for row in self.card_table.get_children():
            self.card_table.delete(row)

    def __analyze(self):
        if not self.set_selection or not self.format_selection:
            return

        set_name = self.set_selection.get()
        format_name = self.format_selection.get()
        set_data = self.set_info.get(set_name)
        if not set_data:
            return

        set_code = set_data.seventeenlands[0]

        self.__clear_tables()
        self.status_text.set("Fetching and processing trophy decks...")
        self.window.update()

        try:
            result = analyze_trophy_decks(
                set_code,
                set_name,
                format_name,
                start_date=getattr(set_data, "start_date", None),
                end_date=datetime.now().strftime("%Y-%m-%d"),
            )

            total_trophy_wins = sum(item.trophy_wins for item in result.archetypes)
            total_games = sum(item.total_games for item in result.archetypes)

            for row_index, item in enumerate(result.archetypes[:25]):
                trophy_share = (item.trophy_wins / total_trophy_wins * 100.0) if total_trophy_wins else 0.0
                games_share = (item.total_games / total_games * 100.0) if total_games else 0.0
                index = (item.trophy_wins / item.total_games) if item.total_games else 0.0

                row_tag = self._identify_table_row_tag(False, "", row_index)
                self.archetype_table.insert(
                    "",
                    tkinter.END,
                    values=(
                        item.name,
                        item.trophy_wins,
                        item.trophy_count,
                        item.total_games,
                        f"{trophy_share:.2f}",
                        f"{games_share:.2f}",
                        f"{index:.4f}",
                    ),
                    tags=row_tag,
                )

            for row_index, item in enumerate(result.cards[:120]):
                win_per_copy = (item.trophy_wins / item.trophy_count) if item.trophy_count else 0.0
                copy_per_game = (item.trophy_count / item.total_games) if item.total_games else 0.0

                row_tag = self._identify_table_row_tag(False, "", row_index)
                self.card_table.insert(
                    "",
                    tkinter.END,
                    values=(
                        item.name,
                        item.trophy_wins,
                        item.trophy_count,
                        item.total_games,
                        f"{win_per_copy:.4f}",
                        f"{copy_per_game:.6f}",
                    ),
                    tags=row_tag,
                )

            self.status_text.set(
                f"Analyzed {result.meta.set_code} {result.meta.format_name}. Saved to Trophy/Trophy_{result.meta.set_code}_{FORMAT_OPTIONS[result.meta.format_name]['17lands']}.json"
            )
        except Exception as error:
            logger.error(error)
            self.status_text.set("Analysis failed. Check Debug logs and verify set dataset exists in Sets/.")
