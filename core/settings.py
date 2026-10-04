"""Persist voice settings between launches in settings.json (git-ignored)."""
import json
import logging
import os

log = logging.getLogger(__name__)

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SETTINGS_PATH = os.path.join(_ROOT, "settings.json")

DEFAULTS = {
    "language": "American English",
    "voice": "af_heart",
    "blend_voice": None,
    "blend_ratio": 0.5,
    "speed": 1.0,
    "pitch": 0.0,
    "output_name": "audio_output",
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
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: data.get(k, v) for k, v in DEFAULTS.items()}, f, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except Exception as exc:
        log.warning("Could not save settings: %s", exc)
