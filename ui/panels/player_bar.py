import tkinter as tk
import customtkinter as ctk
from ui.theme import C, FONT_SMALL, FONT_TINY, FONT_MONO, FONT_LABEL, FONT_NORMAL, FONT_SPEED
from ui.components.player_waveform import PlayerWaveformCanvas


class PlayerBar(ctk.CTkFrame):
    """Audio player bar: waveform + transport controls + volume + save."""

    def __init__(self, parent,
                 on_play=None, on_pause=None, on_stop=None,
                 on_save=None, on_seek=None, on_volume=None,
                 **kwargs):
        super().__init__(parent, fg_color=C["surface2"],
                         border_color=C["border"], border_width=1,
                         corner_radius=0, **kwargs)
        self._on_play  = on_play
        self._on_pause = on_pause
        self._on_stop  = on_stop
        self._on_save  = on_save
        self._on_seek  = on_seek
        self._on_volume = on_volume
        self._playing = False
        self._muted = False
        self._build()
        self.set_no_audio()

    def _build(self):
        self.grid_columnconfigure(0, weight=1)

        # Top label row
        top = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0)
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 0))
        ctk.CTkLabel(top, text="Player", font=FONT_SMALL,
                     text_color=C["text2"]).pack(side="left")

        # Main row: time + filename + format badges
        main = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0)
        main.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 4))

        self._cur_time = ctk.CTkLabel(main, text="00:00", font=FONT_SPEED,
                                      text_color="#ffffff")
        self._cur_time.pack(side="left", padx=(0, 8))

        self._total_time = ctk.CTkLabel(main, text="00:00.0", font=FONT_SMALL,
                                        text_color=C["text3"])
        self._total_time.pack(side="left", padx=(0, 12))

        self._filename_lbl = ctk.CTkLabel(main, text="—", font=FONT_LABEL,
                                          text_color="#ffffff")
        self._filename_lbl.pack(side="left", padx=(0, 8))

        self._fmt_badge = ctk.CTkLabel(main, text="WAV",
                                       fg_color=C["surface3"], text_color=C["text3"],
                                       font=FONT_TINY, corner_radius=4, padx=6, pady=2)
        self._fmt_badge.pack(side="left", padx=(0, 4))

        self._sr_badge = ctk.CTkLabel(main, text="24kHz",
                                      fg_color=C["surface3"], text_color=C["text3"],
                                      font=FONT_TINY, corner_radius=4, padx=6, pady=2)
        self._sr_badge.pack(side="left")

        # Waveform canvas (native tk.Canvas wrapped in a frame)
        wave_wrap = tk.Frame(self, bg=C["border"], bd=0, highlightthickness=0)
        wave_wrap.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))

        self.waveform = PlayerWaveformCanvas(wave_wrap, height=40)
        self.waveform.pack(fill="x")
        self.waveform._seek_callback = self._seek

        # Controls row
        ctrl = ctk.CTkFrame(self, fg_color=C["surface2"], corner_radius=0)
        ctrl.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 8))

        btn_kw = dict(width=28, fg_color="transparent", hover_color=C["surface3"],
                      text_color=C["text2"], font=FONT_LABEL)

        self._play_btn = ctk.CTkButton(ctrl, text="▶", command=self._toggle_play, **btn_kw)
        self._play_btn.pack(side="left")

        self._stop_btn = ctk.CTkButton(ctrl, text="⏹", command=self._do_stop, **btn_kw)
        self._stop_btn.pack(side="left")

        self._time_info = ctk.CTkLabel(ctrl, text="00:00:00 / 00:00:00",
                                       font=FONT_MONO, text_color=C["text3"])
        self._time_info.pack(side="left", padx=(8, 0))

        # Volume (right side)
        self._vol_btn = ctk.CTkButton(ctrl, text="🔊", command=self._toggle_mute,
                                      width=24, fg_color="transparent",
                                      hover_color=C["surface3"],
                                      text_color=C["text2"], font=FONT_NORMAL)
        self._vol_btn.pack(side="right")

        self._vol_slider = ctk.CTkSlider(
            ctrl, from_=0, to=1, width=60,
            fg_color=C["surface3"], progress_color=C["btn_save"],
            button_color="#ffffff", command=self._on_volume_change,
        )
        self._vol_slider.set(1.0)
        self._vol_slider.pack(side="right", padx=(0, 4))

        self._save_btn = ctk.CTkButton(
            ctrl, text="💾  Save As…",
            fg_color=C["surface2"], text_color=C["btn_save"],
            border_color=C["btn_save"], border_width=1,
            hover_color=C["surface3"], corner_radius=50,
            font=FONT_LABEL, command=self._do_save,
        )
        self._save_btn.pack(side="right", padx=(0, 12))

    # ── state helpers ──────────────────────────────────────────────────────────

    def set_no_audio(self):
        self._set_controls_enabled(False)
        self._save_btn.configure(state="disabled")
        self.waveform.clear()

    def set_audio_ready(self, filename: str, duration: float):
        self._filename_lbl.configure(text=filename)
        self._total_time.configure(text=self._fmt_time(duration))
        self._time_info.configure(text=f"00:00:00 / {self._fmt_hms(duration)}")
        self._set_controls_enabled(True)
        self._save_btn.configure(state="normal")
        self._play_btn.configure(text="▶")
        self._playing = False

    def set_generating(self, generating: bool):
        state = "disabled" if generating else "normal"
        self._set_controls_enabled(not generating)
        self._save_btn.configure(state=state)

    def update_progress(self, position_ratio: float, duration: float):
        elapsed = position_ratio * duration
        self._cur_time.configure(text=self._fmt_time(elapsed))
        self._time_info.configure(
            text=f"{self._fmt_hms(elapsed)} / {self._fmt_hms(duration)}")
        self.waveform.set_progress(position_ratio)

    def on_playback_done(self):
        self._playing = False
        self._play_btn.configure(text="▶")

    # ── internal ───────────────────────────────────────────────────────────────

    def _set_controls_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for btn in (self._play_btn, self._stop_btn):
            btn.configure(state=state)

    def _toggle_play(self):
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

    def _do_stop(self):
        self._playing = False
        self._play_btn.configure(text="▶")
        self._cur_time.configure(text="00:00")
        self.waveform.set_progress(0.0)
        if self._on_stop:
            self._on_stop()

    def _do_prev(self):
        self._cur_time.configure(text="00:00")
        self.waveform.set_progress(0.0)
        if self._on_stop:
            self._on_stop()

    def _do_save(self):
        if self._on_save:
            self._on_save()

    def _seek(self, ratio: float):
        if self._on_seek:
            self._on_seek(ratio)

    def _toggle_mute(self):
        self._muted = not self._muted
        self._vol_btn.configure(text="🔇" if self._muted else "🔊")
        if self._on_volume:
            self._on_volume(0.0 if self._muted else self._vol_slider.get())

    def _on_volume_change(self, value):
        if not self._muted and self._on_volume:
            self._on_volume(float(value))

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:04.1f}"

    @staticmethod
    def _fmt_hms(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:05.2f}"
