"""Central database access module for MTGA Draft 17Lands.

All persistent data (card datasets, configuration, archetypes, trophy analysis)
is stored in a single SQLite file (mtga_draft.db by default).
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Optional

from src.constants import DB_FILE

DB_PATH = DB_FILE

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_meta (
    set_code TEXT PRIMARY KEY,
    collection_date TEXT DEFAULT '',
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    version REAL DEFAULT 0.0,
    game_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS color_ratings (
    set_code TEXT NOT NULL,
    color_pair TEXT NOT NULL,
    win_rate REAL NOT NULL,
    PRIMARY KEY (set_code, color_pair)
);

CREATE TABLE IF NOT EXISTS cards (
    arena_id TEXT NOT NULL,
    set_code TEXT NOT NULL,
    name TEXT NOT NULL,
    cmc INTEGER DEFAULT 0,
    mana_cost TEXT DEFAULT '',
    isprimarycard INTEGER DEFAULT 0,
    linkedfacetype INTEGER DEFAULT 0,
    rarity TEXT DEFAULT '',
    colors TEXT DEFAULT '[]',
    types TEXT DEFAULT '[]',
    image TEXT DEFAULT '[]',
    PRIMARY KEY (arena_id, set_code)
);

CREATE TABLE IF NOT EXISTS card_deck_stats (
    arena_id TEXT NOT NULL,
    set_code TEXT NOT NULL,
    color_filter TEXT NOT NULL,
    alsa REAL DEFAULT 0.0,
    ata REAL DEFAULT 0.0,
    iwd REAL DEFAULT 0.0,
    gihwr REAL DEFAULT 0.0,
    ohwr REAL DEFAULT 0.0,
    gpwr REAL DEFAULT 0.0,
    gnswr REAL DEFAULT 0.0,
    gdwr REAL DEFAULT 0.0,
    ngp INTEGER DEFAULT 0,
    ngoh INTEGER DEFAULT 0,
    gih INTEGER DEFAULT 0,
    ngnd INTEGER DEFAULT 0,
    ngd INTEGER DEFAULT 0,
    PRIMARY KEY (arena_id, set_code, color_filter)
);

CREATE TABLE IF NOT EXISTS archetypes_config (
    set_code TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trophy_analysis (
    set_code TEXT NOT NULL,
    format_name TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (set_code, format_name)
);

CREATE TABLE IF NOT EXISTS configuration (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_set_name ON cards (set_code, name);
CREATE INDEX IF NOT EXISTS idx_deck_stats_card ON card_deck_stats (arena_id, set_code);
"""


def _resolve_path(db_path: Optional[str] = None) -> str:
    return db_path if db_path is not None else DB_PATH


def init_db(db_path: Optional[str] = None) -> None:
    """Creates schema if tables don't exist; sets WAL mode."""
    path = _resolve_path(db_path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)


@contextmanager
def _connection(db_path: Optional[str] = None):
    """Context manager that yields a sqlite3.Connection with commit/rollback."""
    path = _resolve_path(db_path)
    conn = sqlite3.connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

def save_dataset(set_code: str, dataset_dict: dict, db_path: Optional[str] = None) -> None:
    """Upsert meta, color_ratings, cards, and card_deck_stats in one transaction."""
    init_db(db_path)
    meta = dataset_dict.get("meta", {})
    color_ratings = dataset_dict.get("color_ratings", {})
    card_ratings = dataset_dict.get("card_ratings", {})

    with _connection(db_path) as conn:
        conn.execute(
            """INSERT INTO dataset_meta
                   (set_code, collection_date, start_date, end_date, version, game_count)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(set_code) DO UPDATE SET
                   collection_date = excluded.collection_date,
                   start_date      = excluded.start_date,
                   end_date        = excluded.end_date,
                   version         = excluded.version,
                   game_count      = excluded.game_count""",
            (
                set_code,
                meta.get("collection_date", ""),
                meta.get("start_date", ""),
                meta.get("end_date", ""),
                meta.get("version", 0.0),
                int(meta.get("game_count", 0) or 0),
            ),
        )

        conn.execute("DELETE FROM color_ratings WHERE set_code=?", (set_code,))
        for color_pair, win_rate in color_ratings.items():
            conn.execute(
                "INSERT INTO color_ratings (set_code, color_pair, win_rate) VALUES (?, ?, ?)",
                (set_code, color_pair, float(win_rate)),
            )

        conn.execute("DELETE FROM cards WHERE set_code=?", (set_code,))
        conn.execute("DELETE FROM card_deck_stats WHERE set_code=?", (set_code,))

        for arena_id, card in card_ratings.items():
            conn.execute(
                """INSERT INTO cards
                       (arena_id, set_code, name, cmc, mana_cost, isprimarycard,
                        linkedfacetype, rarity, colors, types, image)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(arena_id),
                    set_code,
                    card.get("name", ""),
                    int(card.get("cmc", 0) or 0),
                    card.get("mana_cost", "") or "",
                    int(card.get("isprimarycard", 0) or 0),
                    int(card.get("linkedfacetype", 0) or 0),
                    card.get("rarity", "") or "",
                    json.dumps(card.get("colors", [])),
                    json.dumps(card.get("types", [])),
                    json.dumps(card.get("image", [])),
                ),
            )
            for color_filter, stats in card.get("deck_colors", {}).items():
                conn.execute(
                    """INSERT INTO card_deck_stats
                           (arena_id, set_code, color_filter,
                            alsa, ata, iwd, gihwr, ohwr, gpwr, gnswr, gdwr,
                            ngp, ngoh, gih, ngnd, ngd)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(arena_id),
                        set_code,
                        color_filter,
                        float(stats.get("alsa", 0.0) or 0.0),
                        float(stats.get("ata", 0.0) or 0.0),
                        float(stats.get("iwd", 0.0) or 0.0),
                        float(stats.get("gihwr", 0.0) or 0.0),
                        float(stats.get("ohwr", 0.0) or 0.0),
                        float(stats.get("gpwr", 0.0) or 0.0),
                        float(stats.get("gnswr", 0.0) or 0.0),
                        float(stats.get("gdwr", 0.0) or 0.0),
                        int(stats.get("ngp", 0) or 0),
                        int(stats.get("ngoh", 0) or 0),
                        int(stats.get("gih", 0) or 0),
                        int(stats.get("ngnd", 0) or 0),
                        int(stats.get("ngd", 0) or 0),
                    ),
                )


def load_dataset(set_code: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Reconstruct the original {meta, color_ratings, card_ratings} dict from normalized tables.

    Returns None if the set_code is not found in the database.
    """
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return None

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            "SELECT * FROM dataset_meta WHERE set_code=?", (set_code,)
        ).fetchone()
        if not row:
            return None

        meta = {
            "collection_date": row["collection_date"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "version": row["version"],
            "game_count": row["game_count"],
        }

        color_ratings: Dict[str, float] = {}
        for cr_row in conn.execute(
            "SELECT color_pair, win_rate FROM color_ratings WHERE set_code=?", (set_code,)
        ):
            color_ratings[cr_row["color_pair"]] = cr_row["win_rate"]

        card_ratings: Dict[str, dict] = {}
        for card_row in conn.execute(
            "SELECT * FROM cards WHERE set_code=?", (set_code,)
        ):
            arena_id = card_row["arena_id"]
            card_ratings[arena_id] = {
                "name": card_row["name"],
                "cmc": card_row["cmc"],
                "mana_cost": card_row["mana_cost"],
                "isprimarycard": card_row["isprimarycard"],
                "linkedfacetype": card_row["linkedfacetype"],
                "rarity": card_row["rarity"],
                "colors": json.loads(card_row["colors"]),
                "types": json.loads(card_row["types"]),
                "image": json.loads(card_row["image"]),
                "deck_colors": {},
            }

        for stats_row in conn.execute(
            "SELECT * FROM card_deck_stats WHERE set_code=?", (set_code,)
        ):
            arena_id = stats_row["arena_id"]
            if arena_id not in card_ratings:
                continue
            card_ratings[arena_id]["deck_colors"][stats_row["color_filter"]] = {
                "alsa": stats_row["alsa"],
                "ata": stats_row["ata"],
                "iwd": stats_row["iwd"],
                "gihwr": stats_row["gihwr"],
                "ohwr": stats_row["ohwr"],
                "gpwr": stats_row["gpwr"],
                "gnswr": stats_row["gnswr"],
                "gdwr": stats_row["gdwr"],
                "ngp": stats_row["ngp"],
                "ngoh": stats_row["ngoh"],
                "gih": stats_row["gih"],
                "ngnd": stats_row["ngnd"],
                "ngd": stats_row["ngd"],
            }

    return {
        "meta": meta,
        "color_ratings": color_ratings,
        "card_ratings": card_ratings,
    }


def delete_dataset(set_code: str, db_path: Optional[str] = None) -> None:
    """Remove a set from all dataset tables."""
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return
    with _connection(db_path) as conn:
        conn.execute("DELETE FROM card_deck_stats WHERE set_code=?", (set_code,))
        conn.execute("DELETE FROM cards WHERE set_code=?", (set_code,))
        conn.execute("DELETE FROM color_ratings WHERE set_code=?", (set_code,))
        conn.execute("DELETE FROM dataset_meta WHERE set_code=?", (set_code,))


def list_datasets(db_path: Optional[str] = None) -> List[str]:
    """Return all set_codes present in dataset_meta."""
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return []
    with sqlite3.connect(path) as conn:
        rows = conn.execute("SELECT set_code FROM dataset_meta").fetchall()
    return [row[0] for row in rows]


def list_datasets_with_meta(db_path: Optional[str] = None) -> List[Dict]:
    """Return list of dicts with all dataset_meta columns for every stored set."""
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM dataset_meta").fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def save_configuration(config_dict: dict, db_path: Optional[str] = None) -> None:
    """Persist the singleton configuration row (upsert)."""
    init_db(db_path)
    with _connection(db_path) as conn:
        conn.execute(
            """INSERT INTO configuration (id, data) VALUES (1, ?)
               ON CONFLICT(id) DO UPDATE SET data = excluded.data""",
            (json.dumps(config_dict),),
        )


def load_configuration(db_path: Optional[str] = None) -> Optional[dict]:
    """Load the singleton configuration. Returns None if no row exists."""
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT data FROM configuration WHERE id=1").fetchone()
    if not row:
        return None
    return json.loads(row[0])


# ---------------------------------------------------------------------------
# Archetype config
# ---------------------------------------------------------------------------

def save_archetype_config(set_code: str, config_dict: dict, db_path: Optional[str] = None) -> None:
    """Persist archetype config for a set (upsert)."""
    init_db(db_path)
    with _connection(db_path) as conn:
        conn.execute(
            """INSERT INTO archetypes_config (set_code, data) VALUES (?, ?)
               ON CONFLICT(set_code) DO UPDATE SET data = excluded.data""",
            (set_code, json.dumps(config_dict)),
        )


def load_archetype_config(set_code: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Load archetype config for a set. Returns None if not found."""
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT data FROM archetypes_config WHERE set_code=?", (set_code,)
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


# ---------------------------------------------------------------------------
# Trophy analysis
# ---------------------------------------------------------------------------

def save_trophy_analysis(
    set_code: str, format_name: str, data_dict: dict, db_path: Optional[str] = None
) -> None:
    """Persist trophy analysis result for (set_code, format_name) (upsert)."""
    init_db(db_path)
    with _connection(db_path) as conn:
        conn.execute(
            """INSERT INTO trophy_analysis (set_code, format_name, data) VALUES (?, ?, ?)
               ON CONFLICT(set_code, format_name) DO UPDATE SET data = excluded.data""",
            (set_code, format_name, json.dumps(data_dict)),
        )


def load_trophy_analysis(
    set_code: str, format_name: str, db_path: Optional[str] = None
) -> Optional[dict]:
    """Load trophy analysis result. Returns None if not found."""
    path = _resolve_path(db_path)
    if not os.path.exists(path):
        return None
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT data FROM trophy_analysis WHERE set_code=? AND format_name=?",
            (set_code, format_name),
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])
