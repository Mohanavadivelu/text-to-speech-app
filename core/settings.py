"""Persist settings between launches in user_data/settings.json (git-ignored)."""
import json
import logging
import os

from core import paths

log = logging.getLogger(__name__)

SETTINGS_PATH = paths.SETTINGS_PATH

DEFAULTS = {
    "language": "American English",
    "voice": "af_heart",
    "blend_voice": None,
    "blend_ratio": 0.5,
    "speed": 1.0,
    "pitch": 0.0,
    "text_font_size": 11,
}


def load() -> dict:
    """Return saved settings merged over the defaults. Never raises."""
    data = dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            data.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.warning("Ignoring unreadable settings file: %s", exc)
    return data


def save(data: dict):
    """Write settings atomically. Never raises."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: data.get(k, v) for k, v in DEFAULTS.items()}, f, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except Exception as exc:
        log.warning("Could not save settings: %s", exc)
