import tkinter.font as tkfont
import customtkinter as ctk
from ui.theme import C

# Icon glyphs, best available first. Segoe Fluent Icons ships with Windows 11,
# Segoe MDL2 Assets with Windows 10. Plain Segoe UI cannot render "⏸", which
# is why the old pause button showed an empty box.
_ICON_SETS = (
    ("Segoe Fluent Icons", "", ""),   # PlaySolid / PauseSolid
    ("Segoe MDL2 Assets",  "", ""),   # PlaySolid / Pause
    ("Segoe UI Symbol",    "▶", "❚❚"),
)

_BUSY_FRAMES = ("•", "• •", "• • •")


def _pick_icons():
    families = set(tkfont.families())
    for family, play, pause in _ICON_SETS:
        if family in families:
            return family, play, pause
    return _ICON_SETS[-1]


class PlayPauseButton(ctk.CTkFrame):
    """Circular filled play/pause toggle with an optional busy animation.

    Built from a round frame plus a centered label because CTkButton pads each
    side by its corner radius, so a fully rounded CTkButton is never circular.
    """

    def __init__(self, master, size: int = 40, command=None,
                 fill=None, hover=None, icon_color="#ffffff", **kwargs):
        self._fill = fill or C["btn_save"]
        self._hover = hover or C["btn_save_h"]
        self._fill_disabled = C["surface3"]
        self._icon_color = icon_color
        self._icon_disabled = C["text3"]
        self._command = command
        self._enabled = True
        self._playing = False
        self._busy_after = None

        super().__init__(master, width=size, height=size, corner_radius=size // 2,
                         fg_color=self._fill, **kwargs)
        self.pack_propagate(False)
        self.grid_propagate(False)

        family, self._play_glyph, self._pause_glyph = _pick_icons()
        self._icon_font = (family, max(9, int(size * 0.38)))
        self._busy_font = ("Segoe UI", max(7, int(size * 0.22)), "bold")
        self._label = ctk.CTkLabel(self, text=self._play_glyph, fg_color="transparent",
                                   text_color=self._icon_color, font=self._icon_font)
        self._label.place(relx=0.5, rely=0.5, anchor="center")

        for w in (self, self._label):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
        self.configure(cursor="hand2")
        self._label.configure(cursor="hand2")

    # ── public API ────────────────────────────────────────────────────────────

    def set_playing(self, playing: bool):
        """Show the pause icon while playing, the play icon otherwise."""
        self._playing = playing
        if self._busy_after is None:
            self._label.configure(text=self._pause_glyph if playing else self._play_glyph)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        cursor = "hand2" if enabled else "arrow"
        self.configure(fg_color=self._fill if enabled else self._fill_disabled, cursor=cursor)
        self._label.configure(text_color=self._icon_color if enabled else self._icon_disabled,
                              cursor=cursor)

    def set_busy(self, busy: bool):
        """Animate dots and ignore clicks while work is in progress."""
        if busy and self._busy_after is None:
            self.set_enabled(False)
            self._label.configure(font=self._busy_font)
            self._animate(0)
        elif not busy and self._busy_after is not None:
            self.after_cancel(self._busy_after)
            self._busy_after = None
            self._label.configure(font=self._icon_font)
            self.set_enabled(True)
            self.set_playing(self._playing)

    # ── events ────────────────────────────────────────────────────────────────

    def _animate(self, i: int):
        self._label.configure(text=_BUSY_FRAMES[i % len(_BUSY_FRAMES)])
        self._busy_after = self.after(350, lambda: self._animate(i + 1))

    def _on_click(self, _event=None):
        if self._enabled and self._command:
            self._command()

    def _on_enter(self, _event=None):
        if self._enabled:
            self.configure(fg_color=self._hover)

    def _on_leave(self, _event=None):
        if self._enabled:
            self.configure(fg_color=self._fill)
