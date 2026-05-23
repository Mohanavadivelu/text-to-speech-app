"""
Kokoro TTS — application entry point.
Run with:  python app.py
           python -m ui.app_window
"""
import logging
import sys
import os

# Ensure the project root is on sys.path when running as a frozen EXE
if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS  # PyInstaller temp/bundle dir
    sys.path.insert(0, _BASE)

from core.engine import log_device_info

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    log_device_info()

    from ui.app_window import KokoroApp
    app = KokoroApp()
    app.mainloop()
