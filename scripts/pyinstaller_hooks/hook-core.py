"""PyInstaller hook: bundle the whole Python standard library.

The base app doesn't use all of it, but the optional GPU pack (torch, kokoro,
transformers) is loaded from outside the bundle at runtime and imports
standard-library modules the base app never touches. Costs a few MB.
"""
import sys

from PyInstaller.utils.hooks import collect_submodules

_SKIP = {
    "idlelib", "turtledemo", "test", "lib2to3", "ensurepip", "venv", "pydoc_data", "msilib",
    "curses", "readline", "nis", "grp", "pwd", "termios", "tty", "pty", "fcntl", "posix",
    "resource", "syslog", "crypt", "spwd", "ossaudiodev", "antigravity", "this", "turtle",
    "tkinter.tix", "sqlite3.test",
}


def _wanted(name: str) -> bool:
    parts = name.split(".")
    return not (parts[0] in _SKIP or name in _SKIP or "test" in parts or "tests" in parts
                or parts[0].startswith("_test"))


hiddenimports = []
for top in sorted(sys.stdlib_module_names):
    if not _wanted(top):
        continue
    try:
        hiddenimports += [m for m in collect_submodules(top) if _wanted(m)]
    except Exception:
        hiddenimports.append(top)
