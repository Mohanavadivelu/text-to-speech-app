"""Generate core/gpu_manifest.json: the pinned wheel list for the GPU pack.

Run with the app's (torch-free) venv Python:
    venv\\Scripts\\python scripts\\make_gpu_manifest.py

pip resolves PyTorch (CUDA 12.1) + kokoro *on top of the libraries already in
this venv* without installing anything, so the list holds only what the app
doesn't already bundle, in versions compatible with it. Each wheel gets its
official URL, SHA-256 and size.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "core", "gpu_manifest.json")
TORCH = "2.5.1"
KOKORO = "0.9.4"
TORCH_INDEX = "https://download.pytorch.org/whl/cu121"
# kokoro 0.9.4 targets transformers 4.x; transformers 5 is a breaking release.
EXTRA_PINS = ["transformers>=4.44,<5"]
PACK_VERSION = f"torch{TORCH}-cu121-kokoro{KOKORO}-1"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.json")
        cmd = [sys.executable, "-m", "pip", "install", "--dry-run", "--quiet", "--report", report,
               "--only-binary=:all:", "--index-url", TORCH_INDEX, "--extra-index-url", "https://pypi.org/simple",
               f"torch=={TORCH}+cu121", f"kokoro=={KOKORO}", *EXTRA_PINS]
        print("Resolving:", " ".join(cmd[4:]))
        subprocess.run(cmd, check=True)
        data = json.load(open(report, encoding="utf-8"))

    wheels = []
    for item in data["install"]:
        info = item["download_info"]
        url = info["url"]
        sha = info.get("archive_info", {}).get("hashes", {}).get("sha256", "")
        if not sha:
            sha = info.get("archive_info", {}).get("hash", "").replace("sha256=", "")
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "KokoroTTS-build"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            size = int(resp.headers.get("Content-Length", 0))
        meta = item["metadata"]
        wheels.append({"name": meta["name"], "version": meta["version"], "filename": url.rsplit("/", 1)[-1].split("#")[0],
                       "url": url.split("#")[0], "sha256": sha, "size": size})
        print(f"  {meta['name']:30s} {meta['version']:18s} {size / 1e6:9.1f} MB")

    manifest = {
        "version": PACK_VERSION,
        "python": f"cp{sys.version_info.major}{sys.version_info.minor}",
        "platform": "win_amd64",
        "torch": f"{TORCH}+cu121",
        "wheels": sorted(wheels, key=lambda w: -w["size"]),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    total = sum(w["size"] for w in wheels)
    print(f"Wrote {OUT}: {len(wheels)} wheels, {total / 1e9:.2f} GB download")


if __name__ == "__main__":
    main()
