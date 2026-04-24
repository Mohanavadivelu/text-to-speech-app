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

# ── Device selection & GPU optimization ───────────────────────────────────────
# ✓ Using maximum GPU capabilities for fastest inference
if torch.cuda.is_available():
    DEVICE = "cuda"

    # === MAXIMIZING GPU PERFORMANCE ===
    # Enable cuDNN auto-tuning for optimal GPU kernels on this hardware
    torch.backends.cudnn.benchmark = True
    # Ensure determinism doesn't slow down inference (use fastest algorithms)
    torch.backends.cudnn.deterministic = False

    # Get GPU memory info
    gpu_props = torch.cuda.get_device_properties(0)
    gpu_name = torch.cuda.get_device_name(0)
    total_vram = gpu_props.total_memory / 1024**3
    compute_capability = f"{gpu_props.major}.{gpu_props.minor}"

    # Defer GPU info logging — basicConfig may not be set up yet at import time.
    # Call log_device_info() after logging is configured.
else:
    DEVICE = "cpu"
    # Use all available CPU threads for inference
    torch.set_num_threads(os.cpu_count() or 4)
    log.info("CUDA not available — using CPU with %d threads", torch.get_num_threads())

# ── Segment size ──────────────────────────────────────────────────────────────
# Larger segments = fewer pipeline calls = less per-call overhead.
# On GPU with 4 GB VRAM, 2000 chars per segment is safe and fast.
# On CPU, keep smaller to avoid long blocking calls.
_MAX_SEGMENT_CHARS = 2000 if DEVICE == "cuda" else 800

# Number of parallel KPipeline workers.
# On GPU: 1 worker (GPU handles parallelism internally).
# On CPU: up to 2 workers to use multiple cores.
_MAX_WORKERS = 1 if DEVICE == "cuda" else 2

# Clear VRAM cache every N segments to prevent fragmentation on 4 GB cards
_VRAM_CLEAR_INTERVAL = 10


def _split_paragraphs(text: str, max_chars: int = _MAX_SEGMENT_CHARS) -> list[str]:
    """Split text into segments ≤ max_chars.

    Strategy:
    1. Split on blank lines → raw paragraphs
    2. Break any paragraph > max_chars on sentence boundaries
    3. PACK multiple short paragraphs into one segment up to max_chars
       (this prevents 691 tiny segments from a 182k-char text with many short paras)
    """
    # ── Step 1: raw paragraph split ──────────────────────────────────────────
    raw_paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    # ── Step 2: break oversized paragraphs on sentence boundaries ────────────
    atomic: list[str] = []
    for para in raw_paras:
        if len(para) <= max_chars:
            atomic.append(para)
        else:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= max_chars:
                    current = (current + " " + sent).strip() if current else sent
                else:
                    if current:
                        atomic.append(current)
                    # Hard-split sentences that are still too long
                    while len(sent) > max_chars:
                        atomic.append(sent[:max_chars])
                        sent = sent[max_chars:]
                    current = sent
            if current:
                atomic.append(current)

    # ── Step 3: pack atomic pieces into segments up to max_chars ─────────────
    segments: list[str] = []
    bucket = ""
    for piece in atomic:
        separator = "\n\n" if bucket else ""
        if len(bucket) + len(separator) + len(piece) <= max_chars:
            bucket = bucket + separator + piece
        else:
            if bucket:
                segments.append(bucket)
            bucket = piece
    if bucket:
        segments.append(bucket)

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
        """Run pipeline with inference_mode for maximum speed (no gradient tracking)."""
        chunks = []
        with torch.inference_mode():
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
                # Periodically clear VRAM cache to prevent fragmentation
                if DEVICE == "cuda" and (i + 1) % _VRAM_CLEAR_INTERVAL == 0:
                    torch.cuda.empty_cache()
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

        # Final VRAM cleanup
        if DEVICE == "cuda":
            torch.cuda.empty_cache()

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
            cc = f"{torch.cuda.get_device_properties(0).major}.{torch.cuda.get_device_properties(0).minor}"
            return f"🚀 {name} · {vram} GB · CUDA {cc}"
        cores = os.cpu_count() or 1
        return f"🖥️ CPU · {cores} threads"


def log_device_info():
    """Log GPU/CPU info. Call this AFTER logging.basicConfig() is configured."""
    if DEVICE == "cuda":
        log.info("=" * 70)
        log.info("🚀 GPU ACCELERATION ENABLED - MAXIMIZING GPU CAPABILITIES")
        log.info("=" * 70)
        log.info("GPU Device    : %s", gpu_name)
        log.info("Compute Cap.  : %s", compute_capability)
        log.info("Total VRAM    : %.1f GB", total_vram)
        log.info("Segment size  : %d chars (GPU optimized)", _MAX_SEGMENT_CHARS)
        log.info("cuDNN Bench   : ENABLED")
        log.info("Deterministic : DISABLED (fastest mode)")
        log.info("inference_mode: ENABLED")
        log.info("=" * 70)
    else:
        log.info("Device: CPU — %d threads", torch.get_num_threads())
        log.info("Segment size : %d chars", _MAX_SEGMENT_CHARS)
