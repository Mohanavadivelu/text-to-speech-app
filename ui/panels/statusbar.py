import customtkinter as ctk
from ui.theme import C, FONT_TINY, FONT_SMALL


class StatusBar(ctk.CTkFrame):
    """28 px status bar at the bottom of the window."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C["titlebar"], height=28,
                         border_color=C["border"], border_width=1,
                         corner_radius=0, **kwargs)
        self.pack_propagate(False)
        self._pulse_after = None
        self._build()

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color=C["titlebar"])
        inner.pack(fill="x", padx=14, pady=0)

        self._dot = ctk.CTkLabel(inner, text="●", font=FONT_TINY,
                                 text_color=C["status_ok"])
        self._dot.pack(side="left", padx=(0, 4))

        self._msg = ctk.CTkLabel(inner, text="Ready", font=FONT_SMALL,
                                 text_color=C["text2"])
        self._msg.pack(side="left")

        # Right side
        right = ctk.CTkFrame(inner, fg_color=C["titlebar"])
        right.pack(side="right")

        ctk.CTkLabel(right, text="Kokoro TTS Studio", font=FONT_TINY,
                     text_color=C["text3"]).pack(side="right", padx=(10, 0))

        ctk.CTkFrame(right, fg_color=C["border"], width=1, height=14,
                     corner_radius=0).pack(side="right", padx=10)

        ctk.CTkButton(right, text="📂  History",
                      fg_color="transparent", border_color=C["border2"],
                      border_width=1, text_color=C["text3"],
                      font=FONT_TINY, corner_radius=4,
                      height=18, command=lambda: None).pack(side="right", padx=(0, 6))

        ctk.CTkFrame(right, fg_color=C["border"], width=1, height=14,
                     corner_radius=0).pack(side="right", padx=10)

        self._voice_lbl = ctk.CTkLabel(right, text="🎙 af_heart",
                                       font=FONT_TINY, text_color=C["text3"])
        self._voice_lbl.pack(side="right")

    def set_status(self, message: str, state: str = "ok"):
        colours = {"ok": C["status_ok"], "busy": C["status_busy"], "error": C["status_err"]}
        colour = colours.get(state, C["status_ok"])
        self._dot.configure(text_color=colour)
        self._msg.configure(text=message, text_color=C["text2"] if state == "ok" else colour)

        if self._pulse_after:
            self.after_cancel(self._pulse_after)
            self._pulse_after = None

        if state == "busy":
            self._pulse(colour, True)

    def set_voice(self, voice_id: str):
        self._voice_lbl.configure(text=f"🎙 {voice_id}")

    def _pulse(self, colour: str, show: bool):
        try:
            self._dot.configure(text_color=colour if show else C["titlebar"])
            self._pulse_after = self.after(500, lambda: self._pulse(colour, not show))
        except Exception:
            # Widget destroyed (window closed) — stop pulsing silently
            self._pulse_after = None
