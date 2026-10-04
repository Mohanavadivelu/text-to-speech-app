# Kokoro TTS Studio

A Windows desktop app that turns text into natural-sounding speech, running fully on your own machine with the open [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) model. It uses your NVIDIA GPU when one is available and falls back to the CPU otherwise.

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
- **Remembers** your voice settings, editor zoom and unfinished text between launches.

## Requirements

- Windows 10 or 11
- Python 3.9 – 3.12 (PyTorch does not support 3.13 yet), with the `py` launcher
- About 3 GB of disk space for PyTorch, plus about 330 MB for the model, which downloads on first use
- Optional: an NVIDIA GPU with CUDA for much faster generation

## Getting started

Double-click **`start.bat`**. On first run it:

1. Creates a virtual environment in `venv\` with a compatible Python.
2. Installs PyTorch (the CUDA build if an NVIDIA GPU is found) and everything in `requirements.txt`.
3. Starts the app.

Later runs skip straight to step 3. The voice model downloads the first time you generate speech.

### Manual setup

```bat
py -3.12 -m venv venv
venv\Scripts\pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python app.py
```

For a CPU-only machine, use `--index-url https://download.pytorch.org/whl/cpu` for PyTorch.

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
├── app.py                 Entry point: sets up folders and logging, starts the UI
├── start.bat              One-click setup and launch
├── requirements.txt
├── core/                  No UI code in here
│   ├── engine.py          Kokoro model, text splitting, voice blending, cancel
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
├── docs/                  Original design spec and HTML mock-up
├── scripts/build.bat      Builds a standalone KokoroTTS.exe
│
│   Created when the app runs (not in git):
├── audio_output/          Generated speech
├── logs/                  kokoro_tts.log (rotates at 2 MB, keeps 5 old files)
├── user_data/             settings.json, draft.txt, pronunciations.json
├── release/               Output of scripts/build.bat
└── venv/                  Python virtual environment
```

Older versions kept settings, logs and audio in the project root. They are moved into the folders above automatically on first start; nothing is overwritten.

## Building a standalone EXE

```bat
scripts\build.bat
```

This creates `release\bin\KokoroTTS\KokoroTTS.exe` with PyInstaller. Share the whole `KokoroTTS` folder (about 2–3 GB with CUDA); the exe does not run on its own. No Python is needed on the target PC. The app creates `audio_output\`, `logs\` and `user_data\` next to the exe.

## Troubleshooting

- **Something went wrong**: check `logs\kokoro_tts.log`. Errors, including crashes, are recorded there with details.
- **Running on CPU although you have an NVIDIA GPU**: the CPU build of PyTorch is installed. Delete `venv\` and run `start.bat` again, or reinstall PyTorch with the CUDA command above.
- **The first generation is slow**: the model (about 330 MB) and voices are downloading. Later runs work offline.
- **"Unauthenticated requests to the HF Hub" warning**: harmless. Setting an `HF_TOKEN` environment variable only speeds up downloads.
- **A word is pronounced wrongly**: add it under **Pronunciations**.

## Credits

- Speech model: [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (Apache 2.0)
- UI: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
