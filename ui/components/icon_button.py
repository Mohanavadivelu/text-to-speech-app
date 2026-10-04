import math
import customtkinter as ctk
from ui.theme import C, FONT_LABEL
from ui.components.icons import icon


class IconButton(ctk.CTkFrame):
    """Pill-shaped outline button with an icon-font glyph and a text label.

    States: enabled (outline, fills on hover), disabled (greyed, no hover) and a
    short confirmation flash (e.g. "Saved") after an action completes.
    """

    def __init__(self, master, text: str, icon_name: str, command=None,
                 color=None, hover_text="#ffffff", height: int = 32, **kwargs):
        self._color = color or C["btn_save"]
        self._hover_text = hover_text
        self._bg = kwargs.pop("bg_color", C["surface2"])
        super().__init__(master, height=height, corner_radius=height // 2, border_width=1,
                         fg_color=self._bg, border_color=self._color, bg_color=self._bg, **kwargs)
        self._command = command
        self._text = text
        self._enabled = True
        self._hovering = False
        self._flash_after = None

        glyph, font = icon(icon_name, 12)
        self._icon = ctk.CTkLabel(self, text=glyph, font=font, fg_color="transparent",
                                  text_color=self._color, width=16)
        self._label = ctk.CTkLabel(self, text=text, font=FONT_LABEL, fg_color="transparent",
                                   text_color=self._color)
        self._icon.pack(side="left", padx=(16, 6), pady=4)
        self._label.pack(side="left", padx=(0, 18), pady=4)

        for w in (self, self._icon, self._label):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)
        self._apply()

    # ── public API ────────────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        if enabled != self._enabled:
            self._enabled = enabled
            self._apply()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def flash(self, text: str, ms: int = 2000):
        """Show *text* briefly (e.g. "Saved"), then restore the label."""
        if self._flash_after:
            self.after_cancel(self._flash_after)
        else:
            # Hold the current width so a shorter message doesn't shift neighbours
            scale = ctk.ScalingTracker.get_widget_scaling(self)
            self._label.configure(width=math.ceil(self._label.winfo_width() / scale))
        self._label.configure(text=text)
        self._flash_after = self.after(ms, self._end_flash)

    # ── internals ─────────────────────────────────────────────────────────────

    def _end_flash(self):
        self._flash_after = None
        self._label.configure(text=self._text, width=0)

    def _apply(self):
        if not self._enabled:
            fg, border, txt, cursor = self._bg, C["border2"], C["text3"], "arrow"
        elif self._hovering:
            fg, border, txt, cursor = self._color, self._color, self._hover_text, "hand2"
        else:
            fg, border, txt, cursor = self._bg, self._color, self._color, "hand2"
        self.configure(fg_color=fg, border_color=border, cursor=cursor)
        for w in (self._icon, self._label):
            w.configure(text_color=txt, cursor=cursor)

    def _on_enter(self, _e=None):
        self._hovering = True
        self._apply()

    def _on_leave(self, _e=None):
        # Leave fires when moving between child labels; check the real pointer
        x, y = self.winfo_pointerxy()
        inside = self.winfo_containing(x, y)
        if inside is not None and str(inside).startswith(str(self)):
            return
        self._hovering = False
        self._apply()

    def _on_click(self, _e=None):
        if self._enabled and self._command:
            self._command()
