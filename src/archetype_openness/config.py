import os
from typing import Optional
from src.logger import create_logger
from src.archetype_openness.models import ArchetypeConfig

logger = create_logger()

def _set_code_from_path(file_path: str) -> str:
    """Extract set_code from an archetype file path.

    "Archetypes/OTJ_archetypes.json" → "OTJ"
    Falls back to the full basename if no underscore is found.
    """
    basename = os.path.basename(file_path)
    # Strip extension
    name = basename.rsplit(".", 1)[0] if "." in basename else basename
    return name.split("_")[0].upper()


def load_archetype_config(file_path: str, db_path: Optional[str] = None) -> Optional[ArchetypeConfig]:
    """Load archetype config from the SQLite database.

    set_code is derived from file_path for backward compatibility.
    Returns None if the config is not found.
    """
    import src.database as database
    try:
        set_code = _set_code_from_path(file_path)
        data = database.load_archetype_config(set_code, db_path)
        if data is None:
            logger.info("No archetype config found for %s in DB", set_code)
            return None
        return ArchetypeConfig.model_validate(data)
    except Exception as error:
        logger.error("Failed to load archetype config: %s", error)
        return None


def save_archetype_config(config: ArchetypeConfig, file_path: str = None, db_path: Optional[str] = None) -> bool:
    """Save archetype config to the SQLite database.

    set_code is taken from config.set_code; file_path is kept for call-site compatibility.
    """
    import src.database as database
    try:
        database.save_archetype_config(config.set_code, config.model_dump(), db_path)
        return True
    except Exception as error:
        logger.error("Failed to save archetype config: %s", error)
        return False
