import customtkinter as ctk
from ui.theme import C, FONT_SUBLABEL, FONT_TINY, FONT_LABEL, FONT_MONO


class TextPanel(ctk.CTkFrame):
    """Left panel: text input area + generate button."""

    def __init__(self, parent, on_generate=None, **kwargs):
        super().__init__(parent, fg_color=C["surface"],
                         border_color=C["border"], border_width=1,
                         corner_radius=12, **kwargs)
        self._on_generate = on_generate
        self._build()

    def _build(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header label — directly on the parent so rounded corners stay visible
        ctk.CTkLabel(self, text="📝  Text Input", font=FONT_SUBLABEL,
                     text_color=C["text2"], fg_color=C["surface"],
                     anchor="w").grid(row=0, column=0, sticky="ew",
                                      padx=14, pady=(12, 8))

        # Divider
        ctk.CTkFrame(self, fg_color=C["border"], height=1,
                     corner_radius=0).grid(row=1, column=0, sticky="ew")

        # CTkTextbox — built-in dark-themed scrollbar
        self.text_input = ctk.CTkTextbox(
            self, font=FONT_MONO,
            fg_color=C["surface2"], text_color=C["text"],
            border_color=C["border"], border_width=1,
            scrollbar_button_color=C["surface3"],
            scrollbar_button_hover_color=C["border2"],
            corner_radius=8, wrap="word",
            activate_scrollbars=True,
        )
        self.text_input.grid(row=2, column=0, sticky="nsew", padx=12, pady=(10, 4))
        self.text_input.bind("<KeyRelease>", self._on_text_change)
        self.text_input.bind("<Control-Return>", lambda _e: self._fire_generate())

        # Footer
        footer = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0)
        footer.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 12))

        self._char_label = ctk.CTkLabel(footer, text="Characters: 0",
                                        font=FONT_TINY, text_color=C["text3"])
        self._char_label.pack(side="left")

        self.btn_generate = ctk.CTkButton(
            footer, text="✨  Generate Speech",
            font=FONT_LABEL,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="#ffffff", corner_radius=50,
            command=self._fire_generate,
        )
        self.btn_generate.pack(side="right")

    def _on_text_change(self, _event=None):
        text = self.text_input.get("1.0", "end-1c")
        n = len(text)
        est = max(1, n // 15) if n > 0 else 0
        est_str = f" · ~{est}s estimated" if n > 0 else ""
        self._char_label.configure(text=f"Characters: {n:,}{est_str}")

    def _fire_generate(self):
        if self._on_generate:
            self._on_generate()

    def get_text(self) -> str:
        return self.text_input.get("1.0", "end-1c").strip()

    def set_generating(self, generating: bool, progress_pct: int = 0):
        if generating:
            self.btn_generate.configure(state="disabled",
                                        text=f"⏳  Generating… {progress_pct}%")
            self.text_input.configure(state="disabled", fg_color=C["surface3"])
        else:
            self.btn_generate.configure(state="normal", text="✨  Generate Speech")
            self.text_input.configure(state="normal", fg_color=C["surface2"])
