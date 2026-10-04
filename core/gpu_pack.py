"""Optional GPU pack: PyTorch + CUDA + kokoro, installed from inside the app.

Nothing is hosted by us. core/gpu_manifest.json (generated at build time by
scripts/make_gpu_manifest.py) pins every wheel the pack needs — exact version,
official download URL (download.pytorch.org / PyPI) and SHA-256 — matched to
the app's own Python version and to the libraries already bundled in the app.
Installing = download, verify, unzip into engines/pytorch-cuda/site-packages.
"""
import json
import logging
import os
import shutil
import sys
import threading
import zipfile

from core import hardware, model_store, paths

log = logging.getLogger(__name__)

PACK_DIR = os.path.join(paths.ENGINES_DIR, "pytorch-cuda")
SITE_DIR = os.path.join(PACK_DIR, "site-packages")
MARKER = os.path.join(PACK_DIR, "pack.json")
DOWNLOADS = os.path.join(paths.ENGINES_DIR, "_downloads")


def _manifest_path():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "core", "gpu_manifest.json")


_manifest_cache = []


def manifest():
    """The pinned wheel list, or None if this build has no manifest."""
    if not _manifest_cache:
        try:
            with open(_manifest_path(), encoding="utf-8") as fh:
                _manifest_cache.append(json.load(fh))
        except (OSError, ValueError) as exc:
            log.warning("No GPU pack manifest: %s", exc)
            _manifest_cache.append(None)
    return _manifest_cache[0]


def python_tag() -> str:
    return f"cp{sys.version_info.major}{sys.version_info.minor}"


def download_bytes() -> int:
    m = manifest() or {}
    return sum(w.get("size", 0) for w in m.get("wheels", [])) + model_store.total_bytes(model_store.torch_files())


def installed_version():
    try:
        with open(MARKER, encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except (OSError, ValueError):
        return None


def is_installed() -> bool:
    m = manifest()
    return bool(m) and installed_version() == m.get("version") and os.path.isdir(SITE_DIR)


def is_outdated() -> bool:
    v = installed_version()
    return v is not None and not is_installed()


def eligibility():
    """(ok, gpu, reason). The pack is only offered when ok is True."""
    if not sys.platform.startswith("win"):
        return False, None, "The GPU pack is available on Windows only."
    m = manifest()
    if not m:
        return False, None, "This build has no GPU pack list."
    if m.get("python") != python_tag():
        return False, None, f"GPU pack list is for {m.get('python')}, app runs {python_tag()}."
    gpu = hardware.nvidia_gpu()
    if gpu is None:
        return False, None, "No NVIDIA GPU found."
    if not gpu.eligible:
        return False, gpu, gpu.problem()
    return True, gpu, ""


_activated = []


def activate() -> bool:
    """Make the installed pack importable (before torch is imported). Safe to repeat."""
    if _activated and _activated[0]:
        return True
    _activated.clear()
    ok = is_installed()
    if ok:
        # Appended: libraries bundled with the app always take precedence.
        sys.path.append(SITE_DIR)
        torch_lib = os.path.join(SITE_DIR, "torch", "lib")
        if hasattr(os, "add_dll_directory") and os.path.isdir(torch_lib):
            os.add_dll_directory(torch_lib)
        log.info("GPU pack %s active (%s)", installed_version(), SITE_DIR)
    _activated.append(ok)
    return ok


# ── install / remove ─────────────────────────────────────────────────────────

def install(progress=None, cancel: threading.Event = None):
    """Download and install the pack. progress(done_bytes, total_bytes, label)."""
    m = manifest()
    if not m:
        raise RuntimeError("This build has no GPU pack list.")
    wheels = m["wheels"]
    total = download_bytes() or 1
    done = 0
    os.makedirs(DOWNLOADS, exist_ok=True)
    staging = PACK_DIR + ".new"
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
    site = os.path.join(staging, "site-packages")
    os.makedirs(site)

    for w in wheels:
        dest = os.path.join(DOWNLOADS, w["filename"])
        label = f"{w['name']} {w['version']}"
        if not (os.path.isfile(dest) and (not w.get("size") or os.path.getsize(dest) == w["size"])):
            model_store.download(w["url"], dest, w.get("size", 0), w.get("sha256", ""),
                                 (lambda got, base=done, lbl=label: progress and progress(base + got, total, lbl)),
                                 cancel)
        done += w.get("size", 0)
        if progress:
            progress(done, total, f"Unpacking {label}")
        with zipfile.ZipFile(dest) as zf:
            zf.extractall(site)
        if cancel is not None and cancel.is_set():
            raise model_store.DownloadCancelled()

    files = model_store.torch_files()
    model_store.fetch_all(files, (lambda got, tot, lbl: progress and progress(done + got, total, lbl)), cancel)

    with open(os.path.join(staging, "pack.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": m["version"], "python": m["python"], "torch": m.get("torch")}, fh, indent=2)
    if os.path.isdir(PACK_DIR):
        shutil.rmtree(PACK_DIR)
    os.replace(staging, PACK_DIR)
    shutil.rmtree(DOWNLOADS, ignore_errors=True)
    log.info("GPU pack %s installed", m["version"])
    if progress:
        progress(total, total, "done")


REMOVE_FLAG = os.path.join(paths.ENGINES_DIR, "remove_pending")


def removal_needs_restart() -> bool:
    """Windows can't delete DLLs that are loaded; torch stays loaded until exit."""
    return "torch" in sys.modules


def request_removal():
    os.makedirs(paths.ENGINES_DIR, exist_ok=True)
    open(REMOVE_FLAG, "w").close()


def removal_pending() -> bool:
    return os.path.exists(REMOVE_FLAG)


def process_pending_removal() -> bool:
    """Call at startup, before activate(). Returns True if the pack was removed."""
    if not removal_pending():
        return False
    remove()
    try:
        os.remove(REMOVE_FLAG)
    except OSError:
        pass
    return True


def remove():
    for d in (PACK_DIR, PACK_DIR + ".new", DOWNLOADS, model_store.TORCH_DIR):
        shutil.rmtree(d, ignore_errors=True)
    log.info("GPU pack removed")


def installed_size_mb() -> int:
    total = 0
    for root, _dirs, files in os.walk(PACK_DIR):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total // (1 << 20)


# ── self-test ────────────────────────────────────────────────────────────────

def _spectrum(x):
    import numpy as np
    n = 1024
    if len(x) < n:
        return np.zeros(n // 2 + 1)
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::256] * np.hanning(n)
    return np.log1p(np.abs(np.fft.rfft(frames, axis=1))).mean(axis=0)


def self_test(gpu_engine, cpu_engine) -> tuple:
    """Generate the same phrase on GPU and CPU; (passed, message)."""
    import numpy as np
    phrase = "This is a quick test of the graphics card voice engine."
    try:
        g, _ = gpu_engine.generate(phrase, "a", "af_heart", 1.0)
        c, _ = cpu_engine.generate(phrase, "a", "af_heart", 1.0)
    except Exception as exc:
        log.exception("GPU self-test failed")
        return False, f"GPU test failed: {exc}"
    match = float(np.corrcoef(_spectrum(g), _spectrum(c))[0, 1])
    log.info("GPU self-test spectral match %.4f", match)
    if not np.isfinite(match) or match < 0.98:
        return False, f"GPU audio did not match the CPU engine (match {match:.3f})."
    return True, f"GPU engine verified (match {match:.3f})."
