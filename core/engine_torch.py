"""GPU engine: Kokoro-82M on PyTorch + CUDA (optional GPU pack).

torch and kokoro are imported only when this engine is used, so the base app
never needs them. Voices come from the same voice files as the CPU engine.
"""
import logging
import threading

import numpy as np

from core import model_store
from core.tts_common import EngineBase, GenerationCancelled

log = logging.getLogger(__name__)

_LANGS_WITH_PIPELINE = ("a", "b", "h", "f", "e", "i", "p")


def chunk_chars_for_vram(memory_mb: int) -> int:
    """Measured peak: ~1.3 GB of GPU memory with 2,000-character chunks."""
    if memory_mb >= 8000:
        return 4000
    if memory_mb >= 4000:
        return 2000
    return 800


class TorchEngine(EngineBase):
    name = "GPU"
    default_realtime_factor = 30.0

    def __init__(self, gpu_name: str = "GPU", memory_mb: int = 4096):
        super().__init__()
        self._gpu_name = gpu_name
        self.segment_chars = chunk_chars_for_vram(memory_mb)
        self._model = None
        self._pipelines = {}
        self._lock = threading.Lock()

    def label(self) -> str:
        return f"GPU · {self._gpu_name}"

    # ── model ─────────────────────────────────────────────────────────────────
    def _ensure_model(self):
        if self._model is None:
            import torch
            from kokoro import KModel
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA is not available on this PC.")
            # benchmark=True re-tunes kernels for every new input length; real text
            # rarely repeats a length, so it measured ~7x real time instead of ~36x.
            torch.backends.cudnn.benchmark = False
            log.info("Loading PyTorch model on CUDA (%s)", self._gpu_name)
            cfg = f"{model_store.TORCH_DIR}/config.json"
            weights = f"{model_store.TORCH_DIR}/kokoro-v1_0.pth"
            self._model = KModel(repo_id=model_store.TORCH_REPO, config=cfg, model=weights).to("cuda").eval()
        return self._model

    def _pipeline(self, lang):
        if lang not in self._pipelines:
            from kokoro import KPipeline
            self._pipelines[lang] = KPipeline(lang_code=lang, repo_id=model_store.TORCH_REPO,
                                              model=self._ensure_model(), device="cuda")
        return self._pipelines[lang]

    def release(self):
        with self._lock:
            if self._model is None:
                return
            log.info("Releasing PyTorch model and GPU memory")
            self._pipelines.clear()
            self._model = None
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass

    # ── synthesis ─────────────────────────────────────────────────────────────
    def _synth_segment(self, text, lang_code, style, speed, cancel_event):
        import torch
        with self._lock:
            pipeline = self._pipeline(lang_code)
            voice = torch.from_numpy(np.ascontiguousarray(style)).reshape(510, 1, 256).float()
            parts = []
            with torch.inference_mode():
                for _gs, _ps, audio in pipeline(text, voice=voice, speed=speed):
                    if cancel_event is not None and cancel_event.is_set():
                        raise GenerationCancelled()
                    if audio is None:
                        continue
                    if hasattr(audio, "detach"):
                        audio = audio.detach().cpu().numpy()
                    parts.append(np.asarray(audio, dtype=np.float32))
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)
