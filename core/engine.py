"""Engine selection: CPU (ONNX Runtime, built in) or GPU (PyTorch pack, optional).

The rest of the app only talks to TTSEngine. It picks the engine from the
user's settings (Auto / GPU / CPU), applies the CPU performance mode, lowers
process priority while generating, and falls back to the CPU if the GPU fails.
"""
import logging
import os

import soundfile as sf
import numpy as np

from core import gpu_pack, hardware, model_store
from core.engine_onnx import OnnxEngine
from core.tts_common import SAMPLE_RATE, GenerationCancelled  # noqa: F401 (re-exported)

log = logging.getLogger(__name__)

ENGINE_CHOICES = ("Auto", "GPU", "CPU")
PERF_MODES = ("Maximum", "Balanced", "Quiet")


class TTSEngine:
    def __init__(self):
        self.cpu = OnnxEngine()
        self._gpu = None
        self.choice = "Auto"
        self.perf_mode = "Maximum"
        self.quiet_on_battery = True
        self.gpu_verified = False
        self._last_fallback = ""

    # ── configuration ─────────────────────────────────────────────────────────
    def configure(self, choice=None, perf_mode=None, quiet_on_battery=None, gpu_verified=None):
        if choice in ENGINE_CHOICES:
            self.choice = choice
        if perf_mode in PERF_MODES:
            self.perf_mode = perf_mode
        if quiet_on_battery is not None:
            self.quiet_on_battery = bool(quiet_on_battery)
        if gpu_verified is not None:
            self.gpu_verified = bool(gpu_verified)

    def effective_perf_mode(self) -> str:
        if self.quiet_on_battery and hardware.on_battery():
            return "Quiet"
        return self.perf_mode

    @staticmethod
    def gpu_pack_installed() -> bool:
        return gpu_pack.is_installed()

    def gpu_engine(self):
        """The PyTorch engine, if the GPU pack is installed and active."""
        if self._gpu is None and gpu_pack.activate():
            gpu = hardware.nvidia_gpu()
            from core.engine_torch import TorchEngine
            self._gpu = TorchEngine(hardware.short_gpu_name(gpu.name) if gpu else "GPU",
                                    gpu.memory_mb if gpu else 4096)
        return self._gpu

    def gpu_usable(self) -> bool:
        return self.gpu_verified and self.gpu_pack_installed() and model_store.missing(model_store.torch_files()) == []

    def active(self):
        if self.choice in ("Auto", "GPU") and self.gpu_usable():
            gpu = self.gpu_engine()
            if gpu is not None:
                return gpu
        self.cpu.set_mode(self.effective_perf_mode())
        return self.cpu

    def device_label(self) -> str:
        return self.active().label()

    @property
    def realtime_factor(self):
        return self.active().realtime_factor

    def estimate_generation_seconds(self, audio_seconds: float) -> float:
        return self.active().estimate_generation_seconds(audio_seconds)

    @staticmethod
    def model_ready() -> bool:
        return model_store.onnx_ready()

    # ── generation ────────────────────────────────────────────────────────────
    def generate(self, text, lang_code, voice_id, speed, pitch=0.0, on_status=None,
                 on_progress=None, on_chunk=None, blend_voice=None, blend_ratio=0.5,
                 cancel_event=None):
        engine = self.active()
        kwargs = dict(pitch=pitch, on_status=on_status, on_progress=on_progress, on_chunk=on_chunk,
                      blend_voice=blend_voice, blend_ratio=blend_ratio, cancel_event=cancel_event)
        background = engine is self.cpu and self.cpu.mode == "Maximum"
        if background:
            hardware.set_background_priority(True)
        try:
            return engine.generate(text, lang_code, voice_id, speed, **kwargs)
        except GenerationCancelled:
            raise
        except Exception as exc:
            if engine is self.cpu:
                raise
            log.exception("GPU generation failed; falling back to CPU")
            self._last_fallback = str(exc)
            if on_status:
                on_status("GPU failed — continuing on the CPU…")
            self.cpu.set_mode(self.effective_perf_mode())
            return self.cpu.generate(text, lang_code, voice_id, speed, **kwargs)
        finally:
            if background:
                hardware.set_background_priority(False)

    def take_fallback_notice(self) -> str:
        msg, self._last_fallback = self._last_fallback, ""
        return msg

    def release(self):
        """Free model memory (both engines); they reload on the next generation."""
        self.cpu.release()
        if self._gpu is not None:
            self._gpu.release()

    @staticmethod
    def save(audio, sample_rate: int, path: str):
        audio = np.asarray(audio, dtype=np.float32)
        sf.write(path, audio, sample_rate)
        log.info("Saved audio → %s  (%.2fs)", path, len(audio) / sample_rate)

    def device_info(self) -> str:
        return f"{self.device_label()}"


def log_device_info():
    gpu = hardware.nvidia_gpu()
    log.info("CPU: %d logical processors", hardware.logical_cpus())
    if gpu:
        log.info("NVIDIA GPU: %s · driver %s · %d MB", gpu.name, gpu.driver, gpu.memory_mb)
    log.info("GPU pack: %s", "installed" if gpu_pack.is_installed() else
             ("outdated" if gpu_pack.is_outdated() else "not installed"))
    log.info("Voice model: %s", "ready" if model_store.onnx_ready() else "not downloaded yet")
