import customtkinter as ctk
from ui.theme import C, FONT_TITLE, FONT_TINY


class TitleBar(ctk.CTkFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C["titlebar"], height=52,
                         corner_radius=0, **kwargs)
        self.pack_propagate(False)
        self._build()

    def _build(self):
        # Left: icon + title stack
        left = ctk.CTkFrame(self, fg_color=C["titlebar"])
        left.pack(side="left", padx=16, pady=8)

        icon_bg = ctk.CTkFrame(left, fg_color=C["accent"],
                               width=32, height=32, corner_radius=8)
        icon_bg.pack(side="left")
        icon_bg.pack_propagate(False)
        ctk.CTkLabel(icon_bg, text="🎙", font=("Segoe UI", 14),
                     fg_color=C["accent"]).place(relx=0.5, rely=0.5, anchor="center")

        title_col = ctk.CTkFrame(left, fg_color=C["titlebar"])
        title_col.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(title_col, text="Kokoro TTS", font=FONT_TITLE,
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(title_col, text="Text-to-Speech Studio", font=FONT_TINY,
                     text_color=C["text3"]).pack(anchor="w")

        # Right: badges
        right = ctk.CTkFrame(self, fg_color=C["titlebar"])
        right.pack(side="right", padx=16)

        ctk.CTkLabel(right, text="⚡ hexgrad/Kokoro-82M",
                     fg_color=C["surface2"], text_color=C["accent_h"],
                     font=FONT_TINY, corner_radius=20,
                     padx=10, pady=4).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(right, text="v1.0",
                     fg_color=C["surface2"], text_color=C["text3"],
                     font=FONT_TINY, corner_radius=20,
                     padx=10, pady=4).pack(side="left")
