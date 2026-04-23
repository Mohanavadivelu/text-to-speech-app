# Kokoro TTS Studio - PySide6 Architecture

When transitioning from the single-file `app.py` script to a production-ready desktop application with PySide6, organizing the codebase properly is critical. We will strictly separate the User Interface (UI), Business Logic (Core), and Asynchronous Tasks (Workers).

## Proposed Folder Structure

```text
pyside6_app/
│
├── main.py                      # Application entry point. Initializes the app and shows the main window.
├── config.py                    # Global constants, settings keys, and configuration variables.
├── DESIGN.md                    # Architecture and design notes (this file).
│
├── ui/                          # 🎨 All UI and PySide6 graphical components
│   ├── __init__.py
│   ├── main_window.py           # The central application window (combines widgets below).
│   │
│   ├── widgets/                 # Reusable, standalone UI components
│   │   ├── __init__.py
│   │   ├── titlebar.py          # Custom frameless title bar
│   │   ├── text_input.py        # Text editor card
│   │   ├── settings_panel.py    # Right-side settings panel (Voice, Speed, Advanced)
│   │   ├── audio_player.py      # Bottom audio player with waveform and playback controls
│   │   └── statusbar.py         # Custom status bar for errors and state indication
│   │
│   ├── dialogs/                 # Popup dialogs and floating windows
│   │   ├── __init__.py
│   │   └── popup_dialogs.py     # Simple custom message boxes or settings dialogs
│   │
│   ├── styles/                  # Theming and styling
│   │   ├── __init__.py
│   │   ├── theme.qss            # Pure stylesheet for the dark studio theme
│   │   └── style_manager.py     # Python script to load and apply QSS styles/fonts
│   │
│   └── assets/                  # Static resources
│       ├── icons/               # SVG/PNG icons for buttons
│       └── fonts/               # Custom fonts (e.g., Inter)
│
├── core/                        # 🧠 Business logic, audio processing, Kokoro integration
│   ├── __init__.py
│   ├── tts_engine.py            # Wrapper class for the Kokoro model and speech generation logic
│   ├── audio_manager.py         # Logic for handling audio playback (e.g., sounddevice or QtMultimedia)
│   ├── state_manager.py         # Manages the global state (current text, selected voice, generation history)
│   └── utils.py                 # Helper functions (file saving, audio data conversion)
│
└── workers/                     # ⚙️ Background threads (Prevents UI freezing)
    ├── __init__.py
    ├── generation_worker.py     # QRunnable/QThread for processing text to speech asynchronously
    └── signals.py               # Custom Qt signals for workers to communicate with the UI
```

## Architectural Separation of Concerns

### 1. The `ui/` Module (View)
* **Rule:** Must **not** directly generate audio or block the main thread.
* **Responsibility:** Strictly handles user input, drawing pixels, responding to clicks, and sending events to the Core.
* **Communication:** Listens to signals from the `workers/` to update progress bars, error popups, and the player state.

### 2. The `core/` Module (Model & Logic)
* **Rule:** Must **not** import any PySide6 GUI components (like `QPushButton` or `QWidget`).
* **Responsibility:** Holds the state, instantiates the TTS model, processes audio arrays, and writes files. If we ever wanted to make a web app or CLI version, the `core/` folder could be copy-pasted without changes.

### 3. The `workers/` Module (Concurrency)
* **Rule:** Must safely bridge the UI and Core logic using Qt Signals.
* **Responsibility:** Heavy lifting. When the user clicks "Generate", the UI spawns a `generation_worker` in a background thread. The worker calls `core.tts_engine`, waits for the output, and emits a success/error signal back to the UI.
