import customtkinter as ctk
from ui.theme import C, FONT_SMALL, FONT_TINY, FONT_MONO, FONT_LABEL, FONT_NORMAL
from ui.components.player_waveform import PlayerWaveformCanvas


class PlayerBar(ctk.CTkFrame):
    """Compact audio player bar pinned to the bottom of the window."""

    def __init__(self, parent,
                 on_play=None, on_pause=None, on_stop=None,
                 on_save=None, on_seek=None, on_volume=None,
                 on_skip_back=None, on_skip_fwd=None,
                 **kwargs):
        super().__init__(parent, fg_color=C["surface2"],
                         border_color=C["border"], border_width=1,
                         corner_radius=0, **kwargs)
        self._on_play      = on_play
        self._on_pause     = on_pause
        self._on_stop      = on_stop
        self._on_save      = on_save
        self._on_seek      = on_seek
        self._on_volume    = on_volume
        self._on_skip_back = on_skip_back
        self._on_skip_fwd  = on_skip_fwd
        self._playing   = False
        self._muted     = False
        self._duration  = 0.0
        self._seeking   = False
        self._sample_rate = 24000
        self._build()
        self.set_no_audio()

    def _build(self):
        self.pack_propagate(True)

        # ── Row 0: time + filename/bitrate + waveform ─────────────────────────
        wave_row = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0)
        wave_row.pack(fill="x", padx=10, pady=(6, 0))

        # Stacked time (large current / small total)
        time_frame = ctk.CTkFrame(wave_row, fg_color=C["surface2"])
        time_frame.pack(side="left", padx=(0, 8))

        self._cur_time_big = ctk.CTkLabel(
            time_frame, text="00:00",
            font=("Consolas", 20, "bold"), text_color=C["text"], width=70, anchor="w")
        self._cur_time_big.pack(anchor="w")

        self._total_time_small = ctk.CTkLabel(
            time_frame, text="00:00.0",
            font=FONT_MONO, text_color=C["text3"], width=70, anchor="w")
        self._total_time_small.pack(anchor="w")

        # Filename + bitrate (stacked, fixed width)
        info_frame = ctk.CTkFrame(wave_row, fg_color=C["surface2"])
        info_frame.pack(side="left", padx=(0, 8))

        self._filename_label = ctk.CTkLabel(
            info_frame, text="", font=FONT_SMALL, text_color=C["text"],
            width=110, anchor="w")
        self._filename_label.pack(anchor="w")

        self._bitrate_label = ctk.CTkLabel(
            info_frame, text="", font=FONT_TINY, text_color=C["text3"],
            width=110, anchor="w")
        self._bitrate_label.pack(anchor="w")

        # Waveform canvas — fills remaining width
        self._waveform = PlayerWaveformCanvas(wave_row, height=52)
        self._waveform.pack(side="left", fill="x", expand=True)
        self._waveform._seek_callback = self._on_waveform_seek

        # ── Row 1: transport controls ─────────────────────────────────────────
        ctrl_row = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0)
        ctrl_row.pack(fill="x", padx=10, pady=(2, 6))

        btn_kw = dict(width=28, fg_color="transparent",
                      hover_color=C["surface3"],
                      text_color=C["text2"], font=FONT_LABEL)

        # Play/Pause
        self._play_btn = ctk.CTkButton(ctrl_row, text="▶",
                                       command=self.toggle_play, **btn_kw)
        self._play_btn.pack(side="left", padx=(0, 2))

        # Stop
        self._stop_btn = ctk.CTkButton(ctrl_row, text="⏹",
                                       command=self._do_stop, **btn_kw)
        self._stop_btn.pack(side="left", padx=(0, 12))

        # Time label (hh:mm:ss / hh:mm:ss)
        self._time_label = ctk.CTkLabel(ctrl_row, text="00:00:00 / 00:00:00",
                                        font=FONT_MONO, text_color=C["text3"])
        self._time_label.pack(side="left", padx=(0, 10))

        # Format badge (e.g. "WAV 2.0")
        self._fmt_label = ctk.CTkLabel(ctrl_row, text="",
                                       font=FONT_TINY, text_color=C["text3"])
        self._fmt_label.pack(side="left", padx=(0, 10))

        # Right side: volume + save
        self._save_btn = ctk.CTkButton(
            ctrl_row, text="💾  Save As…",
            fg_color=C["surface2"], text_color=C["btn_save"],
            border_color=C["btn_save"], border_width=1,
            hover_color=C["surface3"], corner_radius=50,
            font=FONT_LABEL, command=self._do_save,
        )
        self._save_btn.pack(side="right", padx=(8, 0))

        self._vol_slider = ctk.CTkSlider(
            ctrl_row, from_=0, to=1, width=70,
            fg_color=C["surface3"],
            progress_color=C["btn_save"],
            button_color="#ffffff",
            command=self._on_volume_change,
        )
        self._vol_slider.set(1.0)
        self._vol_slider.pack(side="right", padx=(0, 4))

        self._vol_btn = ctk.CTkButton(ctrl_row, text="🔊",
                                      command=self._toggle_mute,
                                      width=24, fg_color="transparent",
                                      hover_color=C["surface3"],
                                      text_color=C["text2"], font=FONT_NORMAL)
        self._vol_btn.pack(side="right", padx=(0, 4))

    # ── public state API ───────────────────────────────────────────────────────

    def set_no_audio(self):
        self._set_controls_enabled(False)
        self._save_btn.configure(state="disabled")
        self._cur_time_big.configure(text="00:00")
        self._total_time_small.configure(text="00:00.0")
        self._time_label.configure(text="00:00:00 / 00:00:00")
        self._filename_label.configure(text="")
        self._bitrate_label.configure(text="")
        self._fmt_label.configure(text="")
        self._duration = 0.0
        self._waveform.clear()

    def set_audio_ready(self, filename: str, duration: float, sample_rate: int = 24000):
        self._duration = duration
        self._sample_rate = sample_rate
        self._cur_time_big.configure(text="00:00")
        self._total_time_small.configure(text=self._fmt_mm_ss_dec(duration))
        self._time_label.configure(
            text=f"00:00:00 / {self._fmt_hh_mm_ss(duration)}")
        self._filename_label.configure(text=filename)
        # Real bitrate: sample_rate × 32-bit float × 1 channel
        kbps = (sample_rate * 32) // 1000
        self._bitrate_label.configure(text=f"WAV {kbps}kbps {sample_rate // 1000}kHz")
        self._fmt_label.configure(text="WAV")
        self._set_controls_enabled(True)
        self._save_btn.configure(state="normal")
        self._play_btn.configure(text="▶")
        self._playing = False

    def set_audio_data(self, audio, sample_rate: int):
        """Load waveform data into the canvas."""
        self._waveform.set_audio(audio, sample_rate)

    def set_generating(self, generating: bool):
        self._set_controls_enabled(not generating)
        self._save_btn.configure(state="disabled" if generating else "normal")

    def update_progress(self, position_ratio: float, duration: float):
        if self._seeking:
            return
        self._duration = duration
        elapsed = position_ratio * duration
        self._cur_time_big.configure(text=self._fmt_mm_ss(elapsed))
        self._total_time_small.configure(text=self._fmt_mm_ss_dec(duration))
        self._time_label.configure(
            text=f"{self._fmt_hh_mm_ss(elapsed)} / {self._fmt_hh_mm_ss(duration)}")
        self._waveform.set_progress(position_ratio)

    def on_playback_done(self):
        self._playing = False
        self._play_btn.configure(text="▶")
        self._cur_time_big.configure(text="00:00")
        self._time_label.configure(
            text=f"00:00:00 / {self._fmt_hh_mm_ss(self._duration)}")
        self._waveform.set_progress(0.0)

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
        for w in (self._play_btn, self._stop_btn):
            w.configure(state=state)

    def _do_stop(self):
        self._playing = False
        self._play_btn.configure(text="▶")
        self._cur_time_big.configure(text="00:00")
        self._time_label.configure(
            text=f"00:00:00 / {self._fmt_hh_mm_ss(self._duration)}")
        self._waveform.set_progress(0.0)
        if self._on_stop:
            self._on_stop()

    def _do_save(self):
        if self._on_save:
            self._on_save()

    def _on_waveform_seek(self, ratio: float):
        if self._on_seek:
            self._on_seek(ratio)

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

    @staticmethod
    def _fmt_mm_ss_dec(seconds: float) -> str:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:04.1f}"

    @staticmethod
    def _fmt_hh_mm_ss(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
