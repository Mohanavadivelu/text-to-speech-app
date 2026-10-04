"""Download and locate the voice model files (pinned versions, verified).

CPU engine (ONNX Runtime):  models/onnx/   model.onnx, tokenizer.json, voices/*.bin
GPU engine (PyTorch):       models/pytorch/ kokoro-v1_0.pth, config.json
"""
import hashlib
import json
import logging
import os
import threading
import urllib.request
from dataclasses import dataclass

from core import paths
from core.voices import VOICES

log = logging.getLogger(__name__)

ONNX_REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
ONNX_REVISION = "1939ad2a8e416c0acfeecc08a694d14ef25f2231"
TORCH_REPO = "hexgrad/Kokoro-82M"
TORCH_REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"

ONNX_DIR = os.path.join(paths.MODELS_DIR, "onnx")
TORCH_DIR = os.path.join(paths.MODELS_DIR, "pytorch")
VOICE_BYTES = 510 * 256 * 4


class DownloadCancelled(Exception):
    pass


@dataclass
class RemoteFile:
    url: str
    dest: str
    size: int = 0          # 0 = unknown
    sha256: str = ""       # "" = not checked


def _hf(repo, rev, name):
    return f"https://huggingface.co/{repo}/resolve/{rev}/{name}"


def onnx_files() -> list[RemoteFile]:
    files = [
        RemoteFile(_hf(ONNX_REPO, ONNX_REVISION, "onnx/model.onnx"), os.path.join(ONNX_DIR, "model.onnx"),
                   325532232, "8fbea51ea711f2af382e88c833d9e288c6dc82ce5e98421ea61c058ce21a34cb"),
        RemoteFile(_hf(ONNX_REPO, ONNX_REVISION, "tokenizer.json"), os.path.join(ONNX_DIR, "tokenizer.json")),
    ]
    for vid in sorted({v for voices in VOICES.values() for v, _ in voices}):
        files.append(RemoteFile(_hf(ONNX_REPO, ONNX_REVISION, f"voices/{vid}.bin"),
                                os.path.join(ONNX_DIR, "voices", f"{vid}.bin"), VOICE_BYTES))
    return files


def torch_files() -> list[RemoteFile]:
    return [
        RemoteFile(_hf(TORCH_REPO, TORCH_REVISION, "kokoro-v1_0.pth"), os.path.join(TORCH_DIR, "kokoro-v1_0.pth"),
                   327212226, "496dba118d1a58f5f3db2efc88dbdc216e0483fc89fe6e47ee1f2c53f18ad1e4"),
        RemoteFile(_hf(TORCH_REPO, TORCH_REVISION, "config.json"), os.path.join(TORCH_DIR, "config.json")),
    ]


def _complete(f: RemoteFile) -> bool:
    return os.path.isfile(f.dest) and (not f.size or os.path.getsize(f.dest) == f.size)


def missing(files) -> list[RemoteFile]:
    return [f for f in files if not _complete(f)]


def onnx_ready() -> bool:
    return not missing(onnx_files())


def total_bytes(files) -> int:
    return sum(f.size for f in files)


def _sha256(path, cancel=None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(4 << 20), b""):
            if cancel is not None and cancel.is_set():
                raise DownloadCancelled()
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: str, size: int = 0, sha256: str = "", progress=None,
             cancel: threading.Event = None, timeout: int = 30):
    """Download *url* to *dest* with resume (.part file) and verification.

    progress(bytes_this_file) is called as data arrives. Raises DownloadCancelled
    or OSError/ValueError with a readable message.
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    if size and have > size:
        os.remove(part)
        have = 0
    if not (size and have == size):
        req = urllib.request.Request(url, headers={"User-Agent": "KokoroTTS"})
        if have:
            req.add_header("Range", f"bytes={have}-")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if have and resp.status != 206:     # server ignored Range: start over
                have = 0
            mode = "ab" if have else "wb"
            with open(part, mode) as out:
                if progress:
                    progress(have)
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled()
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    have += len(chunk)
                    if progress:
                        progress(have)
    if size and os.path.getsize(part) != size:
        raise ValueError(f"Download of {os.path.basename(dest)} is incomplete; try again.")
    if sha256 and _sha256(part, cancel) != sha256:
        os.remove(part)
        raise ValueError(f"{os.path.basename(dest)} failed its integrity check; try again.")
    os.replace(part, dest)


def fetch_all(files, progress=None, cancel=None):
    """Download every missing file. progress(done_bytes, total_bytes, label)."""
    todo = missing(files)
    total = sum(f.size for f in todo) or 1
    done_before = 0
    for f in todo:
        label = os.path.basename(f.dest)
        cb = (lambda got, base=done_before, lbl=label: progress(base + got, total, lbl)) if progress else None
        download(f.url, f.dest, f.size, f.sha256, cb, cancel)
        done_before += f.size or 0
    if progress:
        progress(total, total, "done")


# ── loading helpers ─────────────────────────────────────────────────────────

def onnx_model_path() -> str:
    return os.path.join(ONNX_DIR, "model.onnx")


def onnx_vocab() -> dict:
    with open(os.path.join(ONNX_DIR, "tokenizer.json"), encoding="utf-8") as fh:
        return json.load(fh)["model"]["vocab"]


def voice_array(voice_id: str):
    """Voice style table, shape (510, 256) float32 — shared by both engines."""
    import numpy as np
    path = os.path.join(ONNX_DIR, "voices", f"{voice_id}.bin")
    return np.fromfile(path, dtype=np.float32).reshape(510, 256)
