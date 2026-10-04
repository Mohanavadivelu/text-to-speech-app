"""
Kokoro TTS — application entry point.
Run with:  python app.py   (or start.bat, which also sets up the venv)
"""
import logging
import sys

# Ensure the project root is on sys.path when running as a frozen EXE
if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)  # PyInstaller bundle dir

from core import paths
from core.logging_setup import setup_logging


def main():
    paths.ensure_dirs()
    moved = paths.migrate_legacy_files()
    log_file = setup_logging()
    log = logging.getLogger("app")
    log.info("Kokoro TTS starting · log file: %s", log_file)
    for old, new in moved:
        log.info("Moved %s -> %s", old, new)

    from core.engine import log_device_info
    log_device_info()

    from ui.app_window import KokoroApp
    app = KokoroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
