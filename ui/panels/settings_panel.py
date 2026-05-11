import customtkinter as ctk
from ui.theme import C, FONT_SUBLABEL, FONT_TINY, FONT_SMALL, FONT_LABEL
from core.voices import VOICES, LANG_FLAGS


class SettingsPanel(ctk.CTkFrame):
    """Right panel: voice settings, speed, pitch, output filename."""

    def __init__(self, parent, on_language_change=None, on_voice_change=None,
                 on_voice_preview=None, **kwargs):
        super().__init__(parent, fg_color=C["surface"],
                         border_color=C["border"], border_width=1,
                         corner_radius=12, width=300, **kwargs)
        self.grid_propagate(False)
        self._on_language_change = on_language_change
        self._on_voice_change = on_voice_change
        self._on_voice_preview = on_voice_preview
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header row ────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="🎛️  VOICE SETTINGS", font=FONT_SUBLABEL,
                     text_color=C["text2"], fg_color=C["surface"],
                     anchor="w").grid(row=0, column=0, sticky="ew",
                                      padx=14, pady=(12, 8))

        ctk.CTkFrame(self, fg_color=C["border"], height=1,
                     corner_radius=0).grid(row=1, column=0, sticky="ew")

        # ── Scrollable body ───────────────────────────────────────────────────
        body = ctk.CTkScrollableFrame(self, fg_color=C["surface"],
                                      scrollbar_button_color=C["surface3"],
                                      scrollbar_button_hover_color=C["border2"])
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=10)
        body.grid_columnconfigure(0, weight=1)

        r = 0

        # ── Language ──────────────────────────────────────────────────────────
        ctk.CTkLabel(body, text="🌐  LANGUAGE", font=FONT_TINY,
                     text_color=C["text2"]).grid(row=r, column=0, sticky="w", pady=(0, 4))
        r += 1

        self.lang_var = ctk.StringVar(value="American English")
        lang_opts = [f"{LANG_FLAGS.get(k, '')} {k}" for k in VOICES.keys()]

        self.lang_cb = ctk.CTkComboBox(
            body, variable=self.lang_var, values=lang_opts,
            fg_color=C["surface2"], border_color=C["border"],
            button_color=C["surface3"], button_hover_color=C["border2"],
            dropdown_fg_color=C["surface2"], dropdown_hover_color=C["surface3"],
            text_color=C["text"], corner_radius=8, width=240,
            command=self._on_lang_selected,
        )
        self.lang_cb.grid(row=r, column=0, sticky="ew", pady=(0, 14))
        r += 1

        # ── Voice ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(body, text="🎤  VOICE", font=FONT_TINY,
                     text_color=C["text2"]).grid(row=r, column=0, sticky="w", pady=(0, 4))
        r += 1

        voice_row = ctk.CTkFrame(body, fg_color=C["surface"])
        voice_row.grid(row=r, column=0, sticky="ew", pady=(0, 14))
        voice_row.grid_columnconfigure(0, weight=1)

        self.voice_var = ctk.StringVar()
        self.voice_cb = ctk.CTkComboBox(
            voice_row, variable=self.voice_var, values=[],
            fg_color=C["surface2"], border_color=C["border"],
            button_color=C["surface3"], button_hover_color=C["border2"],
            dropdown_fg_color=C["surface2"], dropdown_hover_color=C["surface3"],
            text_color=C["text"], corner_radius=8, width=200,
            command=self._on_voice_selected,
        )
        self.voice_cb.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._preview_btn = ctk.CTkButton(
            voice_row, text="▶", width=28,
            fg_color=C["surface3"], hover_color=C["border2"],
            text_color=C["text2"], corner_radius=6,
            command=self._do_voice_preview,
        )
        self._preview_btn.grid(row=0, column=1)
        r += 1

        # ── Speed ─────────────────────────────────────────────────────────────
        self.speed_var = ctk.DoubleVar(value=1.0)

        speed_hdr = ctk.CTkFrame(body, fg_color=C["surface"])
        speed_hdr.grid(row=r, column=0, sticky="ew", pady=(0, 4))
        speed_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(speed_hdr, text="⚡  SPEED", font=FONT_TINY,
                     text_color=C["text2"], anchor="w").grid(row=0, column=0, sticky="w")
        self._speed_val_label = ctk.CTkLabel(speed_hdr, text="1.0",
                                             font=FONT_SMALL, text_color=C["accent_h"])
        self._speed_val_label.grid(row=0, column=1, sticky="e")
        r += 1

        self._speed_slider = ctk.CTkSlider(
            body, from_=0.5, to=2.0, variable=self.speed_var,
            fg_color=C["surface3"], progress_color=C["accent"],
            button_color="#ffffff", button_hover_color=C["text"],
            command=self._on_speed_change,
        )
        self._speed_slider.grid(row=r, column=0, sticky="ew", pady=(0, 14))
        r += 1

        # ── Pitch ─────────────────────────────────────────────────────────────
        self.pitch_var = ctk.DoubleVar(value=0.0)

        pitch_hdr = ctk.CTkFrame(body, fg_color=C["surface"])
        pitch_hdr.grid(row=r, column=0, sticky="ew", pady=(0, 4))
        pitch_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(pitch_hdr, text="🎵  PITCH", font=FONT_TINY,
                     text_color=C["text2"], anchor="w").grid(row=0, column=0, sticky="w")
        self._pitch_val_label = ctk.CTkLabel(pitch_hdr, text="0.0",
                                             font=FONT_SMALL, text_color=C["accent_h"])
        self._pitch_val_label.grid(row=0, column=1, sticky="e")
        r += 1

        ctk.CTkSlider(
            body, from_=-5, to=5, variable=self.pitch_var,
            fg_color=C["surface3"], progress_color=C["accent"],
            button_color="#ffffff", button_hover_color=C["text"],
            command=self._on_pitch_change,
        ).grid(row=r, column=0, sticky="ew", pady=(0, 14))
        r += 1

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(body, fg_color=C["border"], height=1,
                     corner_radius=0).grid(row=r, column=0, sticky="ew", pady=(0, 12))
        r += 1

        # ── Output filename ───────────────────────────────────────────────────
        ctk.CTkLabel(body, text="💾  OUTPUT FILE", font=FONT_TINY,
                     text_color=C["text2"]).grid(row=r, column=0, sticky="w", pady=(0, 4))
        r += 1

        self._output_entry = ctk.CTkEntry(
            body, placeholder_text="audio_output",
            fg_color=C["surface2"], border_color=C["border"],
            text_color=C["text"], corner_radius=8,
        )
        self._output_entry.insert(0, "audio_output")
        self._output_entry.grid(row=r, column=0, sticky="ew", pady=(0, 4))
        r += 1

        ctk.CTkLabel(body, text=".wav will be appended automatically",
                     font=FONT_TINY, text_color=C["text3"],
                     anchor="w").grid(row=r, column=0, sticky="w")
        r += 1

    # ── callbacks ──────────────────────────────────────────────────────────────

    def _on_lang_selected(self, value):
        key = value.split(" ", 1)[-1] if " " in value else value
        if self._on_language_change:
            self._on_language_change(key)

    def _on_voice_selected(self, value):
        if self._on_voice_change:
            self._on_voice_change(value)

    def _do_voice_preview(self):
        if self._on_voice_preview:
            self._on_voice_preview()

    def _on_speed_change(self, value):
        self._speed_val_label.configure(text=f"{value:.1f}")

    def _on_pitch_change(self, value):
        sign = "+" if value > 0 else ""
        self._pitch_val_label.configure(text=f"{sign}{value:.1f}")

    # ── public API ─────────────────────────────────────────────────────────────

    def update_voice_list(self, lang_key: str, voices: list):
        labels = [label for _, label in voices]
        self.voice_cb.configure(values=labels)
        if labels:
            self.voice_cb.set(labels[0])

    def update_output_info(self, filename: str, meta: str):
        """No-op — Last Output card removed; kept for API compatibility."""
        pass

    def get_language_key(self) -> str:
        val = self.lang_var.get()
        return val.split(" ", 1)[-1] if " " in val else val

    def get_voice_label(self) -> str:
        return self.voice_var.get()

    def get_speed(self) -> float:
        return round(self.speed_var.get(), 1)

    def get_pitch(self) -> float:
        return round(self.pitch_var.get(), 1)

    def get_output_filename(self) -> str:
        """Return the user-specified output filename (without extension)."""
        name = self._output_entry.get().strip()
        return name if name else "audio_output"
