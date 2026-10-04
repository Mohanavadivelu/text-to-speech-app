"""Code shared by the ONNX (CPU) and PyTorch (GPU) engines."""
import re

import numpy as np

SAMPLE_RATE = 24000


class GenerationCancelled(Exception):
    """Raised inside generate() when its cancel_event is set."""


def split_paragraphs(text: str, max_chars: int = 800) -> list[str]:
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


def pitch_factor(semitones: float) -> float:
    return 2.0 ** (semitones / 12.0)


def pitch_shift(audio: np.ndarray, factor: float) -> np.ndarray:
    """Resample *audio* so it plays *factor* times higher (and shorter).

    Combined with generating speech at speed / factor, the net effect is a
    pitch change with the original duration preserved.
    """
    if factor == 1.0 or len(audio) < 2:
        return audio
    n_out = max(1, int(round(len(audio) / factor)))
    src = np.linspace(0, len(audio) - 1, n_out, dtype=np.float64)
    return np.interp(src, np.arange(len(audio)), audio).astype(np.float32)

# English (a/b) uses misaki's own chunker. Every other language goes through
# espeak, where kokoro only splits on . ! ? — so Hindi text ending in "।"
# reached the model as one chunk and was cut at 510 phonemes. We pre-break
# those languages into short lines, which kokoro treats as separate chunks.
_ESPEAK_LINE_CHARS = 200
_SENTENCE_END = re.compile(r"(?<=[.!?।॥…])\s+")
_CLAUSE_END = re.compile(r"(?<=[,;:—])\s+")


def break_lines(text: str, max_chars: int = _ESPEAK_LINE_CHARS) -> str:
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


# ── Shared generation loop ───────────────────────────────────────────────────

import logging as _logging
import time as _time

_log = _logging.getLogger(__name__)


class EngineBase:
    """Segments text, reports progress, handles cancel, pitch and speed tracking.

    Subclasses implement _synth_segment() and describe themselves via
    name/label; voice tables come from model_store.voice_array().
    """

    name = "engine"
    segment_chars = 800
    default_realtime_factor = 2.0

    def __init__(self):
        self.realtime_factor = None   # measured audio-seconds per second of work

    # subclasses ──────────────────────────────────────────────────────────────
    def label(self) -> str:
        return self.name

    def _synth_segment(self, text, lang_code, style, speed, cancel_event):
        raise NotImplementedError

    def release(self):
        """Free the model from memory (it reloads on the next generation)."""

    # shared ──────────────────────────────────────────────────────────────────
    @staticmethod
    def voice_style(voice_id, blend_voice=None, blend_ratio=0.5):
        from core.model_store import voice_array
        base = voice_array(voice_id)
        if not blend_voice or blend_voice == voice_id or blend_ratio <= 0:
            return base
        ratio = min(1.0, float(blend_ratio))
        return ((1.0 - ratio) * base + ratio * voice_array(blend_voice)).astype(np.float32)

    def estimate_generation_seconds(self, audio_seconds: float) -> float:
        return audio_seconds / (self.realtime_factor or self.default_realtime_factor)

    def generate(self, text, lang_code, voice_id, speed, pitch=0.0, on_status=None,
                 on_progress=None, on_chunk=None, blend_voice=None, blend_ratio=0.5,
                 cancel_event=None):
        """Return (audio float32, SAMPLE_RATE). Raises GenerationCancelled."""
        def check():
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelled()

        started = _time.perf_counter()
        check()
        style = self.voice_style(voice_id, blend_voice, blend_ratio)
        factor = pitch_factor(pitch)
        segments = split_paragraphs(text, self.segment_chars)
        if lang_code not in ("a", "b"):
            segments = [break_lines(s) for s in segments]
        total = len(segments)
        _log.info("[%s] %d segment(s), %d chars, voice=%s blend=%s@%.2f speed=%s pitch=%+.1f",
                  self.name, total, len(text), voice_id, blend_voice, blend_ratio, speed, pitch)
        if on_status:
            on_status(f"Generating… 0 / {total} [{self.label()}]")
        parts = []
        for i, seg in enumerate(segments):
            check()
            audio = self._synth_segment(seg, lang_code, style, speed / factor, cancel_event)
            audio = pitch_shift(audio, factor)
            if len(audio):
                parts.append(audio)
                if on_chunk:
                    on_chunk(audio)
            if on_progress:
                on_progress(min(99, int((i + 1) / total * 100)))
            if on_status:
                on_status(f"Generating… {i + 1} / {total} [{self.label()}]")
        if not parts:
            raise RuntimeError("The engine produced no audio for this text.")
        full = np.concatenate(parts) if len(parts) > 1 else parts[0]
        secs, elapsed = len(full) / SAMPLE_RATE, _time.perf_counter() - started
        if elapsed > 0.5 and secs > 1.0:
            rtf = secs / elapsed
            self.realtime_factor = rtf if self.realtime_factor is None else \
                0.7 * self.realtime_factor + 0.3 * rtf
        if on_progress:
            on_progress(100)
        _log.info("[%s] %.2fs of audio in %.2fs (%.1fx real time)", self.name, secs, elapsed,
                  secs / max(elapsed, 1e-6))
        return full, SAMPLE_RATE
