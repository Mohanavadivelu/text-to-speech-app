import os
import logging
import threading

import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog, messagebox

from ui.theme import C, WIN_W, WIN_H, WIN_MIN_W, WIN_MIN_H
from ui.panels.titlebar import TitleBar
from ui.panels.text_panel import TextPanel
from ui.panels.settings_panel import SettingsPanel
from ui.panels.player_bar import PlayerBar
from ui.panels.statusbar import StatusBar
from ui.components.toast import Toast
from ui.components.pronunciation_dialog import PronunciationDialog
from ui.components.download_dialog import DownloadDialog

from core.engine import TTSEngine, GenerationCancelled, SAMPLE_RATE
from core import gpu_pack, model_store, hardware
from core import text_tools, paths
from core.logging_setup import log_tk_exception
from core.player import AudioPlayer
from core.voices import VOICES, LANG_CODES, PREVIEW_TEXT
from core import settings as app_settings

log = logging.getLogger(__name__)


# Ask before generating when it is expected to take longer than this
_LONG_GENERATION_WARN_SECS = 60

# Drag-and-drop needs tkinterdnd2; the app still works without it.
try:
    from tkinterdnd2 import TkinterDnD
    _DND_BASES = (TkinterDnD.DnDWrapper,)
except ImportError:
    TkinterDnD = None
    _DND_BASES = ()


class KokoroApp(ctk.CTk, *_DND_BASES):
    def __init__(self):
        super().__init__()
        self.report_callback_exception = log_tk_exception
        self._dnd_ready = False
        if TkinterDnD is not None:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self._dnd_ready = True
            except Exception as exc:
                log.warning("Drag and drop unavailable: %s", exc)
        self.title("Kokoro TTS")
        self.geometry(f"{WIN_W}x{WIN_H}")
        self.minsize(WIN_MIN_W, WIN_MIN_H)
        self.configure(fg_color=C["bg"])
        # Always launch maximized
        self.after(0, lambda: self.state("zoomed"))

        self._engine = TTSEngine()
        self._player = AudioPlayer()
        self._player.on_progress = self._on_player_progress
        self._player.on_done = self._on_player_done
        # Voice previews use their own player so they never replace generated audio
        self._preview_player = AudioPlayer()
        self._preview_player.on_done = lambda: self.after(0, self._on_preview_finished)
        self._save_after = None
        self._draft_after = None
        self._cancel_event = None
        self._pronunciations = text_tools.load_pronunciations()
        self._pron_dialog = None
        self._idle_after = None
        self._gpu_verified = False
        self._gpu_message = ""
        self._busy_dialog = False

        self._audio_data = None
        self._audio_path = None
        self._generating = False

        self._build_ui()
        saved = app_settings.load()
        self._settings_panel.apply_state(saved)
        self._text_panel.set_font_size(saved.get("text_font_size", 11), notify=False)
        self._text_panel.load_draft(text_tools.load_draft())
        self._gpu_verified = bool(saved.get("gpu_verified")) and gpu_pack.is_installed()
        self._on_engine_change(save=False)
        if self._dnd_ready:
            self._text_panel.enable_drop(self._open_files)
        self._bind_shortcuts()
        # Clean shutdown when the window X button is clicked
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # First run: download the voice model; otherwise show which engine is in use
        self.after(600, lambda: self._ensure_model(then=self._show_device_toast) and self._show_device_toast())

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
            on_save=self._on_save,
            on_seek=self._on_seek,
            on_volume=self._on_volume,
            on_skip_back=self._on_skip_back,
            on_skip_fwd=self._on_skip_fwd,
        )
        self._player_bar.pack(side="bottom", fill="x")

        body = ctk.CTkFrame(self, fg_color=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(10, 6))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=300)
        body.grid_rowconfigure(0, weight=1)

        self._text_panel = TextPanel(
            body, on_generate=self._on_generate, on_cancel=self._on_cancel,
            on_open=self._on_open, on_pronunciations=self._open_pronunciations,
            on_change=self._schedule_draft_save, estimate_context=self._estimate_context,
        )
        self._text_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._settings_panel = SettingsPanel(
            body,
            on_language_change=self._update_voice_list,
            on_voice_change=self._on_voice_change,
            on_voice_preview=self._on_voice_preview,
            on_change=self._schedule_settings_save,
            on_engine_change=self._on_engine_change,
            on_gpu_install=self._on_gpu_install,
            on_gpu_remove=self._on_gpu_remove,
            on_gpu_retest=self._run_gpu_self_test,
        )
        self._settings_panel.grid(row=0, column=1, sticky="nsew")
        self._settings_panel.configure(width=300)

    def _bind_shortcuts(self):
        self.bind("<Escape>", lambda _e: self._on_stop())
        self.bind("<Control-s>", lambda _e: self._on_save())
        self.bind("<space>", self._on_space)
        shortcuts = {
            "<Control-o>": self._on_open,
            "<Control-f>": lambda: self._text_panel.open_find(False),
            "<Control-h>": lambda: self._text_panel.open_find(True),
        }
        text = self._text_panel.text_input._textbox
        for seq, fn in shortcuts.items():
            self.bind(seq, lambda _e, f=fn: f())
            # Tk's Text class maps Ctrl+O/F/H to old editing keys (new line,
            # cursor right, backspace); bind on the widget and stop them.
            text.bind(seq, lambda _e, f=fn: (f(), "break")[1])

    def _show_device_toast(self):
        Toast(self, f"Engine: {self._engine.device_label()}", kind="info")

    # ── Engine, model download and GPU pack ────────────────────────────────────

    def _ensure_model(self, then=None) -> bool:
        """True if the voice model is ready now. Otherwise start the download and
        return False; *then* runs only after a successful download."""
        if self._engine.model_ready():
            return True
        if self._busy_dialog:
            return False
        self._busy_dialog = True
        size = model_store.total_bytes(model_store.missing(model_store.onnx_files())) / 1e6
        self._statusbar.set_status("Downloading the voice model…", "busy")

        def done(ok):
            self._busy_dialog = False
            if ok:
                self._statusbar.set_status("Voice model ready", "ok")
                Toast(self, "Voice model downloaded — ready to generate", kind="info")
                if then:
                    then()
            else:
                self._statusbar.set_status("Voice model not downloaded — Generate will ask again", "error")

        DownloadDialog(self, "Downloading the voice model",
                       f"Kokoro needs its voice model ({size:,.0f} MB) once. After this the app works offline.",
                       lambda progress, cancel: model_store.fetch_all(model_store.onnx_files(), progress, cancel),
                       on_done=done)
        return False

    def _on_engine_change(self, save: bool = True):
        cfg = self._settings_panel.get_engine_settings()
        self._engine.configure(choice=cfg["engine"], perf_mode=cfg["perf_mode"],
                               quiet_on_battery=cfg["quiet_on_battery"], gpu_verified=self._gpu_verified)
        self._refresh_engine_ui()
        if save:
            self._schedule_settings_save()

    def _refresh_engine_ui(self):
        label = self._engine.device_label()
        self._settings_panel.set_engine_status(label)
        self._statusbar.set_device(label)
        installed = gpu_pack.is_installed()
        ok, gpu, reason = gpu_pack.eligibility()
        size_gb = gpu_pack.download_bytes() / 1e9
        name = hardware.short_gpu_name(gpu.name) if gpu else "GPU"
        if gpu_pack.removal_pending():
            self._settings_panel.set_gpu_card(True, "GPU pack", "Will be removed when you restart the app.",
                                              installed=False)
        elif installed:
            if self._gpu_verified:
                text = f"Installed · {name}. Auto uses the GPU; CPU stays available as a fallback."
                self._settings_panel.set_gpu_card(True, "GPU pack", text, "remove", "Remove GPU pack", installed=True)
            else:
                text = self._gpu_message or "Installed, but the GPU self-test has not passed yet."
                self._settings_panel.set_gpu_card(True, "GPU pack", text, "retest", "Run GPU test", installed=True)
        elif gpu_pack.is_outdated() and ok:
            self._settings_panel.set_gpu_card(True, "GPU pack", "Your GPU pack is from an older app version.",
                                              "install", f"Update GPU pack ({size_gb:.1f} GB)")
        elif ok:
            self._settings_panel.set_gpu_card(
                True, f"GPU pack · {name}",
                f"PyTorch + CUDA for your NVIDIA GPU — about 10x faster than the CPU. {size_gb:.1f} GB download.",
                "install", f"Download GPU pack ({size_gb:.1f} GB)")
        elif gpu is not None:
            self._settings_panel.set_gpu_card(True, f"GPU pack · {name}", f"Not available: {reason}")
        else:
            self._settings_panel.set_gpu_card(False)

    def _on_gpu_install(self):
        if self._generating or self._busy_dialog:
            return
        size_gb = gpu_pack.download_bytes() / 1e9
        if not messagebox.askyesno(
                "Download GPU pack",
                f"Download PyTorch with CUDA for your NVIDIA GPU?\n\n"
                f"Download: about {size_gb:.1f} GB · Disk space: about 4.5 GB\n"
                f"Files come from download.pytorch.org, PyPI and Hugging Face.\n\n"
                f"It takes a few minutes. The CPU engine stays available if anything goes wrong.",
                parent=self):
            return
        self._busy_dialog = True

        def done(ok):
            self._busy_dialog = False
            if ok:
                self._run_gpu_self_test()
            else:
                self._statusbar.set_status("GPU pack not installed", "ok")
                self._refresh_engine_ui()

        DownloadDialog(self, "Downloading the GPU pack",
                       "Installing PyTorch with CUDA and the GPU voice model. Completed files are kept if you cancel.",
                       lambda progress, cancel: gpu_pack.install(progress, cancel), on_done=done)

    def _run_gpu_self_test(self):
        if self._generating:
            return
        self._generating = True
        self._statusbar.set_status("Testing the GPU engine…", "busy")
        self._settings_panel.set_gpu_card(True, "GPU pack", "Testing the GPU engine…", installed=True)

        def worker():
            try:
                gpu = self._engine.gpu_engine()
                ok, msg = (False, "GPU pack could not be loaded.") if gpu is None else \
                    gpu_pack.self_test(gpu, self._engine.cpu)
            except Exception as exc:
                log.exception("GPU self-test crashed")
                ok, msg = False, f"GPU test failed: {exc}"
            self.after(0, lambda: self._on_gpu_test_done(ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    def _on_gpu_test_done(self, ok, msg):
        self._generating = False
        self._gpu_verified = ok
        self._gpu_message = "" if ok else msg
        self._on_engine_change()
        self._statusbar.set_status(msg, "ok" if ok else "error")
        Toast(self, msg if ok else f"{msg} Using the CPU engine.", kind="info" if ok else "error")

    def _on_gpu_remove(self):
        if self._generating:
            return
        mb = gpu_pack.installed_size_mb()
        if not messagebox.askyesno("Remove GPU pack",
                                   f"Remove the GPU pack and free about {mb / 1024:.1f} GB?\n"
                                   "The app keeps working on the CPU.", parent=self):
            return
        self._gpu_verified = False
        self._gpu_message = ""
        if gpu_pack.removal_needs_restart():
            gpu_pack.request_removal()
            Toast(self, "GPU pack will be removed when you restart the app", kind="info")
        else:
            gpu_pack.remove()
            Toast(self, "GPU pack removed", kind="info")
        self._on_engine_change()

    def _schedule_idle_release(self, minutes: int = 10):
        """Free model memory after a while without generating."""
        if self._idle_after:
            self.after_cancel(self._idle_after)
        self._idle_after = self.after(minutes * 60_000, self._idle_release)

    def _idle_release(self):
        self._idle_after = None
        if not self._generating:
            self._engine.release()

    # ── Voice helpers ──────────────────────────────────────────────────────────

    def _update_voice_list(self, lang_key: str):
        """Language changed. All voices are downloaded with the model, so nothing to fetch."""

    def _schedule_settings_save(self):
        """Debounce saves so dragging a slider writes the file once."""
        if self._save_after:
            self.after_cancel(self._save_after)
        self._save_after = self.after(600, self._save_settings)

    def _save_settings(self):
        self._save_after = None
        state = self._settings_panel.get_state()
        state["text_font_size"] = self._text_panel.font_size
        state["gpu_verified"] = self._gpu_verified
        app_settings.save(state)
        self._text_panel.refresh_counts()   # speed/language change the audio estimate

    def _estimate_context(self):
        panel = getattr(self, "_settings_panel", None)
        if panel is None:
            return "a", 1.0
        return LANG_CODES.get(panel.get_language_key(), "a"), panel.get_speed()

    # ── Text helpers ───────────────────────────────────────────────────────────

    def _schedule_draft_save(self):
        """Text or zoom changed: save the draft and font size shortly after."""
        if self._draft_after:
            self.after_cancel(self._draft_after)
        self._draft_after = self.after(1000, self._save_draft)
        self._schedule_settings_save()

    def _save_draft(self):
        self._draft_after = None
        text_tools.save_draft(self._text_panel.text_input.get("1.0", "end-1c"))

    def _on_open(self):
        if self._generating:
            return
        path = filedialog.askopenfilename(title="Open text", filetypes=text_tools.OPEN_FILETYPES)
        if path:
            self._open_files([path])

    def _open_files(self, paths):
        if self._generating or not paths:
            return
        path = paths[0]
        try:
            text, cleaned = text_tools.load_text_file(path)
        except ValueError as exc:
            Toast(self, str(exc), kind="error")
            return
        if not text.strip():
            Toast(self, f"{os.path.basename(path)} has no text.", kind="error")
            return
        self._text_panel.set_text(text)
        note = " (cleaned)" if cleaned else ""
        extra = f" · {len(paths) - 1} other file(s) ignored" if len(paths) > 1 else ""
        self._statusbar.set_status(f"Opened {os.path.basename(path)}{note}", "ok")
        Toast(self, f"Opened {os.path.basename(path)}{note}{extra} · Ctrl+Z to undo", kind="info")

    def _open_pronunciations(self):
        if self._pron_dialog is not None and self._pron_dialog.winfo_exists():
            self._pron_dialog.lift()
            return
        self._pron_dialog = PronunciationDialog(
            self, on_saved=self._on_pronunciations_saved,
            on_test=lambda text: self._on_voice_preview(text=text, status="Testing pronunciation…"))

    def _on_pronunciations_saved(self, entries):
        self._pronunciations = entries
        Toast(self, f"Saved {len(entries)} pronunciation(s)", kind="info")

    def _on_voice_change(self, _label: str):
        pass  # voice is read from the settings panel at generate time

    def _on_voice_preview(self, text=None, status="Previewing voice…"):
        """Generate and play a short sample; clicking again while it plays stops it."""
        if self._preview_player.is_playing:
            self._preview_player.stop()
            self._on_preview_finished()
            return
        if self._generating:
            return
        if not self._ensure_model():
            return
        self._generating = True
        if self._player.is_playing:
            self._player.pause()
            self._player_bar.set_playing(False)
        self._settings_panel.set_preview_state("busy")
        self._statusbar.set_status(status, "busy")

        lang_key  = self._settings_panel.get_language_key()
        lang_code = LANG_CODES.get(lang_key, "a")
        voice_id  = self._settings_panel.get_voice_id()
        blend_voice, blend_ratio = self._settings_panel.get_blend()
        speed     = self._settings_panel.get_speed()
        pitch     = self._settings_panel.get_pitch()
        text      = text or PREVIEW_TEXT.get(lang_key, PREVIEW_TEXT["American English"])

        def _worker():
            try:
                audio, sr = self._engine.generate(
                    text, lang_code, voice_id, speed, pitch=pitch,
                    blend_voice=blend_voice, blend_ratio=blend_ratio)
                self.after(0, lambda: self._on_preview_done(audio, sr))
            except Exception as exc:
                log.exception("Preview failed: %s", exc)
                self.after(0, lambda msg=str(exc): self._on_preview_error(msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_preview_done(self, audio, sr):
        """Play the preview on its own player; the main player keeps its audio."""
        self._generating = False
        self._schedule_idle_release()
        self._preview_player.load(audio, sr)
        self._preview_player.play()
        self._settings_panel.set_preview_state("playing")
        self._statusbar.set_status("Playing preview…", "busy")

    def _on_preview_finished(self):
        self._settings_panel.set_preview_state("idle")
        self._statusbar.set_status("Ready", "ok")

    def _on_preview_error(self, msg: str):
        self._generating = False
        self._settings_panel.set_preview_state("idle")
        self._on_generate_error(msg)

    # ── Generate ───────────────────────────────────────────────────────────────

    def _on_generate(self):
        if self._generating:
            return
        text, is_selection = self._text_panel.get_generate_text()
        if not text:
            Toast(self, "Please enter some text first.", kind="error")
            return
        if not self._ensure_model(then=self._on_generate):
            return

        lang_key    = self._settings_panel.get_language_key()
        lang_code   = LANG_CODES.get(lang_key, "a")
        audio_est   = text_tools.estimate_seconds(text, lang_code, self._settings_panel.get_speed())
        gen_est     = self._engine.estimate_generation_seconds(audio_est)
        if gen_est > _LONG_GENERATION_WARN_SECS and not messagebox.askyesno(
                "Long text",
                f"This is about {text_tools.format_duration(audio_est)} of audio.\n"
                f"Generating it will take roughly {text_tools.format_duration(gen_est)} "
                f"on {self._engine.device_label()}.\n\nYou can cancel at any time. Continue?",
                parent=self):
            return

        if self._preview_player.is_playing:
            self._preview_player.stop()
            self._on_preview_finished()
        self._generating = True
        self._cancel_event = threading.Event()
        self._text_panel.set_generating(True)
        self._player_bar.set_generating(True)
        what = f"selection ({len(text):,} characters)" if is_selection else "audio"
        self._statusbar.set_status(f"Generating {what}…", "busy")
        text = text_tools.apply_pronunciations(text, self._pronunciations, lang_code)

        voice_id    = self._settings_panel.get_voice_id()
        blend       = self._settings_panel.get_blend()
        speed       = self._settings_panel.get_speed()
        pitch       = self._settings_panel.get_pitch()

        threading.Thread(
            target=self._generate_worker,
            args=(text, lang_code, voice_id, speed, pitch, blend,
                  self._cancel_event),
            daemon=True,
        ).start()

    def _generate_worker(self, text, lang_code, voice_id, speed, pitch,
                         blend=(None, 0.0), cancel_event=None):
        try:
            first_chunk_played = threading.Event()

            def on_status(msg):
                self.after(0, lambda: self._statusbar.set_status(msg, "busy"))

            def on_progress(pct: int):
                if not (cancel_event and cancel_event.is_set()):
                    self.after(0, lambda p=pct: self._text_panel.set_generating(True, p))

            def on_chunk(chunk_audio):
                """Stream first chunk to player immediately so playback starts early."""
                if not first_chunk_played.is_set():
                    first_chunk_played.set()
                    self.after(0, lambda a=chunk_audio: self._on_first_chunk(a))

            audio, sr = self._engine.generate(
                text, lang_code, voice_id, speed,
                pitch=pitch, on_status=on_status, on_progress=on_progress,
                on_chunk=on_chunk, blend_voice=blend[0], blend_ratio=blend[1],
                cancel_event=cancel_event,
            )
            # audio_output/ddmmyyyy_HHMMSS.wav, stamped when the audio is finished
            output_path = paths.new_output_path()
            self._engine.save(audio, sr, output_path)
            self.after(0, lambda: self._on_generate_done(audio, sr, output_path, voice_id))
        except GenerationCancelled:
            self.after(0, self._on_generate_cancelled)
        except Exception as exc:
            log.exception("Generation failed: %s", exc)
            self.after(0, lambda msg=str(exc): self._on_generate_error(msg))

    def _on_cancel(self):
        if self._generating and self._cancel_event is not None:
            self._cancel_event.set()
            self._text_panel.set_cancelling()
            self._statusbar.set_status("Cancelling…", "busy")

    def _on_generate_cancelled(self):
        """Nothing is saved; the player goes back to the previous audio (if any)."""
        self._generating = False
        self._cancel_event = None
        self._text_panel.set_generating(False)
        self._player_bar.set_generating(False)
        self._restore_previous_audio()
        self._statusbar.set_status("Generation cancelled", "ok")
        Toast(self, "Generation cancelled", kind="info")

    def _restore_previous_audio(self):
        """Drop any half-streamed clip and show the last finished audio again."""
        if self._audio_data is not None:
            self._player.load(self._audio_data, SAMPLE_RATE)
            name = os.path.basename(self._audio_path) if self._audio_path else "audio"
            self._player_bar.set_audio_ready(name, len(self._audio_data) / SAMPLE_RATE)
            self._player_bar.set_audio_data(self._audio_data, SAMPLE_RATE)
        else:
            self._player.unload()
            self._player_bar.set_no_audio()

    def _on_first_chunk(self, chunk_audio):
        """Load the first audio chunk into the player so playback can start immediately."""
        import numpy as np
        if self._cancel_event is not None and self._cancel_event.is_set():
            return
        chunk_audio = np.asarray(chunk_audio, dtype=np.float32)
        self._player.load(chunk_audio, SAMPLE_RATE)
        duration = len(chunk_audio) / SAMPLE_RATE
        self._player_bar.set_audio_ready("generating…", duration)
        self._statusbar.set_status("First segment ready — click ▶ to preview", "ok")

    def _on_generate_done(self, audio, sr, path, voice_id):
        self._generating = False
        self._schedule_idle_release()
        fallback = self._engine.take_fallback_notice()
        if fallback:
            Toast(self, "The GPU failed, so this was generated on the CPU. See the log for details.",
                  kind="error")
        self._cancel_event = None
        self._audio_data = audio
        self._audio_path = path

        self._player.load(audio, sr)

        duration = len(audio) / sr
        filename = os.path.basename(path)
        meta = text_tools.format_duration(duration)

        self._text_panel.set_generating(False)
        self._player_bar.set_generating(False)
        self._player_bar.set_audio_ready(filename, duration, sample_rate=sr)
        self._player_bar.set_audio_data(audio, sr)   # render waveform

        self._settings_panel.update_output_info(filename, meta)
        self._statusbar.set_status(f"Done — saved to {os.path.basename(paths.AUDIO_DIR)}{os.sep}{filename}", "ok")

        Toast(self, f"Saved to {filename}", kind="info")

    def _on_generate_error(self, msg: str):
        was_generating = self._cancel_event is not None
        self._generating = False
        self._cancel_event = None
        self._text_panel.set_generating(False)
        self._player_bar.set_generating(False)
        if was_generating:
            self._restore_previous_audio()
        self._statusbar.set_status(f"Error: {msg}", "error")
        Toast(self, f"Error: {msg}", kind="error")

    # ── Playback ───────────────────────────────────────────────────────────────

    def _on_play(self):
        # Allow playback if full audio is ready OR if a streaming chunk is loaded
        if self._audio_data is None and not self._player.has_audio:
            return
        if self._preview_player.is_playing:
            self._preview_player.stop()
            self._on_preview_finished()
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
        self._player.seek(ratio)

    def _on_skip_back(self):
        """Skip back 5 seconds."""
        if self._audio_data is None:
            return
        new_pos = max(0.0, self._player.position - 5.0 / self._player.duration)
        self._on_seek(new_pos)
        self._player_bar.update_progress(new_pos, self._player.duration)

    def _on_skip_fwd(self):
        """Skip forward 5 seconds."""
        if self._audio_data is None:
            return
        new_pos = min(1.0, self._player.position + 5.0 / self._player.duration)
        self._on_seek(new_pos)
        self._player_bar.update_progress(new_pos, self._player.duration)

    def _on_volume(self, value: float):
        self._player.set_volume(value)

    def _on_space(self, event):
        # The key event's widget is where the key was pressed; focus_get() can be
        # None when the window isn't active.
        focused = getattr(event, "widget", None) or self.focus_get()
        if isinstance(focused, (tk.Text, tk.Entry)):
            return   # typing a space, not a playback shortcut
        self._player_bar.toggle_play()

    def _on_player_progress(self, ratio: float):
        duration = self._player.duration
        self.after(0, lambda: self._player_bar.update_progress(ratio, duration))

    def _on_player_done(self):
        self.after(0, self._player_bar.on_playback_done)
        self.after(0, lambda: self._statusbar.set_status("Ready", "ok"))

    # ── Clean shutdown ─────────────────────────────────────────────────────────

    def _on_close(self):
        """Called when the window X button is clicked. Stops all threads cleanly."""
        import sys
        import sounddevice as sd
        try:
            # Persist settings, then stop audio and release the sounddevice stream
            if self._save_after:
                self.after_cancel(self._save_after)
            self._save_settings()
            if self._draft_after:
                self.after_cancel(self._draft_after)
            self._save_draft()
            if self._cancel_event is not None:
                self._cancel_event.set()
            self._preview_player.stop()
            self._player.stop()
            sd.stop()
        except Exception:
            pass
        try:
            # Cancel any pending statusbar pulse timer
            if hasattr(self._statusbar, "_pulse_after") and self._statusbar._pulse_after:
                self.after_cancel(self._statusbar._pulse_after)
                self._statusbar._pulse_after = None
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        # Force-exit the process so background daemon threads don't keep it alive
        sys.exit(0)

    # ── Save ───────────────────────────────────────────────────────────────────

    def _on_save(self):
        if self._audio_data is None or self._generating or not self._player_bar.can_save:
            return
        suggested = os.path.basename(self._audio_path) if self._audio_path else "kokoro_output.wav"
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
            initialfile=suggested,
            initialdir=paths.AUDIO_DIR,
            title="Save Audio As",
            parent=self,
        )
        if not path:
            return
        try:
            self._engine.save(self._audio_data, SAMPLE_RATE, path)
        except Exception as exc:
            log.exception("Save failed")
            self._statusbar.set_status(f"Could not save: {exc}", "error")
            Toast(self, f"Could not save: {exc}", kind="error")
            return
        self._player_bar.flash_saved()
        self._statusbar.set_status(f"Saved → {os.path.basename(path)}", "ok")
        Toast(self, f"Saved to {os.path.basename(path)}", kind="info")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import app
    app.main()
