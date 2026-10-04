"""
Kokoro TTS — application entry point.
Run with:  python app.py   (or start.bat, which also sets up the venv)
"""
import logging
import sys

# Ensure the project root is on sys.path when running as a frozen EXE
if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)  # PyInstaller bundle dir

# A windowed (--noconsole) build has no stdout/stderr; libraries that print or
# draw progress bars (e.g. model downloads) would crash writing to None.
import os
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

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
