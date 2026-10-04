"""CPU engine: Kokoro-82M on ONNX Runtime (no PyTorch).

Text processing is the same misaki G2P used by the PyTorch engine, so output
matches it (spectral match 0.998 in testing); only the network runs here.
"""
import logging
import re
import threading

import numpy as np

from core import hardware, model_store
from core.tts_common import EngineBase, GenerationCancelled

log = logging.getLogger(__name__)

MAX_PHONEMES = 510
# Sentences are packed into calls of up to 510 phonemes, like kokoro's own
# pipeline. Kokoro's pacing depends on chunk length (the voice table has a row
# per length), so smaller calls sounded slower (28.4 s vs 26.0 s in testing).
# Cancel stays fast by aborting the running call (RunOptions.terminate).
PACK_PHONEMES = MAX_PHONEMES
_SENTENCE = re.compile(r"(?<=[.!?।॥…])\s+")
_ESPEAK_CODES = {"h": "hi", "f": "fr-fr", "e": "es", "i": "it", "p": "pt-br"}


class OnnxEngine(EngineBase):
    name = "CPU"
    segment_chars = 800
    default_realtime_factor = 3.0

    def __init__(self, mode: str = "Maximum"):
        super().__init__()
        self._mode = mode
        self._session = None
        self._session_threads = None
        self._vocab = None
        self._g2p = {}
        self._lock = threading.Lock()

    # ── configuration ─────────────────────────────────────────────────────────
    def set_mode(self, mode: str):
        """Maximum / Balanced / Quiet; takes effect on the next generation."""
        self._mode = mode

    @property
    def mode(self) -> str:
        return self._mode

    def label(self) -> str:
        return f"CPU · {self._mode}"

    def threads(self) -> int:
        return hardware.threads_for_mode(self._mode)

    # ── model ─────────────────────────────────────────────────────────────────
    def _ensure_session(self):
        threads = self.threads()
        if self._session is not None and self._session_threads == threads:
            return self._session
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = threads        # 0 = ONNX Runtime default (fastest)
        opts.inter_op_num_threads = 1
        log.info("Loading ONNX model on CPU (%s, %s threads)", self._mode, threads or "auto")
        self._session = ort.InferenceSession(model_store.onnx_model_path(), opts,
                                             providers=["CPUExecutionProvider"])
        self._session_threads = threads
        if self._vocab is None:
            self._vocab = model_store.onnx_vocab()
        return self._session

    def release(self):
        with self._lock:
            if self._session is not None:
                log.info("Releasing ONNX model from memory")
            self._session = None
            self._session_threads = None

    # ── text → phonemes ───────────────────────────────────────────────────────
    def _get_g2p(self, lang):
        if lang not in self._g2p:
            from misaki import espeak
            if lang in ("a", "b"):
                from misaki import en
                try:
                    fallback = espeak.EspeakFallback(british=lang == "b")
                except Exception as exc:
                    log.warning("espeak fallback unavailable: %s", exc)
                    fallback = None
                self._g2p[lang] = en.G2P(trf=False, british=lang == "b", fallback=fallback, unk="")
            else:
                self._g2p[lang] = espeak.EspeakG2P(language=_ESPEAK_CODES[lang])
        return self._g2p[lang]

    def _phoneme_chunks(self, text, lang):
        g2p = self._get_g2p(lang)
        pieces = text.splitlines() if lang not in ("a", "b") else _SENTENCE.split(text)
        chunks, cur = [], ""
        for piece in pieces:
            if not piece.strip():
                continue
            ps = (g2p(piece.strip())[0] or "").strip()
            for part in self._split_long(ps):
                if cur and len(cur) + 1 + len(part) > PACK_PHONEMES:
                    chunks.append(cur)
                    cur = part
                else:
                    cur = f"{cur} {part}".strip()
        if cur:
            chunks.append(cur)
        return chunks

    @staticmethod
    def _split_long(ps):
        if len(ps) <= MAX_PHONEMES:
            return [ps] if ps else []
        out, cur = [], ""
        for word in ps.split(" "):
            while len(word) > MAX_PHONEMES:
                out.append(word[:MAX_PHONEMES])
                word = word[MAX_PHONEMES:]
            if cur and len(cur) + 1 + len(word) > MAX_PHONEMES:
                out.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        return out + ([cur] if cur else [])

    # ── synthesis ─────────────────────────────────────────────────────────────
    def _synth_segment(self, text, lang_code, style, speed, cancel_event):
        import onnxruntime as ort
        with self._lock:
            session = self._ensure_session()
            parts = []
            for ps in self._phoneme_chunks(text, lang_code):
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelled()
                ids = [self._vocab[c] for c in ps if c in self._vocab][:MAX_PHONEMES]
                if not ids:
                    continue
                run_opts = ort.RunOptions()
                done = threading.Event()
                watcher = None
                if cancel_event is not None:
                    def _watch():
                        while not done.is_set():
                            if cancel_event.wait(0.05):
                                run_opts.terminate = True      # abort the running call
                                return
                    watcher = threading.Thread(target=_watch, daemon=True)
                    watcher.start()
                try:
                    out = session.run(None, {
                        "input_ids": np.array([[0, *ids, 0]], dtype=np.int64),
                        "style": style[len(ids) - 1][None, :].astype(np.float32),
                        "speed": np.array([speed], dtype=np.float32),
                    }, run_opts)[0]
                except Exception:
                    if cancel_event is not None and cancel_event.is_set():
                        raise GenerationCancelled()
                    raise
                finally:
                    done.set()
                parts.append(out.reshape(-1).astype(np.float32))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)
