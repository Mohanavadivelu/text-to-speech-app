import os
import logging
import threading

import customtkinter as ctk
from tkinter import filedialog

from ui.theme import C, WIN_W, WIN_H, WIN_MIN_W, WIN_MIN_H
from ui.panels.titlebar import TitleBar
from ui.panels.text_panel import TextPanel
from ui.panels.settings_panel import SettingsPanel
from ui.panels.player_bar import PlayerBar
from ui.panels.statusbar import StatusBar
from ui.components.toast import Toast

from core.engine import TTSEngine, SAMPLE_RATE, log_device_info
from core.player import AudioPlayer
from core.voices import VOICES, LANG_CODES

log = logging.getLogger(__name__)

# Output file is always written next to app.py (project root)
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_DEFAULT_OUTPUT = os.path.join(_ROOT, "output.wav")


class KokoroApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Kokoro TTS")
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.minsize(WIN_MIN_W, WIN_MIN_H)
        self.configure(fg_color=C["bg"])
        self.state("zoomed")

        self._engine = TTSEngine()
        self._player = AudioPlayer()
        self._player.on_progress = self._on_player_progress
        self._player.on_done = self._on_player_done

        self._audio_data = None
        self._audio_path = None
        self._generating = False

        self._build_ui()
        self._update_voice_list("American English")
        self._bind_shortcuts()
        # Show device info toast after window is fully drawn
        self.after(500, self._show_device_toast)

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._titlebar = TitleBar(self)
        self._titlebar.pack(fill="x")

        self._statusbar = StatusBar(self)
        self._statusbar.pack(side="bottom", fill="x")

        self._player_bar = PlayerBar(
            self,
            on_play=self._on_play,
            on_pause=self._on_pause,
            on_stop=self._on_stop,
            on_save=self._on_save,
            on_seek=self._on_seek,
            on_volume=self._on_volume,
        )
        self._player_bar.pack(side="bottom", fill="x")

        body = ctk.CTkFrame(self, fg_color=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(10, 6))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=300)
        body.grid_rowconfigure(0, weight=1)

        self._text_panel = TextPanel(body, on_generate=self._on_generate)
        self._text_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._settings_panel = SettingsPanel(
            body,
            on_language_change=self._update_voice_list,
            on_voice_change=self._on_voice_change,
        )
        self._settings_panel.grid(row=0, column=1, sticky="nsew")
        self._settings_panel.configure(width=300)

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda _e: self._on_stop())
        self.bind("<Control-s>", lambda _e: self._on_save())
        self.bind("<space>", self._on_space)

    def _show_device_toast(self):
        from core.engine import DEVICE, TTSEngine
        info = TTSEngine.device_info()
        kind = "info" if DEVICE == "cuda" else "error"
        Toast(self, info, kind=kind)

    # ── Voice helpers ──────────────────────────────────────────────────────────

    def _update_voice_list(self, lang_key: str):
        voices = VOICES.get(lang_key, [])
        self._settings_panel.update_voice_list(lang_key, voices)
        self._statusbar.set_voice(self._get_voice_id())

    def _on_voice_change(self, _label: str):
        self._statusbar.set_voice(self._get_voice_id())

    def _get_voice_id(self) -> str:
        lang_key = self._settings_panel.get_language_key()
        label = self._settings_panel.get_voice_label()
        for vid, lbl in VOICES.get(lang_key, []):
            if lbl == label:
                return vid
        voices = VOICES.get(lang_key, [])
        return voices[0][0] if voices else "af_heart"

    # ── Generate ───────────────────────────────────────────────────────────────

    def _on_generate(self):
        text = self._text_panel.get_text()
        if not text:
            Toast(self, "Please enter some text first.", kind="error")
            return
        if self._generating:
            return

        self._generating = True
        self._text_panel.set_generating(True)
        self._player_bar.set_generating(True)
        self._statusbar.set_status("Generating audio…", "busy")

        lang_key  = self._settings_panel.get_language_key()
        lang_code = LANG_CODES.get(lang_key, "a")
        voice_id  = self._get_voice_id()
        speed     = self._settings_panel.get_speed()
        pitch     = self._settings_panel.get_pitch()

        threading.Thread(
            target=self._generate_worker,
            args=(text, lang_code, voice_id, speed, pitch),
            daemon=True,
        ).start()

    def _generate_worker(self, text, lang_code, voice_id, speed, pitch):
        try:
            first_chunk_played = threading.Event()

            def on_status(msg):
                self.after(0, lambda: self._statusbar.set_status(msg, "busy"))

            def on_progress(pct: int):
                self.after(0, lambda p=pct: self._text_panel.set_generating(True, p))

            def on_chunk(chunk_audio):
                """Stream first chunk to player immediately so playback starts early."""
                if not first_chunk_played.is_set():
                    first_chunk_played.set()
                    # Load just this chunk so the player can start right away
                    self.after(0, lambda a=chunk_audio: self._on_first_chunk(a))

            audio, sr = self._engine.generate(
                text, lang_code, voice_id, speed,
                pitch=pitch, on_status=on_status, on_progress=on_progress,
                on_chunk=on_chunk,
            )
            self._engine.save(audio, sr, _DEFAULT_OUTPUT)
            self.after(0, lambda: self._on_generate_done(audio, sr, _DEFAULT_OUTPUT, voice_id))
        except Exception as exc:
            log.exception("Generation failed: %s", exc)
            self.after(0, lambda msg=str(exc): self._on_generate_error(msg))

    def _on_first_chunk(self, chunk_audio):
        """Load the first audio chunk into the player so playback can start immediately."""
        import numpy as np
        chunk_audio = np.asarray(chunk_audio, dtype=np.float32)
        self._player.load(chunk_audio, SAMPLE_RATE)
        duration = len(chunk_audio) / SAMPLE_RATE
        self._player_bar.set_audio_ready("generating…", duration)
        self._statusbar.set_status("First segment ready — click ▶ to preview", "ok")

    def _on_generate_done(self, audio, sr, path, voice_id):
        self._generating = False
        self._audio_data = audio
        self._audio_path = path

        self._player.load(audio, sr)

        duration = len(audio) / sr
        filename = os.path.basename(path)
        mins = int(duration // 60)
        secs = duration % 60
        meta = f"24 kHz · WAV · {mins}:{secs:04.1f}s"

        self._text_panel.set_generating(False)
        self._player_bar.set_generating(False)
        self._player_bar.set_audio_ready(filename, duration)

        self._settings_panel.update_output_info(filename, meta)
        self._statusbar.set_voice(voice_id)
        self._statusbar.set_status(f"Done — saved to {filename}", "ok")

        Toast(self, f"Saved to {filename}", kind="info")

    def _on_generate_error(self, msg: str):
        self._generating = False
        self._text_panel.set_generating(False)
        self._player_bar.set_generating(False)
        self._statusbar.set_status(f"Error: {msg}", "error")
        Toast(self, f"Error: {msg}", kind="error")

    # ── Playback ───────────────────────────────────────────────────────────────

    def _on_play(self):
        # Allow playback if full audio is ready OR if a streaming chunk is loaded
        if self._audio_data is None and self._player._audio is None:
            return
        self._player.play()
        self._statusbar.set_status("Playing…", "busy")

    def _on_pause(self):
        self._player.pause()
        self._statusbar.set_status("Paused", "ok")

    def _on_stop(self):
        self._player.stop()
        self._player_bar.on_playback_done()
        self._statusbar.set_status("Ready", "ok")

    def _on_seek(self, ratio: float):
        # Restart playback from the seeked position
        if self._audio_data is None:
            return
        was_playing = self._player.is_playing
        self._player.stop()
        total = len(self._audio_data)
        self._player._start_sample = int(ratio * total)
        self._player._position = ratio
        if was_playing:
            self._player.play()

    def _on_volume(self, value: float):
        self._player.set_volume(value)

    def _on_space(self, event):
        focused = self.focus_get()
        if focused is self._text_panel.text_input:
            return
        self._player_bar.toggle_play()

    def _on_player_progress(self, ratio: float):
        duration = self._player.duration
        self.after(0, lambda: self._player_bar.update_progress(ratio, duration))

    def _on_player_done(self):
        self.after(0, self._player_bar.on_playback_done)
        self.after(0, lambda: self._statusbar.set_status("Ready", "ok"))

    # ── Save ───────────────────────────────────────────────────────────────────

    def _on_save(self):
        if self._audio_data is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
            initialfile="kokoro_output.wav",
            title="Save Audio As",
        )
        if path:
            self._engine.save(self._audio_data, SAMPLE_RATE, path)
            self._statusbar.set_status(f"Saved → {os.path.basename(path)}", "ok")
            Toast(self, f"Saved to {os.path.basename(path)}", kind="info")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    log_device_info()   # now logging is configured — GPU info will appear in console/log
    app = KokoroApp()
    app.mainloop()
