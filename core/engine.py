import logging
import threading
import numpy as np
import soundfile as sf
import os

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000


class TTSEngine:
    def __init__(self):
        self._pipeline = None
        self._pipeline_lang = None
        self._lock = threading.Lock()

    def generate(self, text, lang_code, voice_id, speed, on_status=None):
        """Generate audio. Returns (np.ndarray, sample_rate). Blocks until done."""
        from kokoro import KPipeline

        with self._lock:
            if self._pipeline is None or self._pipeline_lang != lang_code:
                log.info("Loading KPipeline for lang_code=%s", lang_code)
                if on_status:
                    on_status("Loading model…")
                self._pipeline = KPipeline(lang_code=lang_code)
                self._pipeline_lang = lang_code
                log.info("KPipeline ready")

            log.info("Generating: chars=%d  voice=%s  speed=%s", len(text), voice_id, speed)
            chunks = []
            for _gs, _ps, audio in self._pipeline(text, voice=voice_id, speed=speed):
                chunks.append(audio)

        full_audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        return full_audio, SAMPLE_RATE

    def save(self, audio, sample_rate, path):
        sf.write(path, audio, sample_rate)
        log.info("Saved audio → %s  (%.2fs)", path, len(audio) / sample_rate)
