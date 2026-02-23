"""One-time migration from JSON files to the SQLite database.

Call ``migrate_json_to_sqlite()`` on first startup (when mtga_draft.db
doesn't yet exist) to import all existing JSON data.
"""
import json
import os
from typing import List, Tuple

from src.logger import create_logger
import src.database as database

logger = create_logger()


def migrate_json_to_sqlite(db_path: str = None) -> Tuple[int, List[str]]:
    """Migrate all existing JSON files to the SQLite database.

    Steps:
      1. Init DB schema.
      2. Migrate config.json → configuration table.
      3. Migrate Sets/*.json → dataset tables.
      4. Migrate Archetypes/*.json → archetypes_config table.
      5. Migrate Trophy/*.json → trophy_analysis table.

    Returns:
        (migrated_count, error_list)
    """
    migrated_count = 0
    error_list: List[str] = []

    database.init_db(db_path)

    # --- 1. Configuration ---
    config_file = os.path.join(os.getcwd(), "config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8", errors="replace") as f:
                config_data = json.loads(f.read())
            database.save_configuration(config_data, db_path)
            migrated_count += 1
            logger.info("Migration: imported config.json")
        except Exception as error:
            msg = f"Failed to migrate config.json: {error}"
            error_list.append(msg)
            logger.error(msg)

    # --- 2. Sets/*.json → dataset tables ---
    sets_folder = os.path.join(os.getcwd(), "Sets")
    if os.path.exists(sets_folder):
        for filename in os.listdir(sets_folder):
            if not filename.endswith(".json"):
                continue
            segments = filename.split("_")
            # Only 2-segment files: "{SET}_Data.json"
            if len(segments) != 2:
                continue
            set_code = segments[0].upper()
            file_path = os.path.join(sets_folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.loads(f.read())
                database.save_dataset(set_code, data, db_path)
                migrated_count += 1
                logger.info("Migration: imported %s as set_code=%s", filename, set_code)
            except Exception as error:
                msg = f"Failed to migrate {filename}: {error}"
                error_list.append(msg)
                logger.error(msg)

    # --- 3. Archetypes/*.json → archetypes_config table ---
    archetypes_folder = os.path.join(os.getcwd(), "Archetypes")
    if os.path.exists(archetypes_folder):
        for filename in os.listdir(archetypes_folder):
            if not filename.endswith(".json"):
                continue
            # Expect filenames like "OTJ_archetypes.json" → set_code = "OTJ"
            set_code = filename.split("_")[0].upper()
            file_path = os.path.join(archetypes_folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.loads(f.read())
                database.save_archetype_config(set_code, data, db_path)
                migrated_count += 1
                logger.info("Migration: imported archetype %s as set_code=%s", filename, set_code)
            except Exception as error:
                msg = f"Failed to migrate archetype {filename}: {error}"
                error_list.append(msg)
                logger.error(msg)

    # --- 4. Trophy/*.json → trophy_analysis table ---
    trophy_folder = os.path.join(os.getcwd(), "Trophy")
    if os.path.exists(trophy_folder):
        for filename in os.listdir(trophy_folder):
            if not filename.endswith(".json"):
                continue
            # Expect "Trophy_{SET}_{FORMAT}.json" e.g. "Trophy_OTJ_TradDraft.json"
            parts = filename[:-5].split("_")  # strip .json, split
            if len(parts) < 3 or parts[0].upper() != "TROPHY":
                continue
            set_code = parts[1].upper()
            format_name = "_".join(parts[2:])
            file_path = os.path.join(trophy_folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.loads(f.read())
                database.save_trophy_analysis(set_code, format_name, data, db_path)
                migrated_count += 1
                logger.info(
                    "Migration: imported trophy %s as set_code=%s format=%s",
                    filename, set_code, format_name,
                )
            except Exception as error:
                msg = f"Failed to migrate trophy {filename}: {error}"
                error_list.append(msg)
                logger.error(msg)

    logger.info(
        "Migration complete: %d items migrated, %d errors",
        migrated_count,
        len(error_list),
    )
    return migrated_count, error_list
