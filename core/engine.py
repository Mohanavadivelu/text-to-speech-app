import logging
import re
import threading
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import torch
import numpy as np
import soundfile as sf

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000

# ── Device selection ──────────────────────────────────────────────────────────
# Use CUDA if available, otherwise fall back to CPU.
if torch.cuda.is_available():
    DEVICE = "cuda"
    # Allow cuDNN to auto-tune for best performance on this GPU
    torch.backends.cudnn.benchmark = True
    log.info("Using CUDA device: %s  (%.1f GB VRAM)",
             torch.cuda.get_device_name(0),
             torch.cuda.get_device_properties(0).total_memory / 1024**3)
else:
    DEVICE = "cpu"
    # Use all available CPU threads for inference
    torch.set_num_threads(os.cpu_count() or 4)
    log.info("CUDA not available — using CPU with %d threads", torch.get_num_threads())

# Maximum characters per segment sent to KPipeline in one call.
# Kokoro works best on ~500-char segments; larger inputs slow it down.
_MAX_SEGMENT_CHARS = 500

# Number of parallel KPipeline workers.
# On GPU: 1 worker (GPU is already parallel internally).
# On CPU: up to 2 workers to use multiple cores.
_MAX_WORKERS = 1 if DEVICE == "cuda" else 2


def _split_paragraphs(text: str, max_chars: int = _MAX_SEGMENT_CHARS) -> list[str]:
    """Split text into segments ≤ max_chars, breaking on paragraph/sentence boundaries."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    segments = []
    for para in paragraphs:
        if len(para) <= max_chars:
            segments.append(para)
        else:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= max_chars:
                    current = (current + " " + sent).strip() if current else sent
                else:
                    if current:
                        segments.append(current)
                    while len(sent) > max_chars:
                        segments.append(sent[:max_chars])
                        sent = sent[max_chars:]
                    current = sent
            if current:
                segments.append(current)

    return segments or [text]


class TTSEngine:
    def __init__(self):
        self._pipeline = None
        self._pipeline_lang = None
        self._lock = threading.Lock()
        self._aux_pipelines: list = []
        self._aux_lock = threading.Lock()

    # ── Pipeline management ───────────────────────────────────────────────────

    def _get_pipeline(self, lang_code: str, on_status=None):
        from kokoro import KPipeline
        if self._pipeline is None or self._pipeline_lang != lang_code:
            log.info("Loading KPipeline for lang_code=%s on device=%s", lang_code, DEVICE)
            if on_status:
                on_status(f"Loading model on {DEVICE.upper()}…")
            self._pipeline = KPipeline(lang_code=lang_code, device=DEVICE)
            self._pipeline_lang = lang_code
            self._aux_pipelines = []
            log.info("KPipeline ready on %s", DEVICE)
        return self._pipeline

    def _get_aux_pipeline(self, lang_code: str):
        from kokoro import KPipeline
        with self._aux_lock:
            if len(self._aux_pipelines) < _MAX_WORKERS - 1:
                log.info("Creating auxiliary KPipeline #%d on %s",
                         len(self._aux_pipelines) + 1, DEVICE)
                p = KPipeline(lang_code=lang_code, device=DEVICE)
                self._aux_pipelines.append(p)
                return p
            idx = len(self._aux_pipelines) % max(1, len(self._aux_pipelines))
            return self._aux_pipelines[idx]

    # ── Audio helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _run_pipeline(pipeline, text: str, voice_id: str, speed: float) -> np.ndarray:
        chunks = []
        for _gs, _ps, audio in pipeline(text, voice=voice_id, speed=speed):
            if hasattr(audio, "numpy"):
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks) if len(chunks) > 1 else chunks[0]

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, text: str, lang_code: str, voice_id: str, speed: float,
                 pitch: float = 0.0, on_status=None, on_progress=None,
                 on_chunk=None):
        """Generate audio for *text*.

        Returns (np.ndarray[float32], sample_rate).

        Callbacks (all optional, called from the worker thread):
          on_status(msg: str)          — human-readable status string
          on_progress(pct: int)        — 0-99 during generation, 100 when done
          on_chunk(audio: np.ndarray)  — called with each completed segment
        """
        with self._lock:
            pipeline = self._get_pipeline(lang_code, on_status=on_status)

        segments = _split_paragraphs(text)
        total_segs = len(segments)
        log.info("Generating %d segment(s) for %d chars, voice=%s speed=%s device=%s",
                 total_segs, len(text), voice_id, speed, DEVICE)

        if on_status:
            on_status(f"Generating… 0 / {total_segs} segments [{DEVICE.upper()}]")

        all_chunks: list = [None] * total_segs

        if total_segs == 1 or _MAX_WORKERS <= 1:
            # ── Single-threaded path (GPU or single-core CPU) ─────────────────
            for i, seg in enumerate(segments):
                with self._lock:
                    audio = self._run_pipeline(pipeline, seg, voice_id, speed)
                all_chunks[i] = audio
                if on_chunk:
                    on_chunk(audio)
                pct = min(99, int((i + 1) / total_segs * 100))
                if on_progress:
                    on_progress(pct)
                if on_status:
                    on_status(f"Generating… {i + 1} / {total_segs} [{DEVICE.upper()}]")
        else:
            # ── Parallel path (CPU multi-core) ────────────────────────────────
            def _warm():
                self._get_aux_pipeline(lang_code)
            threading.Thread(target=_warm, daemon=True).start()

            done_count = 0
            result_lock = threading.Lock()

            def _process(idx: int, seg: str):
                nonlocal done_count
                if idx % 2 == 0:
                    with self._lock:
                        audio = self._run_pipeline(pipeline, seg, voice_id, speed)
                else:
                    aux = self._get_aux_pipeline(lang_code)
                    with self._aux_lock:
                        audio = self._run_pipeline(aux, seg, voice_id, speed)
                return idx, audio

            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
                futures = {pool.submit(_process, i, seg): i
                           for i, seg in enumerate(segments)}
                for fut in as_completed(futures):
                    idx, audio = fut.result()
                    all_chunks[idx] = audio
                    with result_lock:
                        done_count += 1
                        pct = min(99, int(done_count / total_segs * 100))
                    if on_chunk:
                        on_chunk(audio)
                    if on_progress:
                        on_progress(pct)
                    if on_status:
                        on_status(f"Generating… {done_count} / {total_segs} [CPU]")

        if not any(c is not None and len(c) > 0 for c in all_chunks):
            raise RuntimeError("TTS pipeline produced no audio output.")

        valid = [c for c in all_chunks if c is not None and len(c) > 0]
        full_audio = np.concatenate(valid) if len(valid) > 1 else valid[0]

        if on_progress:
            on_progress(100)

        log.info("Generation complete: %.2fs of audio on %s", len(full_audio) / SAMPLE_RATE, DEVICE)
        return full_audio, SAMPLE_RATE

    def save(self, audio, sample_rate: int, path: str):
        if hasattr(audio, "numpy"):
            audio = audio.detach().cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32)
        sf.write(path, audio, sample_rate)
        log.info("Saved audio → %s  (%.2fs)", path, len(audio) / sample_rate)

    @staticmethod
    def device_info() -> str:
        """Return a human-readable string describing the active compute device."""
        if DEVICE == "cuda":
            name = torch.cuda.get_device_name(0)
            vram = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
            return f"🖥️ {name} · {vram} GB VRAM · CUDA"
        cores = os.cpu_count() or 1
        return f"🖥️ CPU · {cores} threads"
