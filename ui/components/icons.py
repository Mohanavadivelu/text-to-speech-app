"""Windows icon-font glyphs with emoji fallbacks.

Segoe Fluent Icons ships with Windows 11 and Segoe MDL2 Assets with Windows 10;
both share these code points. Plain Segoe UI lacks many symbols (e.g. "⏸"),
which is why emoji/text icons sometimes rendered as empty boxes.
"""
import tkinter.font as tkfont

_FAMILIES = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

# name: (icon-font glyph, fallback text)
GLYPHS = {
    "settings": ("", "🎛"),
    "language": ("", "🌐"),
    "voice":    ("", "🎤"),
    "mix":      ("", "🔀"),
    "speed":    ("", "⚡"),
    "pitch":    ("", "🎵"),
    "output":   ("", "💾"),
    "play":     ("", "▶"),
    "pause":    ("", "❚❚"),
}

_family_cache = []


def icon_family():
    """Return the installed icon-font family, or None."""
    if not _family_cache:
        families = set(tkfont.families())
        _family_cache.append(next((f for f in _FAMILIES if f in families), None))
    return _family_cache[0]


def icon(name: str, size: int = 11):
    """Return (text, font) for *name*, using the icon font when available."""
    glyph, fallback = GLYPHS[name]
    family = icon_family()
    if family:
        return glyph, (family, size)
    return fallback, ("Segoe UI Symbol", size)
