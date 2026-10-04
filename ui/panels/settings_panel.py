import os
from datetime import datetime
import customtkinter as ctk
from ui.theme import C, FONT_SUBLABEL, FONT_TINY, FONT_SMALL, FONT_NORMAL
from ui.components.icons import icon
from ui.components.play_button import PlayPauseButton
from core.voices import VOICES, DEFAULT_LANGUAGE, default_voice
from core import settings as app_settings
from core import paths

SPEED_DEFAULT, PITCH_DEFAULT, BLEND_DEFAULT = 1.0, 0.0, 0.5
_NO_MIX = "None"

class SettingsPanel(ctk.CTkFrame):
    """Right panel: language, voice, voice mix, speed, pitch, output filename."""

    def __init__(self, parent, on_language_change=None, on_voice_change=None,
                 on_voice_preview=None, on_change=None, on_engine_change=None,
                 on_gpu_install=None, on_gpu_remove=None, on_gpu_retest=None, **kwargs):
        super().__init__(parent, fg_color=C["surface"],
                         border_color=C["border"], border_width=1,
                         corner_radius=12, width=300, **kwargs)
        self.grid_propagate(False)
        self._on_language_change = on_language_change
        self._on_voice_change = on_voice_change
        self._on_voice_preview = on_voice_preview
        self._on_change = on_change
        self._on_engine_change = on_engine_change
        self._on_gpu_install = on_gpu_install
        self._on_gpu_remove = on_gpu_remove
        self._on_gpu_retest = on_gpu_retest
        self._gpu_action = None
        self._voice_map: dict = {}    # label -> voice_id for the current language
        self._build()

    # ── layout helpers ────────────────────────────────────────────────────────

    def _section(self, parent, row, icon_name, title, value_text=None, pady=(0, 4)):
        """Icon + caption row; returns the value label when *value_text* is given."""
        hdr = ctk.CTkFrame(parent, fg_color=C["surface"])
        hdr.grid(row=row, column=0, sticky="ew", pady=pady)
        hdr.grid_columnconfigure(2, weight=1)
        glyph, font = icon(icon_name, 11)
        ctk.CTkLabel(hdr, text=glyph, font=font, text_color=C["text2"],
                     width=16).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr, text=title, font=FONT_TINY,
                     text_color=C["text2"]).grid(row=0, column=1, sticky="w", padx=(6, 0))
        if value_text is None:
            return None
        val = ctk.CTkLabel(hdr, text=value_text, font=FONT_SMALL, text_color=C["accent_h"])
        val.grid(row=0, column=2, sticky="e")
        return val

    def _menu(self, parent, variable, command):
        return ctk.CTkOptionMenu(
            parent, variable=variable, values=[],
            fg_color=C["surface2"], button_color=C["surface3"],
            button_hover_color=C["border2"], text_color=C["text"],
            dropdown_fg_color=C["surface2"], dropdown_hover_color=C["surface3"],
            dropdown_text_color=C["text"], corner_radius=8, height=32,
            font=FONT_NORMAL, dropdown_font=FONT_NORMAL,
            dynamic_resizing=False, command=command,
        )

    def _slider(self, parent, frm, to, steps, variable, command):
        return ctk.CTkSlider(
            parent, from_=frm, to=to, number_of_steps=steps, variable=variable,
            fg_color=C["surface3"], progress_color=C["accent"],
            button_color="#ffffff", button_hover_color=C["text"], command=command,
        )

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color=C["surface"])
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        glyph, font = icon("settings", 13)
        ctk.CTkLabel(hdr, text=glyph, font=font, text_color=C["text2"]).pack(side="left")
        ctk.CTkLabel(hdr, text="VOICE SETTINGS", font=FONT_SUBLABEL,
                     text_color=C["text2"]).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(self, fg_color=C["border"], height=1,
                     corner_radius=0).grid(row=1, column=0, sticky="ew")

        # Scrollable body; the scrollbar hides itself whenever everything fits
        self._body = body = ctk.CTkScrollableFrame(
            self, fg_color=C["surface"], scrollbar_button_color=C["surface3"],
            scrollbar_button_hover_color=C["border2"])
        body.grid(row=2, column=0, sticky="nsew", padx=14, pady=10)
        body.grid_columnconfigure(0, weight=1)
        body.bind("<Configure>", lambda _e: self._refresh_scrollbar(), add="+")
        body._parent_canvas.bind("<Configure>", lambda _e: self._refresh_scrollbar(), add="+")

        r = 0
        # Language
        self._section(body, r, "language", "LANGUAGE"); r += 1
        self.lang_var = ctk.StringVar(value=DEFAULT_LANGUAGE)
        self.lang_menu = self._menu(body, self.lang_var, self._on_lang_selected)
        self.lang_menu.configure(values=list(VOICES.keys()))
        self.lang_menu.grid(row=r, column=0, sticky="ew", pady=(0, 14)); r += 1

        # Voice + preview
        self._section(body, r, "voice", "VOICE"); r += 1
        voice_row = ctk.CTkFrame(body, fg_color=C["surface"])
        voice_row.grid(row=r, column=0, sticky="ew", pady=(0, 14)); r += 1
        voice_row.grid_columnconfigure(0, weight=1)
        self.voice_var = ctk.StringVar()
        self.voice_menu = self._menu(voice_row, self.voice_var, self._on_voice_selected)
        self.voice_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._preview_btn = PlayPauseButton(voice_row, size=32, command=self._do_voice_preview,
                                            bg_color=C["surface"])
        self._preview_btn.grid(row=0, column=1)

        # Voice mix
        self._mix_val = self._section(body, r, "mix", "MIX WITH", value_text=""); r += 1
        self.mix_var = ctk.StringVar(value=_NO_MIX)
        self.mix_menu = self._menu(body, self.mix_var, self._on_mix_selected)
        self.mix_menu.grid(row=r, column=0, sticky="ew", pady=(0, 6)); r += 1
        self.blend_var = ctk.DoubleVar(value=BLEND_DEFAULT)
        self._blend_slider = self._slider(body, 0.1, 0.9, 8, self.blend_var, self._on_blend_change)
        self._blend_row = r
        self._blend_slider.grid(row=r, column=0, sticky="ew", pady=(4, 14)); r += 1
        self._bind_reset(self._blend_slider, self.blend_var, BLEND_DEFAULT, self._on_blend_change)

        # Speed
        self.speed_var = ctk.DoubleVar(value=SPEED_DEFAULT)
        self._speed_val_label = self._section(body, r, "speed", "SPEED", value_text=""); r += 1
        self._speed_slider = self._slider(body, 0.5, 2.0, 15, self.speed_var, self._on_speed_change)
        self._speed_slider.grid(row=r, column=0, sticky="ew", pady=(0, 14)); r += 1
        self._bind_reset(self._speed_slider, self.speed_var, SPEED_DEFAULT, self._on_speed_change)

        # Pitch
        self.pitch_var = ctk.DoubleVar(value=PITCH_DEFAULT)
        self._pitch_val_label = self._section(body, r, "pitch", "PITCH", value_text=""); r += 1
        self._pitch_slider = self._slider(body, -5, 5, 20, self.pitch_var, self._on_pitch_change)
        self._pitch_slider.grid(row=r, column=0, sticky="ew", pady=(0, 4)); r += 1
        self._bind_reset(self._pitch_slider, self.pitch_var, PITCH_DEFAULT, self._on_pitch_change)

        ctk.CTkLabel(body, text="Double-click a slider to reset it", font=FONT_TINY,
                     text_color=C["text3"], anchor="w").grid(row=r, column=0, sticky="w",
                                                              pady=(0, 10)); r += 1

        ctk.CTkFrame(body, fg_color=C["border"], height=1,
                     corner_radius=0).grid(row=r, column=0, sticky="ew", pady=(0, 12)); r += 1

        # Engine: CPU (built in) or GPU pack, plus CPU performance mode
        self._engine_val = self._section(body, r, "engine", "ENGINE", value_text=""); r += 1
        eng_row = ctk.CTkFrame(body, fg_color=C["surface"])
        eng_row.grid(row=r, column=0, sticky="ew", pady=(0, 6)); r += 1
        eng_row.grid_columnconfigure((0, 1), weight=1)
        self.engine_var = ctk.StringVar(value="Auto")
        self.engine_menu = self._menu(eng_row, self.engine_var, self._on_engine_selected)
        self.engine_menu.configure(values=["Auto", "CPU"])
        self.engine_menu.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.perf_var = ctk.StringVar(value="Maximum")
        self.perf_menu = self._menu(eng_row, self.perf_var, self._on_engine_selected)
        self.perf_menu.configure(values=["Maximum", "Balanced", "Quiet"])
        self.perf_menu.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.battery_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(body, text="Quiet mode on battery", variable=self.battery_var,
                        font=FONT_TINY, text_color=C["text2"], checkbox_width=16, checkbox_height=16,
                        border_width=1, fg_color=C["accent"], hover_color=C["accent_h"],
                        command=self._on_engine_selected).grid(row=r, column=0, sticky="w", pady=(0, 8)); r += 1

        self._gpu_card = ctk.CTkFrame(body, fg_color=C["surface2"], corner_radius=8,
                                      border_color=C["border"], border_width=1)
        self._gpu_card.grid(row=r, column=0, sticky="ew", pady=(0, 14)); self._gpu_row = r; r += 1
        self._gpu_card.grid_columnconfigure(0, weight=1)
        self._gpu_title = ctk.CTkLabel(self._gpu_card, text="GPU pack", font=FONT_NORMAL,
                                       text_color=C["text"], anchor="w")
        self._gpu_title.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))
        self._gpu_text = ctk.CTkLabel(self._gpu_card, text="", font=FONT_TINY, text_color=C["text3"],
                                      anchor="w", justify="left", wraplength=230)
        self._gpu_text.grid(row=1, column=0, sticky="w", padx=10)
        self._gpu_btn = ctk.CTkButton(self._gpu_card, text="", font=FONT_SMALL, height=28,
                                      fg_color=C["surface3"], hover_color=C["border2"], text_color=C["text"],
                                      corner_radius=6, command=self._on_gpu_button)
        self._gpu_btn.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 10))
        self._gpu_card.grid_remove()

        # Output: fixed folder, files named by date and time
        self._section(body, r, "output", "OUTPUT"); r += 1
        card = ctk.CTkFrame(body, fg_color=C["surface2"], corner_radius=8,
                            border_color=C["border"], border_width=1)
        card.grid(row=r, column=0, sticky="ew", pady=(0, 4)); r += 1
        card.grid_columnconfigure(0, weight=1)
        folder = os.path.basename(paths.AUDIO_DIR) + os.sep
        ctk.CTkLabel(card, text=folder, font=FONT_NORMAL, text_color=C["text"],
                     anchor="w").grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))
        example = datetime.now().strftime(paths.OUTPUT_NAME_FORMAT)
        ctk.CTkLabel(card, text=f"Named by date and time, e.g. {example}.wav",
                     font=FONT_TINY, text_color=C["text3"], anchor="w",
                     ).grid(row=1, column=0, sticky="w", padx=10)
        self._last_file = ctk.CTkLabel(card, text="", font=FONT_TINY,
                                       text_color=C["accent_h"], anchor="w")
        self._last_file.grid(row=2, column=0, sticky="w", padx=10)
        self._last_file.grid_remove()
        ctk.CTkButton(card, text="Open folder", font=FONT_SMALL, height=28,
                      fg_color=C["surface3"], hover_color=C["border2"], text_color=C["text"],
                      corner_radius=6, command=lambda: paths.open_folder(paths.AUDIO_DIR),
                      ).grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 10))

        # Reset (pinned to the bottom of the panel)
        self._reset_btn = ctk.CTkButton(
            self, text="Reset to defaults", font=FONT_SMALL,
            fg_color="transparent", hover_color=C["surface3"], text_color=C["text2"],
            border_color=C["border2"], border_width=1, corner_radius=8, height=30,
            command=self.reset_to_defaults,
        )
        self._reset_btn.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))

        self._on_speed_change(SPEED_DEFAULT, notify=False)
        self._on_pitch_change(PITCH_DEFAULT, notify=False)
        self._on_blend_change(BLEND_DEFAULT, notify=False)

    # ── behaviour helpers ─────────────────────────────────────────────────────

    def _bind_reset(self, slider, var, default, handler):
        def _reset(_e=None):
            # Run after the slider's own click handling, which moves the knob.
            self.after_idle(lambda: (var.set(default), handler(default)))
        slider.bind("<Double-Button-1>", _reset, add="+")

    def _refresh_scrollbar(self):
        canvas, bar = self._body._parent_canvas, self._body._scrollbar
        try:
            fits = canvas.yview() == (0.0, 1.0)
        except Exception:
            return
        if fits and bar.winfo_ismapped():
            bar.grid_remove()
        elif not fits and not bar.winfo_ismapped():
            bar.grid()

    def _notify(self):
        if self._on_change:
            self._on_change()

    def _rebuild_mix_menu(self):
        """Mix candidates are the language's voices except the selected one."""
        current = self.get_voice_id()
        labels = [lbl for lbl, vid in self._voice_map.items() if vid != current]
        self.mix_menu.configure(values=[_NO_MIX] + labels)
        if self.mix_var.get() not in labels:
            self.mix_var.set(_NO_MIX)
        self._update_mix_visibility()

    def _update_mix_visibility(self):
        mixing = self.mix_var.get() != _NO_MIX
        if mixing:
            self._blend_slider.grid()
        else:
            self._blend_slider.grid_remove()
        self._on_blend_change(self.blend_var.get(), notify=False)
        self.after_idle(self._refresh_scrollbar)

    # ── callbacks ─────────────────────────────────────────────────────────────

    def _on_lang_selected(self, value):
        self.update_voice_list(value, VOICES.get(value, []))
        if self._on_language_change:
            self._on_language_change(value)
        self._notify()

    def _on_voice_selected(self, value):
        self._rebuild_mix_menu()
        if self._on_voice_change:
            self._on_voice_change(value)
        self._notify()

    def _on_mix_selected(self, _value):
        self._update_mix_visibility()
        self._notify()

    def _do_voice_preview(self):
        if self._on_voice_preview:
            self._on_voice_preview()

    def _on_speed_change(self, value, notify=True):
        self._speed_val_label.configure(text=f"{float(value):.1f}×")
        if notify:
            self._notify()

    def _on_pitch_change(self, value, notify=True):
        v = round(float(value) * 2) / 2
        self._pitch_val_label.configure(text="0 st" if v == 0 else f"{v:+.1f} st")
        if notify:
            self._notify()

    def _on_blend_change(self, value, notify=True):
        if self.mix_var.get() == _NO_MIX:
            self._mix_val.configure(text="")
        else:
            other = self.mix_var.get().split(" · ")[0]
            self._mix_val.configure(text=f"{round(float(value) * 100)}% {other}")
        if notify:
            self._notify()

    def _on_engine_selected(self, _value=None):
        if self._on_engine_change:
            self._on_engine_change()
        self._notify()

    def _on_gpu_button(self):
        callback = {"install": self._on_gpu_install, "remove": self._on_gpu_remove,
                    "retest": self._on_gpu_retest}.get(self._gpu_action)
        if callback:
            callback()

    # ── public API ────────────────────────────────────────────────────────────

    def get_engine_settings(self) -> dict:
        return {"engine": self.engine_var.get(), "perf_mode": self.perf_var.get(),
                "quiet_on_battery": bool(self.battery_var.get())}

    def set_engine_status(self, label: str):
        self._engine_val.configure(text=label)

    def set_gpu_card(self, visible: bool, title: str = "", text: str = "", action: str = None,
                     button: str = "", installed: bool = False):
        """Show the GPU pack card. action: install / remove / retest / None."""
        self.engine_menu.configure(values=["Auto", "GPU", "CPU"] if installed else ["Auto", "CPU"])
        if not installed and self.engine_var.get() == "GPU":
            self.engine_var.set("Auto")
        if not visible:
            self._gpu_card.grid_remove()
            return
        self._gpu_title.configure(text=title)
        self._gpu_text.configure(text=text)
        self._gpu_action = action
        if action:
            self._gpu_btn.configure(text=button, state="normal")
            self._gpu_btn.grid()
        else:
            self._gpu_btn.grid_remove()
        self._gpu_card.grid()
        self.after_idle(self._refresh_scrollbar)

    def update_voice_list(self, lang_key: str, voices: list, selected: str = None):
        """Fill the voice menu for *lang_key*; select *selected* (a voice id) if present."""
        self.lang_var.set(lang_key)
        self._voice_map = {label: vid for vid, label in voices}
        labels = list(self._voice_map)
        self.voice_menu.configure(values=labels)
        by_id = {vid: label for label, vid in self._voice_map.items()}
        self.voice_var.set(by_id.get(selected) or (labels[0] if labels else ""))
        self._rebuild_mix_menu()

    def set_preview_state(self, state: str):
        """'idle' | 'busy' (generating) | 'playing' (click stops)."""
        self._preview_btn.set_busy(state == "busy")
        self._preview_btn.set_playing(state == "playing")

    def update_output_info(self, filename: str, meta: str = ""):
        """Show the most recently generated file in the output card."""
        self._last_file.configure(text=f"Last: {filename}" + (f"  ·  {meta}" if meta else ""))
        self._last_file.grid()

    def get_language_key(self) -> str:
        return self.lang_var.get()

    def get_voice_label(self) -> str:
        return self.voice_var.get()

    def get_voice_id(self) -> str:
        return self._voice_map.get(self.voice_var.get(), default_voice(self.get_language_key()))

    def get_blend(self):
        """Return (blend_voice_id or None, ratio)."""
        label = self.mix_var.get()
        if label == _NO_MIX:
            return None, 0.0
        return self._voice_map.get(label), round(self.blend_var.get(), 2)

    def get_speed(self) -> float:
        return round(self.speed_var.get(), 1)

    def get_pitch(self) -> float:
        return round(self.pitch_var.get() * 2) / 2

    def get_state(self) -> dict:
        blend_voice, ratio = self.get_blend()
        return {
            "language": self.get_language_key(),
            "voice": self.get_voice_id(),
            "blend_voice": blend_voice,
            "blend_ratio": ratio if blend_voice else round(self.blend_var.get(), 2),
            "speed": self.get_speed(),
            "pitch": self.get_pitch(),
            **self.get_engine_settings(),
        }

    def apply_state(self, state: dict):
        """Restore a saved state; unknown languages or voices fall back to defaults."""
        lang = state.get("language")
        if lang not in VOICES:
            lang = DEFAULT_LANGUAGE
        self.update_voice_list(lang, VOICES[lang], selected=state.get("voice"))
        by_id = {vid: label for label, vid in self._voice_map.items()}
        blend_label = by_id.get(state.get("blend_voice"))
        self.mix_var.set(blend_label if blend_label and blend_label != self.voice_var.get()
                         else _NO_MIX)

        def _num(key, default, lo, hi):
            try:
                return min(hi, max(lo, float(state.get(key, default))))
            except (TypeError, ValueError):
                return default

        self.blend_var.set(_num("blend_ratio", BLEND_DEFAULT, 0.1, 0.9))
        self.speed_var.set(_num("speed", SPEED_DEFAULT, 0.5, 2.0))
        self.pitch_var.set(_num("pitch", PITCH_DEFAULT, -5.0, 5.0))
        self._on_speed_change(self.speed_var.get(), notify=False)
        self._on_pitch_change(self.pitch_var.get(), notify=False)
        self._update_mix_visibility()
        if state.get("engine") in ("Auto", "GPU", "CPU"):
            self.engine_var.set(state["engine"])
        if state.get("perf_mode") in ("Maximum", "Balanced", "Quiet"):
            self.perf_var.set(state["perf_mode"])
        self.battery_var.set(bool(state.get("quiet_on_battery", True)))

    def reset_to_defaults(self):
        self.apply_state(app_settings.DEFAULTS)
        if self._on_engine_change:
            self._on_engine_change()
        if self._on_language_change:
            self._on_language_change(self.get_language_key())
        self._notify()
