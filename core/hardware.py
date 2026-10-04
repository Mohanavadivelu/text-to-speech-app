"""What the PC can do: CPU threads, battery, NVIDIA GPU, process priority."""
import ctypes
import logging
import os
import subprocess
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

# CUDA 12.x (PyTorch cu121) runs on NVIDIA drivers from this version up.
MIN_CUDA12_DRIVER = (527, 41)
# Measured: PyTorch peaks at ~1.3 GB of GPU memory with 2,000-character chunks.
MIN_GPU_MEMORY_MB = 2048

_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0


def logical_cpus() -> int:
    return os.cpu_count() or 4


def threads_for_mode(mode: str) -> int:
    """ONNX Runtime intra-op threads for a performance mode (0 = its own default).

    Measured on a 20-thread i7-12700H: the default was fastest (3.8–4.8x real
    time) — every hand-picked count was slower; 4 threads kept ~75% of the speed.
    """
    n = logical_cpus()
    if mode == "Balanced":
        return max(2, n // 4)
    if mode == "Quiet":
        return max(1, n // 8)
    return 0


def on_battery() -> bool:
    if not sys.platform.startswith("win"):
        return False

    class SPS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    s = SPS()
    try:
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return s.ACLineStatus == 0
    except Exception:
        pass
    return False


def set_background_priority(enabled: bool):
    """Run below normal priority while generating so the PC stays responsive.

    Lower priority costs nothing when the CPU is otherwise idle.
    """
    if not sys.platform.startswith("win"):
        return
    BELOW_NORMAL, NORMAL = 0x4000, 0x20
    try:
        k32 = ctypes.windll.kernel32
        k32.SetPriorityClass(k32.GetCurrentProcess(), BELOW_NORMAL if enabled else NORMAL)
    except Exception as exc:
        log.debug("Could not change priority: %s", exc)


@dataclass
class NvidiaGpu:
    name: str
    driver: str
    memory_mb: int

    @property
    def driver_ok(self) -> bool:
        try:
            parts = tuple(int(p) for p in self.driver.split(".")[:2])
        except ValueError:
            return False
        return parts >= MIN_CUDA12_DRIVER

    @property
    def memory_ok(self) -> bool:
        return self.memory_mb >= MIN_GPU_MEMORY_MB

    @property
    def eligible(self) -> bool:
        return self.driver_ok and self.memory_ok

    def problem(self) -> str:
        if not self.driver_ok:
            v = ".".join(map(str, MIN_CUDA12_DRIVER))
            return f"NVIDIA driver {self.driver} is too old; version {v} or newer is needed."
        if not self.memory_ok:
            return f"{self.memory_mb} MB of GPU memory; at least {MIN_GPU_MEMORY_MB} MB is needed."
        return ""


_gpu_cache = []


def nvidia_gpu():
    """Return the first NVIDIA GPU (via nvidia-smi, installed with the driver) or None."""
    if _gpu_cache:
        return _gpu_cache[0]
    gpu = None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW,
        ).stdout.strip().splitlines()
        if out:
            name, driver, mem = [p.strip() for p in out[0].split(",")[:3]]
            gpu = NvidiaGpu(name=name, driver=driver, memory_mb=int(float(mem)))
    except (OSError, ValueError, subprocess.SubprocessError):
        gpu = None
    _gpu_cache.append(gpu)
    return gpu


def short_gpu_name(name: str) -> str:
    return name.replace("NVIDIA ", "").replace("GeForce ", "").replace(" Laptop GPU", "")
