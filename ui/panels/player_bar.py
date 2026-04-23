import customtkinter as ctk
from ui.theme import C, FONT_SMALL, FONT_TINY, FONT_MONO, FONT_LABEL, FONT_NORMAL, FONT_SPEED


class PlayerBar(ctk.CTkFrame):
    """Audio player bar: seek slider + volume control in one row."""

    def __init__(self, parent,
                 on_play=None, on_pause=None, on_stop=None,
                 on_save=None, on_seek=None, on_volume=None,
                 **kwargs):
        super().__init__(parent, fg_color=C["surface2"],
                         border_color=C["border"], border_width=1,
                         corner_radius=0, **kwargs)
        self._on_play   = on_play
        self._on_pause  = on_pause
        self._on_stop   = on_stop
        self._on_save   = on_save
        self._on_seek   = on_seek
        self._on_volume = on_volume
        self._playing   = False
        self._muted     = False
        self._duration  = 0.0
        self._seeking   = False
        self._build()
        self.set_no_audio()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # ── Single control row ────────────────────────────────────────────────
        row = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0)
        row.grid(row=0, column=0, sticky="ew", padx=10, pady=6)
        row.grid_columnconfigure(3, weight=1)   # seek slider expands

        btn_kw = dict(width=28, fg_color="transparent",
                      hover_color=C["surface3"],
                      text_color=C["text2"], font=FONT_LABEL)

        # Play/Pause
        self._play_btn = ctk.CTkButton(row, text="▶",
                                       command=self.toggle_play, **btn_kw)
        self._play_btn.grid(row=0, column=0, padx=(0, 2))

        # Stop
        self._stop_btn = ctk.CTkButton(row, text="⏹",
                                       command=self._do_stop, **btn_kw)
        self._stop_btn.grid(row=0, column=1, padx=(0, 6))

        # Current time
        self._cur_time = ctk.CTkLabel(row, text="00:00",
                                      font=FONT_MONO, text_color=C["text2"],
                                      width=42, anchor="e")
        self._cur_time.grid(row=0, column=2, padx=(0, 6))

        # Seek slider (amber/yellow like reference image)
        self._seek_slider = ctk.CTkSlider(
            row, from_=0, to=1,
            fg_color=C["surface3"],
            progress_color="#f59e0b",
            button_color="#ffffff",
            button_hover_color=C["text"],
            command=self._on_seek_change,
        )
        self._seek_slider.set(0)
        self._seek_slider.grid(row=0, column=3, sticky="ew", padx=(0, 6))
        self._seek_slider.bind("<ButtonPress-1>",   lambda _e: self._seek_start())
        self._seek_slider.bind("<ButtonRelease-1>", lambda _e: self._seek_end())

        # Total time
        self._total_time = ctk.CTkLabel(row, text="00:00",
                                        font=FONT_MONO, text_color=C["text3"],
                                        width=42, anchor="w")
        self._total_time.grid(row=0, column=4, padx=(0, 10))

        # Volume icon (mute toggle)
        self._vol_btn = ctk.CTkButton(row, text="🔊",
                                      command=self._toggle_mute,
                                      width=24, fg_color="transparent",
                                      hover_color=C["surface3"],
                                      text_color=C["text2"], font=FONT_NORMAL)
        self._vol_btn.grid(row=0, column=5, padx=(0, 4))

        # Volume slider (short, right side)
        self._vol_slider = ctk.CTkSlider(
            row, from_=0, to=1, width=70,
            fg_color=C["surface3"],
            progress_color=C["btn_save"],
            button_color="#ffffff",
            command=self._on_volume_change,
        )
        self._vol_slider.set(1.0)
        self._vol_slider.grid(row=0, column=6, padx=(0, 10))

        # Save As button
        self._save_btn = ctk.CTkButton(
            row, text="💾  Save As…",
            fg_color=C["surface2"], text_color=C["btn_save"],
            border_color=C["btn_save"], border_width=1,
            hover_color=C["surface3"], corner_radius=50,
            font=FONT_LABEL, command=self._do_save,
        )
        self._save_btn.grid(row=0, column=7, padx=(0, 0))

    # ── public state API ───────────────────────────────────────────────────────

    def set_no_audio(self):
        self._set_controls_enabled(False)
        self._save_btn.configure(state="disabled")
        self._seek_slider.set(0)
        self._cur_time.configure(text="00:00")
        self._total_time.configure(text="00:00")
        self._duration = 0.0

    def set_audio_ready(self, filename: str, duration: float):
        self._duration = duration
        self._seek_slider.set(0)
        self._cur_time.configure(text="00:00")
        self._total_time.configure(text=self._fmt_mm_ss(duration))
        self._set_controls_enabled(True)
        self._save_btn.configure(state="normal")
        self._play_btn.configure(text="▶")
        self._playing = False

    def set_generating(self, generating: bool):
        self._set_controls_enabled(not generating)
        self._save_btn.configure(state="disabled" if generating else "normal")

    def update_progress(self, position_ratio: float, duration: float):
        if self._seeking:
            return
        self._duration = duration
        elapsed = position_ratio * duration
        self._cur_time.configure(text=self._fmt_mm_ss(elapsed))
        self._seek_slider.set(position_ratio)

    def on_playback_done(self):
        self._playing = False
        self._play_btn.configure(text="▶")
        self._seek_slider.set(0)
        self._cur_time.configure(text="00:00")

    def toggle_play(self):
        """Public method — called by Space shortcut and play button."""
        if self._playing:
            self._playing = False
            self._play_btn.configure(text="▶")
            if self._on_pause:
                self._on_pause()
        else:
            self._playing = True
            self._play_btn.configure(text="⏸")
            if self._on_play:
                self._on_play()

    # ── internal helpers ───────────────────────────────────────────────────────

    def _set_controls_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for w in (self._play_btn, self._stop_btn, self._seek_slider):
            w.configure(state=state)

    def _do_stop(self):
        self._playing = False
        self._play_btn.configure(text="▶")
        self._seek_slider.set(0)
        self._cur_time.configure(text="00:00")
        if self._on_stop:
            self._on_stop()

    def _do_save(self):
        if self._on_save:
            self._on_save()

    def _seek_start(self):
        self._seeking = True

    def _seek_end(self):
        self._seeking = False
        ratio = self._seek_slider.get()
        if self._on_seek:
            self._on_seek(ratio)

    def _on_seek_change(self, value: float):
        if self._duration > 0:
            self._cur_time.configure(text=self._fmt_mm_ss(value * self._duration))

    def _toggle_mute(self):
        self._muted = not self._muted
        self._vol_btn.configure(text="🔇" if self._muted else "🔊")
        if self._on_volume:
            self._on_volume(0.0 if self._muted else self._vol_slider.get())

    def _on_volume_change(self, value: float):
        if not self._muted and self._on_volume:
            self._on_volume(float(value))

    @staticmethod
    def _fmt_mm_ss(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
