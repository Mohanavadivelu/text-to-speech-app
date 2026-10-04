# Kokoro TTS Studio

A Windows desktop app that turns text into natural-sounding speech, running fully on your own machine with the open [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) model.

The app itself is small (about 340 MB) and runs on any PC's processor. NVIDIA owners can add an optional **GPU pack** from inside the app for much faster generation. Nothing large is bundled: the voice model and the GPU pack download on demand.

## Features

- **7 languages, 37 voices**: American and British English, Hindi, French, Italian, Spanish and Brazilian Portuguese.
- **Voice mixing**: blend two voices into a new one, from 10% to 90%.
- **Speed and pitch** controls, with a quick voice preview.
- **Long texts**: books and articles are split automatically. Generation shows progress and can be cancelled at any time.
- **Text editor**: undo/redo, find and replace, right-click menu, zoom, live word count and an estimate of the audio length.
- **Open documents**: `.txt`, `.md`, `.docx` and `.pdf`, by button, Ctrl+O or drag and drop.
- **Clean text**: one click fixes pasted text (curly quotes, links, markdown symbols, lines broken mid-sentence in PDFs).
- **Custom pronunciations**: tell the voice how to say names and acronyms.
- **Speak a selection**: select part of the text to generate only that part.
- **Remembers** your voice and engine settings, editor zoom and unfinished text between launches.

## Requirements

- Windows 10 or 11
- 4 GB of RAM (8 GB recommended); the CPU engine uses about 1.2–1.6 GB while generating
- About 700 MB of disk: the app (340 MB) plus the voice model (345 MB, downloaded on first launch)
- Internet once, for the first-launch download; after that the app works offline
- Optional, for the GPU pack: an NVIDIA GPU with at least 2 GB of memory, driver 527.41 or newer, and about 4.5 GB more disk

To build from source you also need Python 3.9 – 3.12 with the `py` launcher.

## Engines

| Engine | Runs on | How you get it | Speed (measured, RTX 3050 Ti laptop) |
|---|---|---|---|
| **CPU** (default) | Any PC | Built in | about 2–5× faster than real time |
| **GPU pack** | NVIDIA GPUs | Optional download from the app, 2.8 GB | about 36× faster than real time |

Both engines run the same model and sound the same; in testing their audio matched today's PyTorch output at 0.997–0.998 (spectral correlation).

Choose under **Voice settings → Engine**:

- **Engine**: *Auto* (GPU if the pack is installed and passed its test, otherwise CPU), *GPU* or *CPU*.
- **Performance** (CPU engine): *Maximum* is fastest and runs at slightly lower Windows priority so your PC stays responsive. *Balanced* uses about a quarter of your processor threads for roughly 75% of the speed. *Quiet* uses even fewer, for a cooler, quieter laptop.
- **Quiet mode on battery**: switches to Quiet automatically when the laptop is unplugged.

### GPU pack

On PCs with a suitable NVIDIA GPU, the Engine section offers **Download GPU pack**. The app downloads PyTorch 2.5.1 with CUDA 12.1 and the GPU voice model directly from download.pytorch.org, PyPI and Hugging Face, checking every file against a pinned SHA-256 list (`core/gpu_manifest.json`). Nothing is hosted by this project.

After installing, the app runs a short self-test that compares GPU audio with the CPU engine. If it passes, *Auto* uses the GPU. If the GPU ever fails while generating (for example, out of memory), the app finishes the job on the CPU and tells you. **Remove GPU pack** deletes it again; if the GPU was in use, removal finishes on the next start.

The model is freed from memory after 10 minutes without generating and reloads in a second or two when needed.

## Getting started

### Build the app

From the project folder, run:

```bat
scripts\build.bat
```

The script does everything on a fresh clone:

1. Finds Python 3.9 – 3.12 and creates a virtual environment in `venv\` (without PyTorch).
2. Installs everything in `requirements.txt` and PyInstaller.
3. Checks the GPU pack list for this Python version and regenerates it if needed.
4. Builds the standalone app into `release\bin\KokoroTTS\`.

Then start **`release\bin\KokoroTTS\KokoroTTS.exe`**. On first launch it downloads the voice model (about 345 MB) with a progress window.

### Run from source (for development)

```bat
venv\Scripts\python app.py
```

The development copy uses the same `models\` and `engines\` folders in the project root, so the GPU pack can be installed and tested from the running app exactly as in the exe.

## Using the app

1. Type, paste, open or drop text into the editor.
2. Pick a language and voice on the right. Press the round play button next to the voice to hear a sample.
3. Press **Generate Speech** (or Ctrl+Enter). You can play the first part while the rest is still generating.
4. The finished audio is saved automatically to `audio_output\`. Use **Save As…** to save a copy anywhere else.

### Output files

Every generation is saved as a WAV file (24 kHz, mono) in `audio_output\`, named by the date and time it finished:

```
audio_output\04102026_203015.wav      ← 4 Oct 2026, 20:30:15  (ddmmyyyy_HHMMSS)
```

If two files finish in the same second, the second gets `_2`, and so on. **Open folder** in the Output section opens the folder.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+Enter | Generate speech (or the selection) |
| Space | Play / pause (when not typing) |
| Esc | Stop playback |
| Ctrl+O | Open a text file |
| Ctrl+S | Save the audio as… |
| Ctrl+F / Ctrl+H | Find / find and replace |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+A, Ctrl+C, Ctrl+X, Ctrl+V | Select all, copy, cut, paste |
| Ctrl+Backspace / Ctrl+Delete | Delete the previous / next word |
| Ctrl+mouse wheel, Ctrl+plus / minus, Ctrl+0 | Zoom the editor text, reset zoom |
| Shift+F10 or the Menu key | Open the right-click menu at the cursor |

### Pronunciations

Open **Pronunciations** above the editor and add a word with how it should sound, for example `Kokoro` → `Koh-koh-roh`. Matching is whole-word and ignores case, and it applies only to the generated speech, not the text you see. For English voices you can also enter phonemes between slashes, such as `/kˈOkəɹO/`.

## Project structure

```
text-to-speech-app/
├── app.py                 Entry point: folders, logging, pending GPU-pack removal, UI
├── requirements.txt       Base app only (no PyTorch)
├── core/                  No UI code in here
│   ├── engine.py          Picks the engine (Auto/GPU/CPU), performance modes, CPU fallback
│   ├── engine_onnx.py     CPU engine: Kokoro on ONNX Runtime
│   ├── engine_torch.py    GPU engine: Kokoro on PyTorch + CUDA (GPU pack only)
│   ├── tts_common.py      Shared text splitting, pitch, cancel, progress
│   ├── model_store.py     Pinned model files: download, resume, verify
│   ├── gpu_pack.py        GPU pack: eligibility, install, remove, self-test
│   ├── gpu_manifest.json  Pinned wheel list for the GPU pack (generated)
│   ├── hardware.py        CPU threads, battery, NVIDIA GPU, process priority
│   ├── player.py          Audio playback (pause, seek, volume)
│   ├── voices.py          Languages, voices and preview sentences
│   ├── text_tools.py      Clean text, file loading, pronunciations, estimates
│   ├── settings.py        Saved settings
│   ├── paths.py           All folder and file locations, output naming
│   └── logging_setup.py   Console + rotating log file, crash logging
├── ui/
│   ├── app_window.py      Main window; connects the panels to core/
│   ├── theme.py           Colours and fonts
│   ├── panels/            Title bar, text editor, voice settings, player, status bar
│   └── components/        Reusable widgets (buttons, menu, find bar, dialogs…)
├── docs/                  Original design spec
├── scripts/
│   ├── build.bat              Sets up venv\ and builds the standalone app
│   ├── make_gpu_manifest.py   Regenerates core/gpu_manifest.json
│   └── pyinstaller_hooks/     Bundles the full standard library for the GPU pack
│
│   Created when the app runs (not in git):
├── models/                Voice model (onnx\) and, with the GPU pack, pytorch\
├── engines/               The GPU pack (pytorch-cuda\)
├── audio_output/          Generated speech
├── logs/                  kokoro_tts.log (rotates at 2 MB, keeps 5 old files)
├── user_data/             settings.json, draft.txt, pronunciations.json
├── release/               Output of scripts\build.bat
└── venv/                  Python virtual environment
```

Older versions kept settings, logs and audio in the project root. They are moved into the folders above automatically on first start; nothing is overwritten.

## Building a standalone EXE

```bat
scripts\build.bat
```

This creates `release\bin\KokoroTTS\KokoroTTS.exe` (about 340 MB) with PyInstaller.

- `scripts\build.bat --refresh-gpu-list` re-resolves the GPU pack wheel list (for example after changing the pinned PyTorch version in `scripts\make_gpu_manifest.py`).
- Set `NO_PAUSE=1` to skip the final "press any key", for scripted builds.
- The build refuses to run if PyTorch is installed in `venv\`: the base app must not bundle it.
- Rebuilding keeps `audio_output\`, `logs\`, `user_data\`, `models\` and `engines\` next to the exe.

Share the whole `KokoroTTS` folder; the exe does not run on its own. No Python is needed on the target PC.

## Troubleshooting

- **Something went wrong**: check `logs\kokoro_tts.log`. Errors, including crashes and GPU fallbacks, are recorded there with details.
- **The first launch asks to download**: the voice model (about 345 MB) is needed once. If the download stops, Retry resumes where it left off.
- **No GPU pack option**: it is only offered with an NVIDIA GPU that has at least 2 GB of memory and driver 527.41 or newer. If your GPU is shown but marked "not available", the card says why; updating the NVIDIA driver usually fixes it.
- **The GPU self-test failed**: the app keeps using the CPU. Use **Run GPU test** to try again, or **Remove GPU pack** to free the disk space.
- **The first GPU generation is slow**: loading PyTorch and the model takes about 10 seconds; later generations are fast.
- **A word is pronounced wrongly**: add it under **Pronunciations**.

## Credits

- Speech model: [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache 2.0); ONNX export: [onnx-community/Kokoro-82M-v1.0-ONNX](https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX)
- Runtimes: [ONNX Runtime](https://onnxruntime.ai/), [PyTorch](https://pytorch.org/)
- UI: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
