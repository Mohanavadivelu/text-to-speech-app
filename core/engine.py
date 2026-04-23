import logging
import threading
import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000


class TTSEngine:
    def __init__(self):
        self._pipeline = None
        self._pipeline_lang = None
        self._lock = threading.Lock()

    def generate(self, text, lang_code, voice_id, speed, pitch=0.0,
                 on_status=None, on_progress=None):
        """Generate audio. Returns (np.ndarray, sample_rate). Blocks until done.

        on_progress(pct: int) is called after each chunk with 1-99% progress.
        """
        from kokoro import KPipeline

        with self._lock:
            if self._pipeline is None or self._pipeline_lang != lang_code:
                log.info("Loading KPipeline for lang_code=%s", lang_code)
                if on_status:
                    on_status("Loading model…")
                self._pipeline = KPipeline(lang_code=lang_code)
                self._pipeline_lang = lang_code
                log.info("KPipeline ready")

            log.info("Generating: chars=%d  voice=%s  speed=%s  pitch=%s",
                     len(text), voice_id, speed, pitch)

            # Collect all chunks; estimate total from character count
            total_chars = max(len(text), 1)
            processed_chars = 0
            chunks = []
            for gs, _ps, audio in self._pipeline(text, voice=voice_id, speed=speed):
                # KPipeline may yield torch.Tensors — normalise to numpy float32
                if hasattr(audio, "numpy"):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32))
                # gs is the grapheme string for this chunk — use its length for progress
                if gs:
                    processed_chars += len(gs)
                pct = min(99, int(processed_chars / total_chars * 100))
                if on_progress:
                    on_progress(pct)

        if not chunks:
            raise RuntimeError("TTS pipeline produced no audio output.")

        full_audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        return full_audio, SAMPLE_RATE

    def save(self, audio, sample_rate, path):
        sf.write(path, audio, sample_rate)
        log.info("Saved audio → %s  (%.2fs)", path, len(audio) / sample_rate)
