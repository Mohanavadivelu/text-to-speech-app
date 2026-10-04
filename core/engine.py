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


def _pitch_factor(semitones: float) -> float:
    return 2.0 ** (semitones / 12.0)


def _pitch_shift(audio: np.ndarray, factor: float) -> np.ndarray:
    """Resample *audio* so it plays *factor* times higher (and shorter).

    Combined with generating speech at speed / factor, the net effect is a
    pitch change with the original duration preserved.
    """
    if factor == 1.0 or len(audio) < 2:
        return audio
    n_out = max(1, int(round(len(audio) / factor)))
    src = np.linspace(0, len(audio) - 1, n_out, dtype=np.float64)
    return np.interp(src, np.arange(len(audio)), audio).astype(np.float32)


# Model repo on Hugging Face. v1.0 covers every language this app offers;
# Kokoro-82M-v1.1-zh is a Chinese-focused variant and is not used here.
REPO_ID = "hexgrad/Kokoro-82M"

# English (a/b) uses misaki's own chunker. Every other language goes through
# espeak, where kokoro only splits on . ! ? — so Hindi text ending in "।"
# reached the model as one chunk and was cut at 510 phonemes. We pre-break
# those languages into short lines, which kokoro treats as separate chunks.
_ESPEAK_LINE_CHARS = 200
_SENTENCE_END = re.compile(r"(?<=[.!?।॥…])\s+")
_CLAUSE_END = re.compile(r"(?<=[,;:—])\s+")


def _break_lines(text: str, max_chars: int = _ESPEAK_LINE_CHARS) -> str:
    """Return *text* with newlines so no line exceeds *max_chars*."""
    lines: list[str] = []

    def _pack(parts, splitter):
        cur = ""
        for part in parts:
            if len(part) > max_chars:
                if cur:
                    lines.append(cur)
                    cur = ""
                splitter(part)
            elif not cur:
                cur = part
            elif len(cur) + 1 + len(part) <= max_chars:
                cur = f"{cur} {part}"
            else:
                lines.append(cur)
                cur = part
        if cur:
            lines.append(cur)

    def _by_words(part):
        _pack(part.split(), lambda w: lines.extend(
            w[i:i + max_chars] for i in range(0, len(w), max_chars)))

    def _by_clause(part):
        _pack(_CLAUSE_END.split(part), _by_words)

    for para in text.splitlines():
        para = para.strip()
        if para:
            _pack(_SENTENCE_END.split(para), _by_clause)
    return "\n".join(lines)


class TTSEngine:
    def __init__(self):
        self._model = None
        self._model_lock = threading.Lock()
        self._pipelines: dict = {}       # lang_code -> KPipeline (shares self._model)
        self._aux_pipelines: dict = {}   # lang_code -> second KPipeline for CPU workers
        self._lock = threading.Lock()      # serialises the main pipeline
        self._aux_lock = threading.Lock()  # serialises the aux pipeline

    # ── Model & pipeline management ───────────────────────────────────────────

    def _get_model(self, on_status=None):
        """Load the Kokoro model once; every language pipeline reuses it."""
        with self._model_lock:
            if self._model is None:
                from kokoro import KModel
                log.info("Loading %s on %s", REPO_ID, DEVICE)
                if on_status:
                    on_status(f"Loading model on {DEVICE.upper()}…")
                self._model = KModel(repo_id=REPO_ID).to(DEVICE).eval()
                log.info("Model ready on %s", DEVICE)
            return self._model

    def _make_pipeline(self, lang_code: str, on_status=None):
        from kokoro import KPipeline
        model = self._get_model(on_status)
        return KPipeline(lang_code=lang_code, repo_id=REPO_ID, model=model, device=DEVICE)

    def _get_pipeline(self, lang_code: str, on_status=None):
        if lang_code not in self._pipelines:
            log.info("Creating %s pipeline (shared model)", lang_code)
            self._pipelines[lang_code] = self._make_pipeline(lang_code, on_status)
        return self._pipelines[lang_code]

    def _get_aux_pipeline(self, lang_code: str):
        with self._model_lock:
            pipeline = self._aux_pipelines.get(lang_code)
        if pipeline is None:
            pipeline = self._make_pipeline(lang_code)
            with self._model_lock:
                pipeline = self._aux_pipelines.setdefault(lang_code, pipeline)
        return pipeline

    # ── Voices ────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_voice(pipeline, voice_id: str, blend_voice=None, blend_ratio: float = 0.5):
        """Return a voice id, or a blended voice tensor when *blend_voice* is set.

        *blend_ratio* is the share of *blend_voice* (0.0–1.0).
        """
        if not blend_voice or blend_voice == voice_id or blend_ratio <= 0:
            return voice_id
        ratio = min(1.0, float(blend_ratio))
        a = pipeline.load_single_voice(voice_id)
        b = pipeline.load_single_voice(blend_voice)
        return ((1.0 - ratio) * a + ratio * b).float()

    @staticmethod
    def prefetch_voices(voice_ids):
        """Download voice files in the background so later previews work offline."""
        def _worker():
            from huggingface_hub import hf_hub_download
            for vid in voice_ids:
                try:
                    hf_hub_download(repo_id=REPO_ID, filename=f"voices/{vid}.pt")
                except Exception as exc:  # offline or rate-limited: try again next time
                    log.debug("Voice prefetch skipped for %s: %s", vid, exc)
                    return
            log.info("Prefetched %d voice(s)", len(voice_ids))
        threading.Thread(target=_worker, daemon=True).start()

    # ── Audio helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _run_pipeline(pipeline, text: str, voice, speed: float,
                      pitch: float = 0.0) -> np.ndarray:
        """Run pipeline with inference_mode for maximum speed (no gradient tracking).

        *pitch* is in semitones. Speech is generated slower or faster by the
        pitch factor, then resampled back, so the chosen speed is preserved.
        """
        factor = _pitch_factor(pitch)
        chunks = []
        with torch.inference_mode():
            for _gs, _ps, audio in pipeline(text, voice=voice, speed=speed / factor):
                if hasattr(audio, "numpy"):
                    audio = audio.detach().cpu().numpy()
                chunks.append(np.asarray(audio, dtype=np.float32))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        return _pitch_shift(audio, factor)

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, text: str, lang_code: str, voice_id: str, speed: float,
                 pitch: float = 0.0, on_status=None, on_progress=None,
                 on_chunk=None, blend_voice=None, blend_ratio: float = 0.5):
        """Generate audio for *text*.

        Returns (np.ndarray[float32], sample_rate).

        Callbacks (all optional, called from the worker thread):
          on_status(msg: str)          — human-readable status string
          on_progress(pct: int)        — 0-99 during generation, 100 when done
          on_chunk(audio: np.ndarray)  — called with each completed segment

        blend_voice / blend_ratio mix a second voice into *voice_id*.
        """
        with self._lock:
            pipeline = self._get_pipeline(lang_code, on_status=on_status)
            voice = self._resolve_voice(pipeline, voice_id, blend_voice, blend_ratio)

        segments = _split_paragraphs(text)
        if lang_code not in ("a", "b"):
            segments = [_break_lines(seg) for seg in segments]
        total_segs = len(segments)
        log.info("Generating %d segment(s) for %d chars, voice=%s blend=%s@%.2f speed=%s "
                 "pitch=%+.1f device=%s", total_segs, len(text), voice_id, blend_voice,
                 blend_ratio, speed, pitch, DEVICE)

        if on_status:
            on_status(f"Generating… 0 / {total_segs} segments [{DEVICE.upper()}]")

        all_chunks: list = [None] * total_segs

        if total_segs == 1 or _MAX_WORKERS <= 1:
            # ── Single-threaded path (GPU or single-core CPU) ─────────────────
            for i, seg in enumerate(segments):
                with self._lock:
                    audio = self._run_pipeline(pipeline, seg, voice, speed, pitch)
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
                        audio = self._run_pipeline(pipeline, seg, voice, speed, pitch)
                else:
                    aux = self._get_aux_pipeline(lang_code)
                    with self._aux_lock:
                        audio = self._run_pipeline(aux, seg, voice, speed, pitch)
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
