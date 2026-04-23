import logging
import threading
import time
import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self):
        self._audio = None
        self._sample_rate = 24000
        self._volume = 1.0
        self._playing = False
        self._paused = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._position = 0.0          # ratio 0.0–1.0
        self._start_sample = 0        # sample index to resume from

        self.on_progress = None       # callback(position_ratio: float)
        self.on_done = None           # callback()

    def load(self, audio, sample_rate: int):
        self.stop()
        # Normalise to a float32 numpy array regardless of source (numpy or torch.Tensor)
        if hasattr(audio, "numpy"):
            audio = audio.detach().cpu().numpy()
        self._audio = np.asarray(audio, dtype=np.float32)
        self._sample_rate = sample_rate
        self._position = 0.0
        self._start_sample = 0

    def play(self):
        """Start or resume playback from the current position."""
        if self._audio is None:
            return
        if self._playing:
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._playing = True
        self._paused = False
        threading.Thread(target=self._worker, daemon=True).start()

    def pause(self):
        """Pause playback, preserving the current position."""
        if not self._playing:
            return
        self._pause_event.set()
        sd.stop()
        self._playing = False
        self._paused = True

    def stop(self):
        """Stop playback and reset position to the beginning."""
        self._stop_event.set()
        self._pause_event.clear()
        sd.stop()
        self._playing = False
        self._paused = False
        self._position = 0.0
        self._start_sample = 0

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        if self._audio is None or self._sample_rate == 0:
            return 0.0
        return len(self._audio) / self._sample_rate

    def _worker(self):
        try:
            # Slice audio from the resume point — handle both numpy arrays and torch Tensors
            start = self._start_sample
            raw = self._audio[start:]
            if hasattr(raw, "numpy"):          # torch.Tensor
                raw = raw.detach().cpu().numpy()
            audio_slice = (np.asarray(raw, dtype=np.float32)) * self._volume
            total_samples = len(self._audio)
            sr = self._sample_rate

            finished = threading.Event()

            def _stream_finished():
                finished.set()

            with sd.OutputStream(
                samplerate=sr,
                channels=1 if audio_slice.ndim == 1 else audio_slice.shape[1],
                dtype="float32",
                finished_callback=_stream_finished,
            ) as stream:
                # Write in chunks so we can check stop/pause
                chunk_size = sr // 10  # 100 ms chunks
                offset = 0
                while offset < len(audio_slice):
                    if self._stop_event.is_set():
                        stream.abort()
                        return
                    if self._pause_event.is_set():
                        stream.abort()
                        # Save resume position
                        self._start_sample = start + offset
                        self._position = self._start_sample / total_samples
                        return
                    chunk = audio_slice[offset: offset + chunk_size]
                    stream.write(chunk)
                    offset += len(chunk)
                    self._start_sample = start + offset
                    self._position = min(1.0, self._start_sample / total_samples)
                    if self.on_progress:
                        self.on_progress(self._position)

                # Wait for stream to drain
                finished.wait(timeout=2.0)

            # Natural end — reset to beginning
            self._position = 1.0
            self._start_sample = 0
            self._playing = False
            log.info("Playback finished")

        except Exception as exc:
            log.error("Playback error: %s", exc)
            self._playing = False

        if self.on_done:
            self.on_done()
