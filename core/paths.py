"""Where the app keeps its files.

    <root>/audio_output/   generated speech, named ddmmyyyy_HHMMSS.wav
    <root>/logs/           rotating log files
    <root>/user_data/      settings.json, draft.txt, pronunciations.json

<root> is the project folder, or the folder holding KokoroTTS.exe when the
app runs as a PyInstaller build (the bundle's own folder is read-only).
"""
import logging
import os
import shutil
import sys
from datetime import datetime

log = logging.getLogger(__name__)

if getattr(sys, "frozen", False):
    ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

AUDIO_DIR = os.path.join(ROOT, "audio_output")
LOGS_DIR = os.path.join(ROOT, "logs")
USER_DATA_DIR = os.path.join(ROOT, "user_data")

SETTINGS_PATH = os.path.join(USER_DATA_DIR, "settings.json")
DRAFT_PATH = os.path.join(USER_DATA_DIR, "draft.txt")
PRONUNCIATIONS_PATH = os.path.join(USER_DATA_DIR, "pronunciations.json")
LOG_PATH = os.path.join(LOGS_DIR, "kokoro_tts.log")

OUTPUT_NAME_FORMAT = "%d%m%Y_%H%M%S"   # e.g. 04102026_203015


def ensure_dirs():
    for d in (AUDIO_DIR, LOGS_DIR, USER_DATA_DIR):
        os.makedirs(d, exist_ok=True)


def new_output_path(when: datetime = None) -> str:
    """Return audio_output/ddmmyyyy_HHMMSS.wav, adding _2, _3… if taken."""
    os.makedirs(AUDIO_DIR, exist_ok=True)
    stem = (when or datetime.now()).strftime(OUTPUT_NAME_FORMAT)
    path = os.path.join(AUDIO_DIR, f"{stem}.wav")
    n = 2
    while os.path.exists(path):
        path = os.path.join(AUDIO_DIR, f"{stem}_{n}.wav")
        n += 1
    return path


def migrate_legacy_files():
    """Move files older versions left in the project root into the new folders.

    Never overwrites: a file is only moved when the destination doesn't exist.
    Returns a list of (old, new) paths that were moved.
    """
    moves = [
        ("settings.json", SETTINGS_PATH),
        ("draft.txt", DRAFT_PATH),
        ("pronunciations.json", PRONUNCIATIONS_PATH),
        ("kokoro_tts.log", os.path.join(LOGS_DIR, "kokoro_tts_legacy.log")),
        ("app_run.log", os.path.join(LOGS_DIR, "app_run.log")),
        ("audio_output.wav", os.path.join(AUDIO_DIR, "audio_output.wav")),
        ("output.wav", os.path.join(AUDIO_DIR, "output.wav")),
    ]
    done = []
    for name, dest in moves:
        src = os.path.join(ROOT, name)
        if os.path.isfile(src) and not os.path.exists(dest):
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(src, dest)
                done.append((src, dest))
            except OSError as exc:
                log.warning("Could not move %s: %s", src, exc)
    return done


def open_folder(path: str):
    """Open *path* in the system file manager."""
    os.makedirs(path, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 — opening our own output folder
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", path])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", path])
