import sys, os

# pythonw.exe has no console — loguru crashes if stderr/stdout are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import logging
from logging.handlers import RotatingFileHandler

_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kokoro_tts.log")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        RotatingFileHandler(_log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import numpy as np
import soundfile as sf
import sounddevice as sd

# ── Voice registry ──────────────────────────────────────────────────────────

LANG_CODES = {
    "American English": "a",
    "British English":  "b",
    "Hindi":            "h",
    "French":           "f",
    "Italian":          "i",
    "Japanese":         "j",
    "Mandarin Chinese": "z",
    "Spanish":          "e",
    "Br. Portuguese":   "p",
}

LANG_FLAGS = {
    "American English": "🇺🇸",
    "British English":  "🇬🇧",
    "Hindi":            "🇮🇳",
    "French":           "🇫🇷",
    "Italian":          "🇮🇹",
    "Japanese":         "🇯🇵",
    "Mandarin Chinese": "🇨🇳",
    "Spanish":          "🇪🇸",
    "Br. Portuguese":   "🇧🇷",
}

VOICES = {
    "American English": [
        ("af_heart",   "Heart ♀ ❤️  · A"),
        ("af_bella",   "Bella ♀ 🔥 · A-"),
        ("af_nicole",  "Nicole ♀ 🎧 · B-"),
        ("af_aoede",   "Aoede ♀ · C+"),
        ("af_kore",    "Kore ♀ · C+"),
        ("af_sarah",   "Sarah ♀ · C+"),
        ("af_alloy",   "Alloy ♀ · C"),
        ("af_nova",    "Nova ♀ · C"),
        ("af_sky",     "Sky ♀ · C-"),
        ("am_fenrir",  "Fenrir ♂ · C+"),
        ("am_michael", "Michael ♂ · C+"),
        ("am_puck",    "Puck ♂ · C+"),
        ("am_echo",    "Echo ♂ · D"),
        ("am_eric",    "Eric ♂ · D"),
        ("am_liam",    "Liam ♂ · D"),
        ("am_adam",    "Adam ♂ · F+"),
    ],
    "British English": [
        ("bf_emma",     "Emma ♀ · B-"),
        ("bf_isabella", "Isabella ♀ · C"),
        ("bf_alice",    "Alice ♀ · D"),
        ("bf_lily",     "Lily ♀ · D"),
        ("bm_fable",    "Fable ♂ · C"),
        ("bm_george",   "George ♂ · C"),
        ("bm_lewis",    "Lewis ♂ · D+"),
        ("bm_daniel",   "Daniel ♂ · D"),
    ],
    "Hindi": [
        ("hf_alpha", "Alpha ♀ · C"),
        ("hf_beta",  "Beta ♀ · C"),
        ("hm_omega", "Omega ♂ · C"),
        ("hm_psi",   "Psi ♂ · C"),
    ],
    "French": [
        ("ff_siwis", "Siwis ♀ · B-"),
    ],
    "Italian": [
        ("if_sara",   "Sara ♀ · C"),
        ("im_nicola", "Nicola ♂ · C"),
    ],
    "Japanese": [
        ("jf_alpha",      "Alpha ♀ · C+"),
        ("jf_gongitsune", "Gongitsune ♀ · C"),
        ("jf_tebukuro",   "Tebukuro ♀ · C"),
        ("jm_kumo",       "Kumo ♂ · C-"),
    ],
    "Mandarin Chinese": [
        ("zf_xiaobei",  "Xiaobei ♀"),
        ("zf_xiaoni",   "Xiaoni ♀"),
        ("zf_xiaoxiao", "Xiaoxiao ♀"),
        ("zf_xiaoyi",   "Xiaoyi ♀"),
        ("zm_yunjian",  "Yunjian ♂"),
        ("zm_yunxi",    "Yunxi ♂"),
        ("zm_yunxia",   "Yunxia ♂"),
        ("zm_yunyang",  "Yunyang ♂"),
    ],
    "Spanish": [
        ("ef_dora",  "Dora ♀"),
        ("em_alex",  "Alex ♂"),
        ("em_santa", "Santa ♂"),
    ],
    "Br. Portuguese": [
        ("pf_dora",  "Dora ♀"),
        ("pm_alex",  "Alex ♂"),
        ("pm_santa", "Santa ♂"),
    ],
}

# ── Studio Dark colour palette ───────────────────────────────────────────────

C = {
    # Backgrounds
    "bg":           "#0f0f13",   # main background
    "surface":      "#1a1a24",   # card / panel surface
    "surface2":     "#22222f",   # input fields / inner surfaces
    "surface3":     "#2a2a3a",   # hover / deeper surface
    "titlebar":     "#13131e",   # title bar

    # Borders
    "border":       "#2e2e42",
    "border2":      "#3a3a52",

    # Accent — purple
    "accent":       "#7c5cbf",
    "accent_h":     "#9370db",
    "accent_glow":  "#7c5cbf",

    # Buttons
    "btn_play":     "#1db97a",
    "btn_play_h":   "#22d68e",
    "btn_stop":     "#e05252",
    "btn_stop_h":   "#f06060",
    "btn_save":     "#3b8eea",
    "btn_save_h":   "#5aa3f5",

    # Text
    "text":         "#e8e8f0",
    "text2":        "#9898b8",
    "text3":        "#5a5a7a",

    # Status
    "status_ok":    "#4ade80",
    "status_err":   "#f87171",
    "status_busy":  "#f59e0b",

    # Misc
    "progress":     "#7c5cbf",
    "waveform":     "#7c5cbf",
    "waveform2":    "#9370db",
}

# ── Constants ────────────────────────────────────────────────────────────────

SAMPLE_RATE   = 24000
WIN_W, WIN_H  = 980, 680
WIN_MIN_W     = 820
WIN_MIN_H     = 580
PROGRESS_SPEED = 10

FONT_TITLE   = ("Segoe UI", 15, "bold")
FONT_LABEL   = ("Segoe UI", 10, "bold")
FONT_SUBLABEL= ("Segoe UI", 9, "bold")
FONT_NORMAL  = ("Segoe UI", 10)
FONT_SMALL   = ("Segoe UI", 9)
FONT_TINY    = ("Segoe UI", 8)
FONT_MONO    = ("Consolas", 10)
FONT_SPEED   = ("Segoe UI", 20, "bold")


# ── Styled button helper ─────────────────────────────────────────────────────

class StyledButton(tk.Button):
    """A flat tk.Button with hover colour support."""

    def __init__(self, parent, text, command, bg, fg, hover_bg,
                 font=FONT_LABEL, state="normal", **kwargs):
        self._bg       = bg
        self._fg       = fg
        self._hover_bg = hover_bg
        self._normal_state = state

        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            font=font,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2" if state == "normal" else "",
            state=state,
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _e=None):
        if str(self.cget("state")) != "disabled":
            self.config(bg=self._hover_bg)

    def _on_leave(self, _e=None):
        if str(self.cget("state")) != "disabled":
            self.config(bg=self._bg)

    def config_state(self, state):
        if state == "disabled":
            self.config(state="disabled", cursor="", bg=self._bg)
        else:
            self.config(state="normal", cursor="hand2", bg=self._bg)

    def config_text(self, text):
        self.config(text=text)


# ── Waveform canvas ──────────────────────────────────────────────────────────

class WaveformCanvas(tk.Canvas):
    """Draws a static waveform from audio data."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=C["surface2"], highlightthickness=0, **kwargs)
        self._audio = None
        self._draw_empty()

    def _draw_empty(self):
        self.delete("all")
        w = self.winfo_reqwidth() or 600
        h = self.winfo_reqheight() or 80
        self.create_text(w//2, h//2, text="〰  Generate audio to see waveform",
                         fill=C["text3"], font=FONT_SMALL)

    def set_audio(self, audio: np.ndarray, sample_rate: int):
        self._audio = audio
        self._sr    = sample_rate
        self.after(50, self._render)

    def _render(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10 or self._audio is None:
            return

        audio = self._audio
        # Downsample to canvas width
        n_samples = len(audio)
        step = max(1, n_samples // w)
        samples = audio[::step][:w]

        mid = h // 2
        bar_w = max(1, w // len(samples))

        for i, s in enumerate(samples):
            amp = int(abs(float(s)) * mid * 0.9)
            amp = max(1, min(amp, mid - 2))
            x = i * bar_w
            # Gradient-like: brighter in center
            brightness = int(180 + 75 * abs(float(s)))
            brightness = min(255, brightness)
            color = C["waveform"]
            self.create_line(x, mid - amp, x, mid + amp,
                             fill=color, width=bar_w)

        # Duration label
        duration = n_samples / self._sr
        mins = int(duration // 60)
        secs = duration % 60
        dur_text = f"{mins}:{secs:05.2f}"
        self.create_rectangle(w-60, 4, w-4, 20,
                               fill=C["surface3"], outline=C["border"])
        self.create_text(w-32, 12, text=dur_text,
                         fill=C["text2"], font=FONT_TINY)


# ── Main application ─────────────────────────────────────────────────────────

class KokoroApp:
    def __init__(self, root: tk.Tk):
        log.info("KokoroApp starting")
        self.root = root
        self.root.title("Kokoro TTS")
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.minsize(WIN_MIN_W, WIN_MIN_H)
        self.root.configure(bg=C["bg"])

        # Remove default title bar on Windows for custom look
        # (keep standard for compatibility — custom chrome via frame)

        self.pipeline        = None
        self._pipeline_lang  = None   # track loaded lang code
        self.audio_data      = None
        self.sample_rate     = SAMPLE_RATE
        self.playback_thread = None
        self._stop_play      = threading.Event()
        self._generating     = False

        self._build_styles()
        self._build_ui()
        self._update_voice_list()

    # ── ttk styles ───────────────────────────────────────────────────────────

    def _build_styles(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")

        s.configure("TFrame",      background=C["bg"])
        s.configure("Card.TFrame", background=C["surface"])

        s.configure("TLabel",
                    background=C["bg"],
                    foreground=C["text"],
                    font=FONT_NORMAL)
        s.configure("Card.TLabel",
                    background=C["surface"],
                    foreground=C["text"],
                    font=FONT_NORMAL)
        s.configure("Sub.TLabel",
                    background=C["surface"],
                    foreground=C["text2"],
                    font=FONT_SUBLABEL)
        s.configure("Dim.TLabel",
                    background=C["surface"],
                    foreground=C["text3"],
                    font=FONT_SMALL)
        s.configure("Dim2.TLabel",
                    background=C["surface2"],
                    foreground=C["text3"],
                    font=FONT_SMALL)
        s.configure("Speed.TLabel",
                    background=C["surface"],
                    foreground=C["accent_h"],
                    font=FONT_SPEED)

        # Combobox
        s.configure("TCombobox",
                    font=FONT_NORMAL,
                    fieldbackground=C["surface2"],
                    background=C["surface2"],
                    foreground=C["text"],
                    selectbackground=C["accent"],
                    selectforeground="#ffffff",
                    arrowcolor=C["text2"],
                    bordercolor=C["border"],
                    lightcolor=C["border"],
                    darkcolor=C["border"],
                    relief="flat")
        s.map("TCombobox",
              fieldbackground=[("readonly", C["surface2"]),
                               ("disabled", C["bg"])],
              foreground=[("readonly", C["text"])],
              background=[("readonly", C["surface2"])],
              bordercolor=[("focus", C["accent"])])

        # Scrollbar
        s.configure("TScrollbar",
                    background=C["surface2"],
                    troughcolor=C["surface"],
                    arrowcolor=C["text3"],
                    bordercolor=C["surface"],
                    darkcolor=C["surface"],
                    lightcolor=C["surface"],
                    relief="flat")
        s.map("TScrollbar", background=[("active", C["border2"])])

        # Scale
        s.configure("TScale",
                    background=C["surface"],
                    troughcolor=C["surface3"],
                    sliderlength=18,
                    sliderrelief="flat")
        s.map("TScale",
              background=[("active", C["surface3"])],
              troughcolor=[("active", C["border2"])])

        # Separator
        s.configure("TSeparator", background=C["border"])

        # Progress bar
        s.configure("Accent.Horizontal.TProgressbar",
                    troughcolor=C["surface2"],
                    background=C["progress"],
                    bordercolor=C["border"],
                    thickness=3,
                    relief="flat")

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_titlebar()
        self._build_tabbar()

        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, minsize=290, weight=0)
        body.rowconfigure(0, weight=1)

        # Use grid on body frame
        self._build_left_panel(body)
        self._build_settings_panel(body)
        self._build_progress()
        self._build_action_bar()
        self._build_statusbar()

    # ── Title bar ────────────────────────────────────────────────────────────

    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=C["titlebar"], height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        # Left: icon + title
        left = tk.Frame(bar, bg=C["titlebar"])
        left.pack(side="left", padx=16, pady=8)

        icon_frame = tk.Frame(left, bg=C["accent"], width=32, height=32)
        icon_frame.pack(side="left")
        icon_frame.pack_propagate(False)
        tk.Label(icon_frame, text="🎙", bg=C["accent"],
                 font=("Segoe UI", 14)).place(relx=0.5, rely=0.5, anchor="center")

        title_frame = tk.Frame(left, bg=C["titlebar"])
        title_frame.pack(side="left", padx=(10, 0))
        tk.Label(title_frame, text="Kokoro TTS",
                 bg=C["titlebar"], fg=C["text"],
                 font=FONT_TITLE).pack(anchor="w")
        tk.Label(title_frame, text="Text-to-Speech Studio",
                 bg=C["titlebar"], fg=C["text3"],
                 font=FONT_TINY).pack(anchor="w")

        # Right: badges
        right = tk.Frame(bar, bg=C["titlebar"])
        right.pack(side="right", padx=16)

        model_lbl = tk.Label(right, text="⚡ hexgrad/Kokoro-82M",
                             bg=C["surface2"], fg=C["accent_h"],
                             font=FONT_TINY, padx=8, pady=3,
                             relief="flat")
        model_lbl.pack(side="left", padx=(0, 8))

        ver_lbl = tk.Label(right, text="v1.0",
                           bg=C["surface2"], fg=C["text3"],
                           font=FONT_TINY, padx=8, pady=3,
                           relief="flat")
        ver_lbl.pack(side="left")

    # ── Tab bar ──────────────────────────────────────────────────────────────

    def _build_tabbar(self):
        bar = tk.Frame(self.root, bg=C["surface"],
                       highlightbackground=C["border"], highlightthickness=1)
        bar.pack(fill="x")

        tabs = [("📝  Generate", True), ("📂  History", False), ("⚙️  Settings", False)]
        for label, active in tabs:
            fg   = C["text"]   if active else C["text3"]
            bord = C["accent"] if active else C["surface"]
            f = tk.Frame(bar, bg=C["surface"])
            f.pack(side="left")
            tk.Label(f, text=label, bg=C["surface"], fg=fg,
                     font=FONT_SMALL, padx=14, pady=10).pack()
            # Active underline
            tk.Frame(f, bg=bord, height=2).pack(fill="x")

    # ── Left panel: text input + waveform ────────────────────────────────────

    def _build_left_panel(self, parent):
        frame = tk.Frame(parent, bg=C["bg"])
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        frame.rowconfigure(0, weight=3)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        self._build_text_card(frame)
        self._build_waveform_card(frame)

    def _build_text_card(self, parent):
        card = tk.Frame(parent, bg=C["surface"],
                        highlightbackground=C["border"], highlightthickness=1)
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)

        # Card header
        hdr = tk.Frame(card, bg=C["surface"],
                       highlightbackground=C["border"], highlightthickness=0)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Frame(hdr, bg=C["border"], height=1).pack(fill="x", side="bottom")
        tk.Label(hdr, text="📝  Text Input", bg=C["surface"], fg=C["text2"],
                 font=FONT_SUBLABEL, padx=14, pady=10).pack(side="left")

        # Text area
        txt_wrap = tk.Frame(card, bg=C["surface2"],
                            highlightbackground=C["border"], highlightthickness=1)
        txt_wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=(10, 4))
        txt_wrap.rowconfigure(0, weight=1)
        txt_wrap.columnconfigure(0, weight=1)

        self.text_input = tk.Text(
            txt_wrap, wrap="word", font=FONT_MONO,
            bg=C["surface2"], fg=C["text"],
            insertbackground=C["accent_h"],
            relief="flat", bd=0, padx=10, pady=10,
            selectbackground=C["accent"],
            selectforeground="#ffffff",
        )
        self.text_input.grid(row=0, column=0, sticky="nsew")
        self.text_input.bind("<KeyRelease>", self._on_text_change)

        sb = ttk.Scrollbar(txt_wrap, orient="vertical",
                           command=self.text_input.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.text_input.configure(yscrollcommand=sb.set)

        # Footer: char count
        footer = tk.Frame(card, bg=C["surface"])
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 8))
        self.char_label = tk.Label(footer, text="Characters: 0",
                                   bg=C["surface"], fg=C["text3"],
                                   font=FONT_TINY)
        self.char_label.pack(side="right")
        self.est_label = tk.Label(footer, text="",
                                  bg=C["surface"], fg=C["text3"],
                                  font=FONT_TINY)
        self.est_label.pack(side="right", padx=(0, 12))

    def _build_waveform_card(self, parent):
        card = tk.Frame(parent, bg=C["surface"],
                        highlightbackground=C["border"], highlightthickness=1)
        card.grid(row=1, column=0, sticky="nsew")
        card.rowconfigure(1, weight=1)
        card.columnconfigure(0, weight=1)

        # Header
        hdr = tk.Frame(card, bg=C["surface"])
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Frame(hdr, bg=C["border"], height=1).pack(fill="x", side="bottom")
        tk.Label(hdr, text="〰  Waveform Preview", bg=C["surface"], fg=C["text2"],
                 font=FONT_SUBLABEL, padx=14, pady=10).pack(side="left")

        # Waveform canvas
        canvas_wrap = tk.Frame(card, bg=C["surface2"],
                               highlightbackground=C["border"], highlightthickness=1)
        canvas_wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=10)
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)

        self.waveform = WaveformCanvas(canvas_wrap, height=80)
        self.waveform.grid(row=0, column=0, sticky="nsew")

    # ── Settings panel ───────────────────────────────────────────────────────

    def _build_settings_panel(self, parent):
        card = tk.Frame(parent, bg=C["surface"],
                        highlightbackground=C["border"], highlightthickness=1)
        card.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        card.columnconfigure(0, weight=1)

        # Header
        hdr = tk.Frame(card, bg=C["surface"])
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Frame(hdr, bg=C["border"], height=1).pack(fill="x", side="bottom")
        tk.Label(hdr, text="🎛️  Voice Settings", bg=C["surface"], fg=C["text2"],
                 font=FONT_SUBLABEL, padx=14, pady=10).pack(side="left")

        body = tk.Frame(card, bg=C["surface"])
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=10)
        body.columnconfigure(0, weight=1)

        row = 0

        # ── Language ──
        tk.Label(body, text="🌐  LANGUAGE", bg=C["surface"], fg=C["text2"],
                 font=FONT_TINY).grid(row=row, column=0, sticky="w", pady=(0, 4))
        row += 1

        self.lang_var = tk.StringVar(value="American English")
        lang_cb = ttk.Combobox(body, textvariable=self.lang_var,
                               values=list(VOICES.keys()),
                               state="readonly", font=FONT_NORMAL)
        lang_cb.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        lang_cb.bind("<<ComboboxSelected>>", lambda e: self._update_voice_list())
        row += 1

        # ── Voice ──
        tk.Label(body, text="🎤  VOICE", bg=C["surface"], fg=C["text2"],
                 font=FONT_TINY).grid(row=row, column=0, sticky="w", pady=(0, 4))
        row += 1

        self.voice_var = tk.StringVar()
        self.voice_cb = ttk.Combobox(body, textvariable=self.voice_var,
                                     state="readonly", font=FONT_NORMAL)
        self.voice_cb.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1

        # ── Speed ──
        tk.Label(body, text="⚡  SPEED", bg=C["surface"], fg=C["text2"],
                 font=FONT_TINY).grid(row=row, column=0, sticky="w", pady=(0, 4))
        row += 1

        # Big speed display
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_label = tk.Label(body, text="1.0",
                                    bg=C["surface"], fg=C["accent_h"],
                                    font=FONT_SPEED)
        self.speed_label.grid(row=row, column=0, pady=(0, 2))
        row += 1

        tk.Label(body, text="× normal speed", bg=C["surface"], fg=C["text3"],
                 font=FONT_TINY).grid(row=row, column=0, pady=(0, 8))
        row += 1

        # Slider row
        slider_row = tk.Frame(body, bg=C["surface"])
        slider_row.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        slider_row.columnconfigure(1, weight=1)

        tk.Label(slider_row, text="0.5×", bg=C["surface"], fg=C["text3"],
                 font=FONT_TINY).grid(row=0, column=0, padx=(0, 6))

        speed_scale = ttk.Scale(slider_row, from_=0.5, to=2.0,
                                variable=self.speed_var, orient="horizontal",
                                command=self._on_speed_change)
        speed_scale.grid(row=0, column=1, sticky="ew")

        tk.Label(slider_row, text="2.0×", bg=C["surface"], fg=C["text3"],
                 font=FONT_TINY).grid(row=0, column=2, padx=(6, 0))
        row += 1

        # ── Divider ──
        tk.Frame(body, bg=C["border"], height=1).grid(
            row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1

        # ── Last Output ──
        tk.Label(body, text="📁  LAST OUTPUT", bg=C["surface"], fg=C["text2"],
                 font=FONT_TINY).grid(row=row, column=0, sticky="w", pady=(0, 6))
        row += 1

        out_card = tk.Frame(body, bg=C["surface2"],
                            highlightbackground=C["border"], highlightthickness=1)
        out_card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        out_card.columnconfigure(1, weight=1)

        self.out_icon = tk.Label(out_card, text="🔊",
                                 bg=C["surface2"], fg=C["text2"],
                                 font=("Segoe UI", 16), padx=10, pady=8)
        self.out_icon.grid(row=0, column=0, rowspan=2)

        self.output_name_label = tk.Label(out_card, text="—",
                                          bg=C["surface2"], fg=C["text"],
                                          font=FONT_SMALL, anchor="w")
        self.output_name_label.grid(row=0, column=1, sticky="w", pady=(6, 0))

        self.output_meta_label = tk.Label(out_card, text="",
                                          bg=C["surface2"], fg=C["text3"],
                                          font=FONT_TINY, anchor="w")
        self.output_meta_label.grid(row=1, column=1, sticky="w", pady=(0, 6))

        self.out_check = tk.Label(out_card, text="",
                                  bg=C["surface2"], fg=C["status_ok"],
                                  font=FONT_NORMAL, padx=8)
        self.out_check.grid(row=0, column=2, rowspan=2)
        row += 1

        # ── Divider ──
        tk.Frame(body, bg=C["border"], height=1).grid(
            row=row, column=0, sticky="ew", pady=(0, 14))
        row += 1

        # ── Info note ──
        note = tk.Frame(body, bg=C["surface3"],
                        highlightbackground=C["border2"], highlightthickness=1)
        note.grid(row=row, column=0, sticky="ew")
        note.columnconfigure(1, weight=1)

        tk.Label(note, text="💡", bg=C["surface3"],
                 font=("Segoe UI", 12), padx=8, pady=8).grid(row=0, column=0)
        tk.Label(note, text="First launch downloads the Kokoro\nmodel (~330 MB). All subsequent\nruns are fully offline.",
                 bg=C["surface3"], fg=C["text3"],
                 font=FONT_TINY, justify="left", pady=8).grid(row=0, column=1, sticky="w")

    # ── Progress bar ─────────────────────────────────────────────────────────

    def _build_progress(self):
        self.progress = ttk.Progressbar(self.root, mode="indeterminate",
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=14, pady=(6, 0))

    # ── Action bar ───────────────────────────────────────────────────────────

    def _build_action_bar(self):
        bar = tk.Frame(self.root, bg=C["surface"],
                       highlightbackground=C["border"], highlightthickness=1)
        bar.pack(fill="x", padx=14, pady=(8, 0))

        inner = tk.Frame(bar, bg=C["surface"])
        inner.pack(fill="x", padx=12, pady=10)

        # Generate button
        self.btn_generate = StyledButton(
            inner, text="✨  Generate Speech",
            command=self._on_generate,
            bg=C["accent"], fg="#ffffff", hover_bg=C["accent_h"],
            font=FONT_LABEL)
        self.btn_generate.pack(side="left", padx=(0, 8))

        # Play button
        self.btn_play = StyledButton(
            inner, text="▶  Play",
            command=self._on_play,
            bg=C["btn_play"], fg="#ffffff", hover_bg=C["btn_play_h"],
            font=FONT_LABEL, state="disabled")
        self.btn_play.pack(side="left", padx=(0, 8))

        # Stop button
        self.btn_stop = StyledButton(
            inner, text="■  Stop",
            command=self._on_stop,
            bg=C["surface2"], fg=C["btn_stop"], hover_bg=C["surface3"],
            font=FONT_LABEL, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 8))

        # Save button (right-aligned)
        self.btn_save = StyledButton(
            inner, text="💾  Save As…",
            command=self._on_save,
            bg=C["surface2"], fg=C["btn_save"], hover_bg=C["surface3"],
            font=FONT_LABEL, state="disabled")
        self.btn_save.pack(side="right")

    # ── Status bar ───────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=C["titlebar"],
                       highlightbackground=C["border"], highlightthickness=1)
        bar.pack(fill="x", side="bottom")

        inner = tk.Frame(bar, bg=C["titlebar"])
        inner.pack(fill="x", padx=14, pady=4)

        # Status dot
        self.status_dot = tk.Label(inner, text="●",
                                   bg=C["titlebar"], fg=C["status_ok"],
                                   font=FONT_TINY)
        self.status_dot.pack(side="left", padx=(0, 4))

        self.status_label = tk.Label(inner, text="Ready",
                                     bg=C["titlebar"], fg=C["text2"],
                                     font=FONT_SMALL)
        self.status_label.pack(side="left")

        # Right side info
        right = tk.Frame(inner, bg=C["titlebar"])
        right.pack(side="right")

        sep = tk.Frame(right, bg=C["border"], width=1, height=14)
        sep.pack(side="left", padx=10)

        self.voice_status = tk.Label(right, text="🎙 af_heart",
                                     bg=C["titlebar"], fg=C["text3"],
                                     font=FONT_TINY)
        self.voice_status.pack(side="left", padx=(0, 10))

        sep2 = tk.Frame(right, bg=C["border"], width=1, height=14)
        sep2.pack(side="left", padx=(0, 10))

        tk.Label(right, text="🖥️ CUDA · RTX 3050 Ti",
                 bg=C["titlebar"], fg=C["text3"],
                 font=FONT_TINY).pack(side="left")

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_text_change(self, _event=None):
        text = self.text_input.get("1.0", "end-1c")
        n = len(text)
        self.char_label.config(text=f"Characters: {n:,}")
        # Rough estimate: ~150 chars/sec at 1× speed
        if n > 0:
            est = max(1, n // 15)
            self.est_label.config(text=f"~{est}s estimated  ·")
        else:
            self.est_label.config(text="")

    def _on_speed_change(self, _val=None):
        v = self.speed_var.get()
        self.speed_label.config(text=f"{v:.1f}")

    def _update_voice_list(self):
        lang   = self.lang_var.get()
        voices = VOICES.get(lang, [])
        labels = [label for _, label in voices]
        self.voice_cb.configure(values=labels)
        if labels:
            self.voice_cb.current(0)
        # Update status bar voice
        vid = self._get_voice_id()
        self.voice_status.config(text=f"🎙 {vid}")

    def _get_voice_id(self) -> str:
        lang   = self.lang_var.get()
        label  = self.voice_var.get()
        voices = VOICES.get(lang, [])
        for vid, lbl in voices:
            if lbl == label:
                return vid
        return voices[0][0] if voices else "af_heart"

    # ── Generate ─────────────────────────────────────────────────────────────

    def _on_generate(self):
        text = self.text_input.get("1.0", "end-1c").strip()
        if not text:
            log.warning("Generate requested with empty text")
            messagebox.showwarning("No Text", "Please enter some text first.")
            return
        if self._generating:
            log.debug("Generate ignored — already generating")
            return

        self._generating = True
        self.btn_generate.config_state("disabled")
        self.btn_generate.config_text("⏳  Generating…")
        self.btn_play.config_state("disabled")
        self.btn_save.config_state("disabled")
        self.progress.start(PROGRESS_SPEED)
        self._set_status("Generating audio…", "busy")

        threading.Thread(target=self._generate_worker,
                         args=(text,), daemon=True).start()

    def _generate_worker(self, text: str):
        try:
            from kokoro import KPipeline

            lang      = self.lang_var.get()
            lang_code = LANG_CODES.get(lang, "a")
            voice_id  = self._get_voice_id()
            speed     = round(self.speed_var.get(), 1)

            log.info("Generating: chars=%d  voice=%s  lang=%s  speed=%s",
                     len(text), voice_id, lang, speed)

            if self.pipeline is None:
                log.info("Loading KPipeline for lang_code=%s", lang_code)
                self.root.after(0, lambda: self._set_status("Loading model…", "busy"))
                self.pipeline       = KPipeline(lang_code=lang_code)
                self._pipeline_lang = lang_code
                log.info("KPipeline loaded")
            elif self._pipeline_lang != lang_code:
                log.info("Switching KPipeline from %s to %s",
                         self._pipeline_lang, lang_code)
                self.root.after(0, lambda: self._set_status("Switching language…", "busy"))
                self.pipeline       = KPipeline(lang_code=lang_code)
                self._pipeline_lang = lang_code
                log.info("KPipeline switched")

            chunks = []
            for _gs, _ps, audio in self.pipeline(text, voice=voice_id, speed=speed):
                chunks.append(audio)

            full_audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
            self.audio_data  = full_audio
            self.sample_rate = SAMPLE_RATE

            # Auto-save to workspace
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output.wav")
            sf.write(out_path, full_audio, self.sample_rate)
            log.info("Auto-saved to %s  (%.2fs)", out_path,
                     len(full_audio) / self.sample_rate)

            self.root.after(0, lambda: self._on_generate_done(out_path, voice_id))

        except Exception as exc:
            log.exception("Generation failed: %s", exc)
            self.root.after(0, lambda msg=str(exc): self._on_generate_error(msg))

    def _on_generate_done(self, path: str, voice_id: str):
        log.info("Generation done — %s", os.path.basename(path))
        self._generating = False
        self.progress.stop()
        self.progress["value"] = 0

        self.btn_generate.config_state("normal")
        self.btn_generate.config_text("✨  Generate Speech")
        self.btn_play.config_state("normal")
        self.btn_stop.config_state("normal")
        self.btn_save.config_state("normal")

        # Update output info card
        duration = len(self.audio_data) / self.sample_rate
        mins = int(duration // 60)
        secs = duration % 60
        self.output_name_label.config(text=os.path.basename(path),
                                      fg=C["text"])
        self.output_meta_label.config(
            text=f"24 kHz · WAV · {mins}:{secs:04.1f}s")
        self.out_check.config(text="✅")

        # Update voice status
        self.voice_status.config(text=f"🎙 {voice_id}")

        # Render waveform
        self.waveform.set_audio(self.audio_data, self.sample_rate)

        self._set_status(f"Done — saved to {os.path.basename(path)}", "ok")

    def _on_generate_error(self, msg: str):
        log.error("Generation error: %s", msg)
        self._generating = False
        self.progress.stop()
        self.progress["value"] = 0
        self.btn_generate.config_state("normal")
        self.btn_generate.config_text("✨  Generate Speech")
        self._set_status(f"Error: {msg}", "error")
        messagebox.showerror("Generation Failed", msg)

    # ── Playback ──────────────────────────────────────────────────────────────

    def _on_play(self):
        if self.audio_data is None:
            return
        self._stop_play.clear()
        self.btn_play.config_state("disabled")
        self.btn_stop.config_state("normal")
        self._set_status("Playing…", "busy")
        self.playback_thread = threading.Thread(
            target=self._play_worker, daemon=True)
        self.playback_thread.start()

    def _play_worker(self):
        log.info("Playback started")
        try:
            sd.play(self.audio_data, self.sample_rate)
            sd.wait()
            log.info("Playback finished")
        except Exception as exc:
            log.error("Playback error: %s", exc)
            self.root.after(0, lambda: self._set_status(f"Playback error: {exc}", "error"))
        self.root.after(0, self._on_play_done)

    def _on_play_done(self):
        self.btn_play.config_state("normal")
        self._set_status("Ready", "ok")

    def _on_stop(self):
        log.info("Playback stopped by user")
        sd.stop()
        self._stop_play.set()
        self.btn_play.config_state("normal" if self.audio_data is not None else "disabled")
        self._set_status("Stopped", "ok")

    # ── Save ─────────────────────────────────────────────────────────────────

    def _on_save(self):
        if self.audio_data is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
            initialfile="kokoro_output.wav",
            title="Save Audio As",
        )
        if path:
            sf.write(path, self.audio_data, self.sample_rate)
            log.info("Saved audio to %s", path)
            self._set_status(f"Saved → {os.path.basename(path)}", "ok")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, state: str = "ok"):
        colours = {
            "ok":    C["status_ok"],
            "error": C["status_err"],
            "busy":  C["status_busy"],
        }
        self.status_dot.config(fg=colours.get(state, C["status_ok"]))
        self.status_label.config(text=msg)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    app = KokoroApp(root)
    root.mainloop()
