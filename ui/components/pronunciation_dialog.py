import customtkinter as ctk
from ui.theme import C, FONT_SMALL, FONT_TINY, FONT_LABEL, FONT_SUBLABEL
from core import text_tools


class PronunciationDialog(ctk.CTkToplevel):
    """Edit the word -> "say it like" list applied before speech generation."""

    def __init__(self, master, on_saved=None, on_test=None):
        super().__init__(master)
        self.title("Pronunciations")
        self.configure(fg_color=C["surface"])
        self.geometry("560x520")
        self.minsize(480, 360)
        self.transient(master)
        self._on_saved = on_saved
        self._on_test = on_test
        self._rows: list[tuple[ctk.CTkFrame, ctk.CTkEntry, ctk.CTkEntry]] = []
        self._build()
        for entry in text_tools.load_pronunciations():
            self._add_row(entry["word"], entry["say"])
        if not self._rows:
            self._add_row()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(100, self._focus)

    def _focus(self):
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except Exception:
            pass

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text="Pronunciations", font=FONT_SUBLABEL, text_color=C["text"],
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            self, justify="left", anchor="w", font=FONT_TINY, text_color=C["text2"], wraplength=520,
            text=("Words are replaced (whole word, any case) before speaking. Write how it should "
                  "sound, e.g. Kokoro → Koh-koh-roh. Advanced: phonemes between slashes, e.g. "
                  "/kˈOkəɹO/, work with English voices only."),
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        self._list = ctk.CTkScrollableFrame(self, fg_color=C["surface2"], corner_radius=8)
        self._list.grid(row=2, column=0, sticky="nsew", padx=16)
        self._list.grid_columnconfigure((0, 1), weight=1)
        hdr = ctk.CTkFrame(self._list, fg_color=C["surface2"])
        hdr.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(2, 4))
        hdr.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(hdr, text="WORD", font=FONT_TINY, text_color=C["text3"], anchor="w").grid(row=0, column=0, sticky="w", padx=4)
        ctk.CTkLabel(hdr, text="SAY IT LIKE", font=FONT_TINY, text_color=C["text3"], anchor="w").grid(row=0, column=1, sticky="w", padx=4)

        bottom = ctk.CTkFrame(self, fg_color=C["surface"])
        bottom.grid(row=3, column=0, sticky="ew", padx=16, pady=12)
        ctk.CTkButton(bottom, text="+ Add word", font=FONT_SMALL, width=100,
                      fg_color=C["surface3"], hover_color=C["border2"], text_color=C["text"],
                      command=lambda: self._add_row(focus=True)).pack(side="left")
        ctk.CTkButton(bottom, text="Save", font=FONT_LABEL, width=90, fg_color=C["accent"],
                      hover_color=C["accent_h"], command=self._save).pack(side="right")
        ctk.CTkButton(bottom, text="Cancel", font=FONT_SMALL, width=80, fg_color="transparent",
                      border_color=C["border2"], border_width=1, hover_color=C["surface3"],
                      text_color=C["text2"], command=self.destroy).pack(side="right", padx=(0, 8))

    def _add_row(self, word: str = "", say: str = "", focus: bool = False):
        row = ctk.CTkFrame(self._list, fg_color=C["surface2"])
        row.grid(row=len(self._rows) + 1, column=0, columnspan=4, sticky="ew", pady=2)
        row.grid_columnconfigure((0, 1), weight=1)
        kw = dict(fg_color=C["surface"], border_color=C["border"], text_color=C["text"],
                  corner_radius=6, height=28, font=FONT_SMALL)
        w = ctk.CTkEntry(row, placeholder_text="Word", **kw)
        s = ctk.CTkEntry(row, placeholder_text="Say it like", **kw)
        w.grid(row=0, column=0, sticky="ew", padx=(4, 4))
        s.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        if word:
            w.insert(0, word)
        if say:
            s.insert(0, say)
        btn = dict(height=28, corner_radius=6, fg_color=C["surface3"], hover_color=C["border2"],
                   text_color=C["text"], font=FONT_SMALL)
        if self._on_test:
            ctk.CTkButton(row, text="Test", width=44, command=lambda: self._test(w, s), **btn).grid(row=0, column=2, padx=(0, 4))
        ctk.CTkButton(row, text="✕", width=28, command=lambda: self._remove(row), **btn).grid(row=0, column=3, padx=(0, 4))
        self._rows.append((row, w, s))
        if focus:
            w.focus_set()

    def _remove(self, row):
        self._rows = [r for r in self._rows if r[0] is not row]
        row.destroy()

    def _test(self, word_entry, say_entry):
        word, say = word_entry.get().strip(), say_entry.get().strip()
        if not say or not self._on_test:
            return
        # Phonemes need Kokoro's [word](/phonemes/) markup to be spoken correctly
        is_phonemes = len(say) > 2 and say.startswith("/") and say.endswith("/")
        self._on_test(f"[{word or 'word'}]({say})" if is_phonemes else say)

    def entries(self) -> list[dict]:
        seen, out = set(), []
        for _row, w, s in self._rows:
            word, say = w.get().strip(), s.get().strip()
            if word and say and word.lower() not in seen:
                seen.add(word.lower())
                out.append({"word": word, "say": say})
        return out

    def _save(self):
        entries = self.entries()
        text_tools.save_pronunciations(entries)
        if self._on_saved:
            self._on_saved(entries)
        self.destroy()
