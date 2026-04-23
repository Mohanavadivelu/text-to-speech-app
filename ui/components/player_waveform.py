import tkinter as tk
import numpy as np
from ui.theme import C, FONT_SMALL


class PlayerWaveformCanvas(tk.Canvas):
    """Draws played/unplayed waveform bars with a progress overlay."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#15151c", highlightthickness=0, **kwargs)
        self._audio = None
        self._sr = 24000
        self._progress = 0.0
        self._seek_callback = None
        self.bind("<Configure>", lambda _e: self._render())
        self.bind("<Button-1>", self._on_click)
        self._draw_empty()

    def set_audio(self, audio: np.ndarray, sample_rate: int):
        self._audio = audio
        self._sr = sample_rate
        self._progress = 0.0
        self.after(50, self._render)

    def set_progress(self, position_ratio: float):
        self._progress = max(0.0, min(1.0, position_ratio))
        self._render()

    def clear(self):
        self._audio = None
        self._progress = 0.0
        self._draw_empty()

    def _draw_empty(self):
        self.delete("all")
        w = self.winfo_reqwidth() or 600
        h = self.winfo_reqheight() or 32
        self.create_text(w // 2, h // 2,
                         text="Generate audio to see waveform",
                         fill=C["text3"], font=FONT_SMALL)

    def _render(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        if self._audio is None:
            self.create_text(w // 2, h // 2,
                             text="Generate audio to see waveform",
                             fill=C["text3"], font=FONT_SMALL)
            return

        n_bars = max(1, w // 2)
        step = max(1, len(self._audio) // n_bars)
        samples = self._audio[::step][:n_bars]
        bar_w = max(1, w // len(samples))
        mid = h // 2
        progress_x = int(self._progress * w)

        for i, s in enumerate(samples):
            amp = int(abs(float(s)) * mid * 0.9)
            amp = max(1, min(amp, mid - 2))
            x = i * bar_w
            color = C["waveform_played"] if x < progress_x else C["waveform_unplayed"]
            self.create_line(x, mid - amp, x, mid + amp, fill=color, width=max(1, bar_w - 1))

        if progress_x > 0:
            self.create_rectangle(0, 0, progress_x, h,
                                  fill="white", stipple="gray12", outline="")
            self.create_line(progress_x, 0, progress_x, h, fill="white", width=1)

    def _on_click(self, event):
        w = self.winfo_width()
        if w > 0 and self._seek_callback:
            self._seek_callback(event.x / w)
