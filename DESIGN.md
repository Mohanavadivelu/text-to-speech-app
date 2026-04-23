# Kokoro TTS — UI Design Specification

> **Theme:** Studio Dark (VS Code–inspired)  
> **UI Framework:** CustomTkinter (`customtkinter`)  
> **Layout:** Fullscreen / maximised to current OS window size on launch. Min size 820 × 580 px. All panels resize dynamically with the window.  
> **Font stack:** Inter / Segoe UI (labels), JetBrains Mono / Consolas (text input, time display)

---

## Table of Contents

1. [Colour Palette](#1-colour-palette)
2. [Typography](#2-typography)
3. [Window Layout Overview](#3-window-layout-overview)
4. [Panel: Title Bar](#4-panel-title-bar)
5. [Panel: Text Input (Left)](#5-panel-text-input-left)
6. [Panel: Voice Settings (Right)](#6-panel-voice-settings-right)
7. [Panel: Audio Player Bar](#7-panel-audio-player-bar)
8. [Panel: Status Bar](#8-panel-status-bar)
9. [Component: PlayerWaveformCanvas](#9-component-playerwaveformcanvas)
10. [Component: Toast Notification](#10-component-toast-notification)
11. [States & Transitions](#11-states--transitions)
12. [Keyboard Shortcuts](#12-keyboard-shortcuts)
13. [File Structure](#13-file-structure)

---

## 1. Colour Palette

| Token | Hex | Usage |
|---|---|---|
| `bg` | `#0f0f13` | Main window background |
| `surface` | `#1a1a24` | Card / panel surface |
| `surface2` | `#22222f` | Input fields, inner surfaces |
| `surface3` | `#2a2a3a` | Hover state, deeper surface |
| `titlebar` | `#13131e` | Title bar + status bar background |
| `border` | `#2e2e42` | Card borders, dividers |
| `border2` | `#3a3a52` | Hover borders |
| `accent` | `#7c5cbf` | Primary accent (purple) |
| `accent_h` | `#9370db` | Accent hover / speed value |
| `btn_play` | `#1db97a` | Play button background |
| `btn_play_h` | `#22d68e` | Play button hover |
| `btn_stop` | `#e05252` | Stop button text colour |
| `btn_save` | `#3b8eea` | Save button text colour |
| `text` | `#e8e8f0` | Primary text |
| `text2` | `#9898b8` | Secondary text / labels |
| `text3` | `#5a5a7a` | Dim text / placeholders |
| `status_ok` | `#4ade80` | Status dot — ready |
| `status_err` | `#f87171` | Status dot — error |
| `status_busy` | `#f59e0b` | Status dot — generating |
| `waveform_played` | `#60a5fa` | Played waveform bars (blue) |
| `waveform_unplayed` | `#1e3a8a` | Unplayed waveform bars (dark blue) |

---

## 2. Typography

| Token | Font | Size | Weight | Usage |
|---|---|---|---|---|
| `FONT_TITLE` | Segoe UI | 15 | Bold | App title in title bar |
| `FONT_LABEL` | Segoe UI | 10 | Bold | Button labels, section headers |
| `FONT_SUBLABEL` | Segoe UI | 9 | Bold | Card headers |
| `FONT_NORMAL` | Segoe UI | 10 | Normal | General text |
| `FONT_SMALL` | Segoe UI | 9 | Normal | Status bar, metadata |
| `FONT_TINY` | Segoe UI | 8 | Normal | Badges, char count |
| `FONT_MONO` | Consolas | 10 | Normal | Text input area |
| `FONT_SPEED` | JetBrains Mono | 20 | Bold | Speed / time display values |

---

## 3. Window Layout Overview

The window launches **maximised** to the current OS screen size. All panels use `fill="both"` / `expand=True` so they grow and shrink with the window. The right settings panel has a fixed width of 300 px; the left text panel takes all remaining horizontal space.

```
┌─────────────────────────────────────────────────────────────────┐  ← fixed 52 px
│  TITLE BAR                                              [badges] │
├──────────────────────────────────┬──────────────────────────────┤  ← flex height
│                                  │                              │
│   TEXT INPUT PANEL (left)        │   VOICE SETTINGS (right)     │
│   - CTkTextbox  (fills height)   │   - Language combo           │
│   - Char count + Generate btn    │   - Voice combo + preview    │
│                                  │   - Speed slider             │
│                                  │   - Advanced (pitch)         │
│                                  │   - Last output info         │
│                                  │                              │
├──────────────────────────────────┴──────────────────────────────┤  ← fixed ~110 px
│  AUDIO PLAYER BAR                                               │
│  [time] [waveform track ──────────────────] [controls] [vol]   │
├─────────────────────────────────────────────────────────────────┤  ← fixed 28 px
│  STATUS BAR  ● Ready  |  🎙 af_heart  |  [📂 History]          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Panel: Title Bar

**File:** `ui/panels/titlebar.py`  
**Class:** `TitleBar(ctk.CTkFrame)`  
**Height:** 52 px  
**Background:** `titlebar` (`#13131e`)

### Layout

```
[ 🎙 icon ] [ Kokoro TTS / Text-to-Speech Studio ]    [ ⚡ model badge ] [ v1.0 badge ]
```

### UI Elements

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| App icon | `ctk.CTkFrame` | 32×32, bg=`accent`, corner_radius=8 | Static — shows 🎙 emoji centred |
| App title | `ctk.CTkLabel` | font=`FONT_TITLE`, text_color=`text` | Static — "Kokoro TTS" |
| App subtitle | `ctk.CTkLabel` | font=`FONT_TINY`, text_color=`text3` | Static — "Text-to-Speech Studio" |
| Model badge | `ctk.CTkLabel` | bg=`surface2`, border=`accent`@40%, corner_radius=20, text_color=`accent_h` | Static — "⚡ hexgrad/Kokoro-82M" |
| Version badge | `ctk.CTkLabel` | bg=`surface2`, border=`border`, corner_radius=20, text_color=`text3` | Static — "v1.0" |

---

## 5. Panel: Text Input (Left)

**File:** `ui/panels/text_panel.py`  
**Class:** `TextPanel(ctk.CTkFrame)`  
**Position:** Left column, fills available height  
**Background:** `surface`, corner_radius=12, border=`border`

### Layout

```
┌─────────────────────────────────────────┐
│ 📝 TEXT INPUT                           │  ← card header
├─────────────────────────────────────────┤
│                                         │
│  [CTkTextbox — monospace, dark]         │  ← text input area (flex height)
│                                         │
├─────────────────────────────────────────┤
│ Characters: 0 · ~0s estimated  [✨ Btn] │  ← footer row
└─────────────────────────────────────────┘
```

### UI Elements

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| Card header label | `ctk.CTkLabel` | text="📝 Text Input", font=`FONT_SUBLABEL`, text_color=`text2` | Static header |
| Header divider | `ctk.CTkFrame` | height=1, bg=`border` | Visual separator |
| Text input | `ctk.CTkTextbox` | font=`FONT_MONO`, fg_color=`surface2`, text_color=`text`, border_color=`border`, corner_radius=8, wrap="word" | Main text entry area. Fires `on_text_change` on `<KeyRelease>`. Focus border changes to `accent`. |
| Char count label | `ctk.CTkLabel` | font=`FONT_TINY`, text_color=`text3` | Updates live: "Characters: N · ~Xs estimated" |
| Generate button | `ctk.CTkButton` | text="✨ Generate Speech", fg_color=`accent`, hover_color=`accent_h`, corner_radius=50, font=`FONT_LABEL` | Triggers TTS generation. Disabled during generation. Shows animated fill state while generating. |
| Shortcut badge | `ctk.CTkLabel` | text="Ctrl+Enter", bg=`surface3`, font=`FONT_TINY`, text_color=`text3`, corner_radius=4 | Visual hint only. `<Control-Return>` binding triggers generate. |

### States

| State | Generate Button | Text Input |
|---|---|---|
| **Idle** | Enabled, purple gradient | Editable |
| **Generating** | Disabled, animated fill overlay, text="⏳ Generating… N%" | Read-only |
| **Done** | Re-enabled | Editable |
| **Error** | Re-enabled | Editable |

---

## 6. Panel: Voice Settings (Right)

**File:** `ui/panels/settings_panel.py`  
**Class:** `SettingsPanel(ctk.CTkFrame)`  
**Position:** Right column, fixed width 300 px  
**Background:** `surface`, corner_radius=12, border=`border`

### Layout

```
┌──────────────────────────────┐
│ 🎛️ Voice Settings        [▶] │  ← header + collapse toggle
├──────────────────────────────┤
│ 🌐 LANGUAGE                  │
│ [ 🇺🇸 American English  ▼ ]  │
│                              │
│ 🎤 VOICE                     │
│ [ ♀ Heart  A ❤️  ▼ ] [▶]    │
│                              │
│ ⚡ SPEED                     │
│        1.0                   │
│    × normal speed            │
│ 0.5× [━━━●━━━━━━━━] 2.0×    │
│                              │
│ ▶ Advanced Settings          │  ← collapsible accordion
│   🎵 PITCH                   │
│   -5 [━━━━━●━━━━━] +5        │
│                              │
│ ──────────────────────────── │
│ 📁 LAST OUTPUT               │
│ ┌──────────────────────────┐ │
│ │ 🔊  output.wav           │ │
│ │     24 kHz · WAV · 4.2s  │ │  ✅
│ └──────────────────────────┘ │
└──────────────────────────────┘
```

### UI Elements

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| Card header | `ctk.CTkLabel` | text="🎛️ Voice Settings", font=`FONT_SUBLABEL` | Static |
| Collapse toggle | `ctk.CTkButton` | text="▶", width=24, bg=transparent | Collapses/expands the settings body |
| Language label | `ctk.CTkLabel` | text="🌐 LANGUAGE", font=`FONT_TINY`, text_color=`text2` | Static section label |
| Language combo | `ctk.CTkComboBox` | values=language list, fg_color=`surface2`, border_color=`border`, corner_radius=8 | Selecting a language updates the voice list and fires `on_language_change` |
| Voice label | `ctk.CTkLabel` | text="🎤 VOICE", font=`FONT_TINY`, text_color=`text2` | Static section label |
| Voice combo | `ctk.CTkComboBox` | values=voice labels, fg_color=`surface2`, border_color=`border`, corner_radius=8 | Selecting a voice updates `voice_var` and status bar |
| Voice quality badge | `ctk.CTkLabel` | text=e.g. "A ❤️", bg=`accent`@25%, text_color=`accent_h`, corner_radius=4, font=`FONT_TINY` | Updates when voice changes |
| Voice preview button | `ctk.CTkButton` | text="▶", width=28, fg_color=`surface3`, hover_color=`border2` | Plays a short sample of the selected voice (future feature — placeholder) |
| Speed label | `ctk.CTkLabel` | text="⚡ SPEED", font=`FONT_TINY`, text_color=`text2` | Static |
| Speed value | `ctk.CTkLabel` | text="1.0", font=`FONT_SPEED`, text_color=`accent_h` | Updates live as slider moves |
| Speed unit | `ctk.CTkLabel` | text="× normal speed", font=`FONT_TINY`, text_color=`text3` | Static |
| Speed slider | `ctk.CTkSlider` | from_=0.5, to=2.0, fg_color=`surface3`, progress_color=`accent`, button_color=white | Updates `speed_var` and speed value label |
| Advanced toggle | `ctk.CTkButton` | text="▶ Advanced Settings", font=`FONT_SMALL`, bg=transparent, text_color=`text3` | Expands/collapses pitch section |
| Pitch label | `ctk.CTkLabel` | text="🎵 PITCH", font=`FONT_TINY`, text_color=`text2` | Static (inside accordion) |
| Pitch slider | `ctk.CTkSlider` | from_=-5, to=5, fg_color=`surface3`, progress_color=`accent` | Updates `pitch_var` |
| Divider | `ctk.CTkFrame` | height=1, fg_color=`border` | Visual separator |
| Last output label | `ctk.CTkLabel` | text="📁 LAST OUTPUT", font=`FONT_TINY`, text_color=`text2` | Static |
| Output info card | `ctk.CTkFrame` | fg_color=`surface2`, border_color=`border`, corner_radius=8 | Container for output details |
| Output icon | `ctk.CTkLabel` | text="🔊", font=16 | Static icon |
| Output filename | `ctk.CTkLabel` | text="—", font=`FONT_SMALL`, text_color=`text` | Updated after generation: shows filename |
| Output metadata | `ctk.CTkLabel` | text="", font=`FONT_TINY`, text_color=`text3` | Updated after generation: "24 kHz · WAV · Xs" |
| Output check | `ctk.CTkLabel` | text="", text_color=`status_ok` | Shows "✅" after successful generation |

---

## 7. Panel: Audio Player Bar

**File:** `ui/panels/player_bar.py`  
**Class:** `PlayerBar(ctk.CTkFrame)`  
**Position:** Below body, above status bar  
**Background:** `surface2`, border-top=`border`

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ Player                                                          │  ← player-top
├──────────────────────────────────────────────────────────────── │
│  00:02   output.wav  [WAV] [24kHz]                              │  ← player-main
│  00:04.2 [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] │
├─────────────────────────────────────────────────────────────────┤
│ [⏸] [⏹] [⏮] [⏭]  00:00:02 / 00:00:04.2  WAV  🔊[━━●━━] [💾] │  ← player-controls
└─────────────────────────────────────────────────────────────────┘
```

### UI Elements

#### Player Top Row

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| "Player" label | `ctk.CTkLabel` | font=`FONT_SMALL`, text_color=`text2` | Static label |

#### Player Main Row

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| Current time | `ctk.CTkLabel` | text="00:00", font=`FONT_SPEED`, text_color=white | Updates every 100 ms during playback |
| Total time | `ctk.CTkLabel` | text="00:00.0", font=`FONT_SMALL`, text_color=`text3` | Set after generation |
| Filename label | `ctk.CTkLabel` | font=`FONT_SMALL`, text_color=white, bold | Set after generation |
| Format badge | `ctk.CTkLabel` | text="WAV", bg=`surface3`, font=`FONT_TINY`, text_color=`text3` | Static after generation |
| Sample rate badge | `ctk.CTkLabel` | text="24kHz", bg=`surface3`, font=`FONT_TINY`, text_color=`text3` | Static after generation |
| Waveform canvas | `PlayerWaveformCanvas` | height=32, bg=`#15151c` | Draws played (blue) / unplayed (dark) bars. Click to seek. |
| Progress overlay | Drawn on canvas | Semi-transparent white fill + vertical line | Shows playback position |

#### Player Controls Row

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| Play/Pause button | `ctk.CTkButton` | text="⏸"/"▶", width=28, bg=transparent, hover=`surface2` | Toggles playback. Shows ▶ when stopped, ⏸ when playing |
| Stop button | `ctk.CTkButton` | text="⏹", width=28, bg=transparent | Stops playback, resets position to 0 |
| Prev button | `ctk.CTkButton` | text="⏮", width=28, bg=transparent | Seeks to start (position=0) |
| Next button | `ctk.CTkButton` | text="⏭", width=28, bg=transparent | Placeholder — no action |
| Time info label | `ctk.CTkLabel` | font=`FONT_MONO` size 10, text_color=`text3` | "00:00:02 / 00:00:04.2" — updates during playback |
| Volume icon | `ctk.CTkButton` | text="🔊", width=24, bg=transparent | Mute/unmute toggle |
| Volume slider | `ctk.CTkSlider` | width=60, from_=0, to=1, fg_color=`surface3`, progress_color=`btn_save` | Controls playback volume (0.0–1.0) |
| Save As button | `ctk.CTkButton` | text="💾 Save As…", fg_color=`surface2`, text_color=`btn_save`, border_color=`btn_save`@30%, corner_radius=50 | Opens file save dialog. Disabled until audio is generated. |

### States

| State | Waveform | Controls | Time |
|---|---|---|---|
| **No audio** | Empty — "Generate audio to see waveform" | All disabled (opacity 0.35) | "00:00 / 00:00" |
| **Audio ready** | Full waveform drawn, all unplayed | Play/Stop/Prev/Save enabled | "00:00 / MM:SS.s" |
| **Playing** | Progress overlay advances | Play shows ⏸, Stop enabled | Current time updates every 100 ms |
| **Paused** | Progress overlay frozen | Play shows ▶ | Frozen at pause position |
| **Generating** | Dimmed (opacity 0.5), pointer-events none | All disabled | Unchanged |

---

## 8. Panel: Status Bar

**File:** `ui/panels/statusbar.py`  
**Class:** `StatusBar(ctk.CTkFrame)`  
**Height:** 28 px  
**Background:** `titlebar` (`#13131e`), border-top=`border`

### Layout

```
● Ready  |  🎙 af_heart  |  [📂 History]  Kokoro TTS Studio
```

### UI Elements

| Element | Widget | Properties | Functionality |
|---|---|---|---|
| Status dot | `ctk.CTkLabel` | text="●", font=`FONT_TINY` | Colour: `status_ok` (green) / `status_busy` (amber) / `status_err` (red). Pulses via `after()` loop when busy. |
| Status message | `ctk.CTkLabel` | font=`FONT_SMALL`, text_color=`text2` | Updated by `_set_status(msg, state)` |
| Separator | `ctk.CTkFrame` | width=1, height=14, fg_color=`border` | Visual divider |
| Voice label | `ctk.CTkLabel` | text="🎙 af_heart", font=`FONT_TINY`, text_color=`text3` | Updated when voice selection changes |
| Separator | `ctk.CTkFrame` | width=1, height=14, fg_color=`border` | Visual divider |
| History button | `ctk.CTkButton` | text="📂 History", fg_color=transparent, border_color=`border2`, text_color=`text3`, corner_radius=4, font=`FONT_TINY` | Placeholder — no action yet |
| App name label | `ctk.CTkLabel` | text="Kokoro TTS Studio", font=`FONT_TINY`, text_color=`text3` | Static, right-aligned |

### Status States

| State | Dot colour | Dot animation | Message colour |
|---|---|---|---|
| `ok` | `#4ade80` green | Slow pulse | `text2` |
| `busy` | `#f59e0b` amber | Fast pulse | `#f59e0b` |
| `error` | `#f87171` red | Static (no pulse) | `#f87171` |

---

## 9. Component: PlayerWaveformCanvas

**File:** `ui/components/player_waveform.py`  
**Class:** `PlayerWaveformCanvas(tk.Canvas)`

### Methods

| Method | Parameters | Description |
|---|---|---|
| `set_audio(audio, sample_rate)` | `np.ndarray`, `int` | Downsamples audio to canvas width, draws played/unplayed bars |
| `set_progress(position_ratio)` | `float` 0.0–1.0 | Redraws progress overlay at given position |
| `clear()` | — | Resets to empty state with placeholder text |

### Drawing Logic

1. Downsample audio to N bars (N = canvas width ÷ 2)
2. For each bar: height = `abs(sample) × canvas_height × 0.9`
3. Bars left of `progress_ratio × N` → colour `waveform_played` (`#60a5fa`)
4. Bars right of progress → colour `waveform_unplayed` (`#1e3a8a`)
5. Progress line: 1 px vertical white line at `progress_ratio × width`
6. Progress overlay: semi-transparent white fill from 0 to progress line

---

## 10. Component: Toast Notification

**File:** `ui/components/toast.py`  
**Class:** `Toast`

### Behaviour

- Appears as a floating frame anchored to the bottom-centre of the app window
- Slides up with a smooth `after()` animation
- Auto-dismisses after 4 seconds
- Can be dismissed manually by clicking

### UI Elements

| Element | Widget | Properties |
|---|---|---|
| Container | `ctk.CTkFrame` | bg=`#1a1010` (error) or `surface3` (info), border=`status_err`@30%, corner_radius=8 |
| Icon | `ctk.CTkLabel` | "🔴" (error) / "💡" (info) |
| Message | `ctk.CTkLabel` | font=`FONT_SMALL`, text_color=`status_err` or `text` |

### Usage

```python
Toast(root, message="Error: Model failed to load", kind="error")
Toast(root, message="Saved to output.wav", kind="info")
```

---

## 11. States & Transitions

```
IDLE
  │
  ├─[user types text]──────────────────► IDLE (char count updates)
  │
  ├─[click Generate / Ctrl+Enter]──────► GENERATING
  │                                         │
  │                                    [success]──► AUDIO_READY
  │                                         │
  │                                    [error]────► IDLE + Toast(error)
  │
AUDIO_READY
  │
  ├─[click Play / Space]───────────────► PLAYING
  │                                         │
  │                                    [playback ends]──► AUDIO_READY
  │                                         │
  │                                    [click Stop]─────► AUDIO_READY
  │
  ├─[click Generate again]─────────────► GENERATING
  │
  └─[click Save As]────────────────────► AUDIO_READY (file saved, toast shown)

PLAYING
  ├─[click Pause / Space]──────────────► PAUSED
  └─[click Stop / Esc]─────────────────► AUDIO_READY

PAUSED
  └─[click Play / Space]───────────────► PLAYING
```

---

## 12. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Generate speech |
| `Space` | Play / Pause (when text input not focused) |
| `Esc` | Stop playback |
| `Ctrl+S` | Save As |

---

## 13. File Structure

```
text-to-speech-app/
│
├── app.py                          ← Entry point (< 10 lines)
│
├── core/
│   ├── __init__.py
│   ├── engine.py                   ← TTSEngine: KPipeline wrapper, generate()
│   ├── player.py                   ← AudioPlayer: play(), stop(), progress callbacks
│   └── voices.py                   ← LANG_CODES, LANG_FLAGS, VOICES registry
│
├── ui/
│   ├── __init__.py
│   ├── app_window.py               ← KokoroApp: root window, wires panels to core
│   ├── theme.py                    ← C{} palette, FONT_*, WIN_*, apply_styles()
│   │
│   ├── components/
│   │   ├── __init__.py
│   │   ├── styled_button.py        ← StyledButton (legacy compat, wraps CTkButton)
│   │   ├── player_waveform.py      ← PlayerWaveformCanvas
│   │   └── toast.py                ← Toast notification
│   │
│   └── panels/
│       ├── __init__.py
│       ├── titlebar.py             ← TitleBar panel
│       ├── text_panel.py           ← TextPanel (text input + generate button)
│       ├── settings_panel.py       ← SettingsPanel (voice, speed, pitch, output)
│       ├── player_bar.py           ← PlayerBar (waveform + controls + volume)
│       └── statusbar.py            ← StatusBar
│
├── DESIGN.md                       ← This file
├── start.bat
├── build.bat
├── requirements.txt
└── README.md
```

### Dependency Rules

- `core/` — **zero** tkinter or UI imports
- `ui/components/` — imports from `ui/theme.py` only
- `ui/panels/` — imports from `ui/theme.py` and `ui/components/`
- `ui/app_window.py` — imports from `core/` and `ui/panels/`
- `app.py` — imports from `ui/app_window.py` only

---

*Last updated: 2026-04-23*
