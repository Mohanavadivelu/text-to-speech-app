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
        self._position = 0.0

        self.on_progress = None  # callback(position_ratio: float)
        self.on_done = None      # callback()

    def load(self, audio: np.ndarray, sample_rate: int):
        self._audio = audio
        self._sample_rate = sample_rate
        self._position = 0.0

    def play(self):
        if self._audio is None:
            return
        self._stop_event.clear()
        self._playing = True
        self._paused = False
        threading.Thread(target=self._worker, daemon=True).start()

    def pause(self):
        sd.stop()
        self._playing = False
        self._paused = True

    def stop(self):
        sd.stop()
        self._stop_event.set()
        self._playing = False
        self._paused = False
        self._position = 0.0

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
            audio = self._audio * self._volume
            sd.play(audio, self._sample_rate)
            total = self.duration
            start = time.time()

            while True:
                stream = sd.get_stream()
                if stream is None or not stream.active:
                    break
                if self._stop_event.is_set():
                    sd.stop()
                    return
                elapsed = time.time() - start
                self._position = min(1.0, elapsed / total) if total > 0 else 0.0
                if self.on_progress:
                    self.on_progress(self._position)
                time.sleep(0.05)

            self._position = 1.0
            self._playing = False
            log.info("Playback finished")
        except Exception as exc:
            log.error("Playback error: %s", exc)
            self._playing = False

        if self.on_done:
            self.on_done()
