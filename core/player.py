import logging
import threading
import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class AudioPlayer:
    """Plays a mono/stereo float32 buffer with pause, resume, seek and live volume.

    Each playback run owns its own stop event and worker thread. Starting a new
    run always halts and joins the previous worker first, so two streams can
    never overlap, and a stale worker can never overwrite position or fire
    on_done for a newer run.
    """

    _JOIN_TIMEOUT = 0.5  # seconds; a 100 ms chunk write is the longest block

    def __init__(self):
        self._audio = None
        self._sample_rate = 24000
        self._volume = 1.0
        self._playing = False
        self._paused = False
        self._position = 0.0          # ratio 0.0–1.0
        self._start_sample = 0        # sample index to resume from

        self._run_stop: threading.Event | None = None
        self._thread: threading.Thread | None = None

        self.on_progress = None       # callback(position_ratio: float)
        self.on_done = None           # callback()

    # ── Worker lifecycle ──────────────────────────────────────────────────────

    def _halt_worker(self):
        """Signal the current worker to exit and wait for it."""
        if self._run_stop is not None:
            self._run_stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=self._JOIN_TIMEOUT)
            if t.is_alive():
                log.warning("Playback worker did not exit within %.1fs", self._JOIN_TIMEOUT)
        self._thread = None
        self._run_stop = None

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, audio, sample_rate: int):
        self.stop()
        # Normalise to a float32 numpy array regardless of source (numpy or torch.Tensor)
        if hasattr(audio, "numpy"):
            audio = audio.detach().cpu().numpy()
        self._audio = np.asarray(audio, dtype=np.float32)
        self._sample_rate = sample_rate
        self._position = 0.0
        self._start_sample = 0

    @property
    def has_audio(self) -> bool:
        return self._audio is not None and len(self._audio) > 0

    def play(self):
        """Start or resume playback from the current position."""
        if not self.has_audio or self._playing:
            return
        self._halt_worker()
        if self._start_sample >= len(self._audio):
            self._start_sample = 0
            self._position = 0.0
        stop_evt = threading.Event()
        self._run_stop = stop_evt
        self._playing = True
        self._paused = False
        self._thread = threading.Thread(target=self._worker, args=(stop_evt,), daemon=True)
        self._thread.start()

    def pause(self):
        """Pause playback, preserving the current position."""
        if not self._playing:
            return
        self._halt_worker()
        self._playing = False
        self._paused = True

    def stop(self):
        """Stop playback and reset position to the beginning."""
        self._halt_worker()
        self._playing = False
        self._paused = False
        self._position = 0.0
        self._start_sample = 0

    def seek(self, ratio: float):
        """Jump to *ratio* (0.0–1.0) of the track, keeping play/pause state."""
        if not self.has_audio:
            return
        ratio = max(0.0, min(1.0, ratio))
        was_playing = self._playing
        self._halt_worker()
        self._playing = False
        self._start_sample = min(int(ratio * len(self._audio)), len(self._audio))
        self._position = ratio
        if was_playing:
            self.play()

    def set_volume(self, volume: float):
        """Takes effect on the next 100 ms chunk, including during playback."""
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

    # ── Worker ────────────────────────────────────────────────────────────────

    def _worker(self, stop_evt: threading.Event):
        audio = self._audio
        sr = self._sample_rate
        total_samples = len(audio)
        offset = self._start_sample
        finished_naturally = False

        try:
            channels = 1 if audio.ndim == 1 else audio.shape[1]
            chunk_size = max(1, sr // 10)  # 100 ms chunks
            drained = threading.Event()

            with sd.OutputStream(samplerate=sr, channels=channels, dtype="float32",
                                 finished_callback=drained.set) as stream:
                while offset < total_samples:
                    if stop_evt.is_set():
                        stream.abort()
                        return
                    chunk = audio[offset: offset + chunk_size] * self._volume
                    stream.write(chunk)
                    offset += len(chunk)
                    if stop_evt.is_set():
                        # Halted mid-write: the owner may have set a new position.
                        stream.abort()
                        return
                    self._start_sample = offset
                    self._position = min(1.0, offset / total_samples)
                    if self.on_progress:
                        self.on_progress(self._position)

            # Leaving the context manager stops the stream after the buffer
            # plays out; wait for the finished callback before reporting done.
            drained.wait(timeout=2.0)
            finished_naturally = True

        except Exception as exc:
            log.error("Playback error: %s", exc)

        if stop_evt.is_set():
            return  # superseded by stop/pause/seek; the caller owns the state

        self._playing = False
        self._paused = False
        if finished_naturally:
            self._position = 1.0
            self._start_sample = 0
            log.info("Playback finished")
        if self.on_done:
            self.on_done()
