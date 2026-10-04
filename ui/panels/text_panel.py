import os
import re
import tkinter as tk
import customtkinter as ctk
from ui.theme import C, FONT_SUBLABEL, FONT_TINY, FONT_LABEL, FONT_SMALL
from ui.components.context_menu import TextContextMenu
from ui.components.find_bar import FindBar
from ui.components.text_undo import single_undo_step
from core import text_tools

FONT_FAMILY = "Consolas"
FONT_SIZE_DEFAULT, FONT_SIZE_MIN, FONT_SIZE_MAX = 11, 8, 28

_PLACEHOLDER = ("Type or paste text here, or drop a .txt, .docx or .pdf file.\n"
                "Ctrl+Enter to generate  ·  Right-click for more options")


class TextPanel(ctk.CTkFrame):
    """Left panel: text editor with toolbar, find/replace, counts and generate."""

    def __init__(self, parent, on_generate=None, on_cancel=None, on_open=None,
                 on_pronunciations=None, on_change=None, estimate_context=None, **kwargs):
        super().__init__(parent, fg_color=C["surface"],
                         border_color=C["border"], border_width=1,
                         corner_radius=12, **kwargs)
        self._on_generate = on_generate
        self._on_cancel = on_cancel
        self._on_open = on_open
        self._on_pronunciations = on_pronunciations
        self._on_change = on_change
        self._estimate_context = estimate_context or (lambda: ("a", 1.0))
        self._generating = False
        self._font_size = FONT_SIZE_DEFAULT
        self._find_refresh_after = None
        self._build()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header: title + toolbar
        header = ctk.CTkFrame(self, fg_color=C["surface"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 6))
        ctk.CTkLabel(header, text="📝  Text Input", font=FONT_SUBLABEL,
                     text_color=C["text2"]).pack(side="left")
        tool_kw = dict(height=26, corner_radius=6, font=FONT_SMALL, fg_color="transparent",
                       hover_color=C["surface3"], text_color=C["text2"])
        self._tool_buttons = {}
        for key, label, cmd in (("clear", "Clear", self.clear),
                                ("pron", "Pronunciations", self._fire_pronunciations),
                                ("find", "Find", lambda: self.open_find(False)),
                                ("clean", "Clean text", self.clean),
                                ("open", "Open…", self._fire_open)):
            b = ctk.CTkButton(header, text=label, width=10, command=cmd, **tool_kw)
            b.pack(side="right", padx=(4, 0))
            self._tool_buttons[key] = b

        ctk.CTkFrame(self, fg_color=C["border"], height=1,
                     corner_radius=0).grid(row=1, column=0, sticky="ew")

        # Editor
        self.text_input = ctk.CTkTextbox(
            self, font=(FONT_FAMILY, self._font_size),
            fg_color=C["surface2"], text_color=C["text"],
            border_color=C["border"], border_width=1,
            scrollbar_button_color=C["surface3"], scrollbar_button_hover_color=C["border2"],
            corner_radius=8, wrap="word", activate_scrollbars=True,
            undo=True, autoseparators=True, maxundo=-1,
        )
        self.text_input.grid(row=3, column=0, sticky="nsew", padx=12, pady=(10, 4))
        self._tk_text = t = self.text_input._textbox
        t.configure(insertbackground=C["text"], selectbackground=C["accent"],
                    selectforeground="#ffffff", inactiveselectbackground=C["border2"])

        # Find / replace bar (row 2, hidden until opened)
        self._find_bar = FindBar(self, t, on_close=self._hide_find)

        # Placeholder overlay
        self._placeholder = ctk.CTkLabel(self.text_input, text=_PLACEHOLDER, justify="left",
                                         anchor="nw", fg_color=C["surface2"],
                                         text_color=C["text3"], font=FONT_SMALL)
        self._placeholder.place(x=10, y=8)
        self._placeholder.bind("<Button-1>", lambda _e: t.focus_set())

        # Bindings
        t.bind("<<Modified>>", self._on_modified, add="+")
        t.bind("<<Selection>>", lambda _e: self.refresh_counts(), add="+")
        t.bind("<<TextReplaced>>", lambda _e: self._after_programmatic_edit(), add="+")
        t.bind("<Control-Return>", lambda _e: (self._fire_generate(), "break")[1])
        t.bind("<Control-BackSpace>", self._delete_word_left)
        t.bind("<Control-Delete>", self._delete_word_right)
        t.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        for seq in ("<Control-equal>", "<Control-plus>", "<Control-KP_Add>"):
            t.bind(seq, lambda _e: (self.zoom(+1), "break")[1])
        for seq in ("<Control-minus>", "<Control-KP_Subtract>"):
            t.bind(seq, lambda _e: (self.zoom(-1), "break")[1])
        t.bind("<Control-Key-0>", lambda _e: (self.set_font_size(FONT_SIZE_DEFAULT), "break")[1])

        self._menu = TextContextMenu(t, {
            "find": lambda: self.open_find(False), "replace": lambda: self.open_find(True),
            "clean": self.clean, "speak_selection": self._fire_generate, "clear": self.clear,
        })

        # Footer
        footer = ctk.CTkFrame(self, fg_color=C["surface"], corner_radius=0)
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=(2, 12))
        self._char_label = ctk.CTkLabel(footer, text="", font=FONT_TINY, text_color=C["text3"])
        self._char_label.pack(side="left")
        self.btn_generate = ctk.CTkButton(
            footer, text="✨  Generate Speech", font=FONT_LABEL, width=180,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="#ffffff", corner_radius=50, command=self._on_button,
        )
        self.btn_generate.pack(side="right")
        self.refresh_counts()

    # ── events ────────────────────────────────────────────────────────────────

    def _on_modified(self, _event=None):
        if not self._tk_text.edit_modified():
            return
        self._tk_text.edit_modified(False)
        self.refresh_counts()
        if self._find_bar.winfo_ismapped():
            if self._find_refresh_after:
                self.after_cancel(self._find_refresh_after)
            self._find_refresh_after = self.after(300, self._find_bar.refresh)
        if self._on_change:
            self._on_change()

    def _after_programmatic_edit(self):
        self._tk_text.edit_modified(True)
        self._on_modified()

    def _on_button(self):
        if self._generating:
            if self._on_cancel:
                self._on_cancel()
        else:
            self._fire_generate()

    def _fire_generate(self):
        if not self._generating and self._on_generate:
            self._on_generate()

    def _fire_open(self):
        if self._on_open and not self._generating:
            self._on_open()

    def _fire_pronunciations(self):
        if self._on_pronunciations:
            self._on_pronunciations()

    def _delete_word_left(self, _event=None):
        t = self._tk_text
        if self._editable():
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            else:
                before = t.get("insert linestart", "insert")
                m = re.search(r"(\w+|[^\w\s]+)?\s*$", before)
                n = len(m.group(0)) if m and m.group(0) else 1
                t.delete(f"insert-{n}c", "insert")
        return "break"

    def _delete_word_right(self, _event=None):
        t = self._tk_text
        if self._editable():
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            else:
                after = t.get("insert", "insert lineend")
                m = re.match(r"\s*(\w+|[^\w\s]+)?", after)
                n = len(m.group(0)) if m and m.group(0) else 1
                t.delete("insert", f"insert+{n}c")
        return "break"

    def _on_ctrl_wheel(self, event):
        self.zoom(+1 if event.delta > 0 else -1)
        return "break"

    def _hide_find(self):
        self._find_bar.grid_remove()

    def _editable(self) -> bool:
        return str(self._tk_text.cget("state")) == "normal"

    # ── public API ────────────────────────────────────────────────────────────

    def refresh_counts(self):
        text = self._tk_text.get("1.0", "end-1c")
        empty = not text
        if empty:
            self._placeholder.place(x=10, y=8)
        else:
            self._placeholder.place_forget()
        lang, speed = self._estimate_context()
        sel = self._selected_text()
        if empty:
            info = "No text yet"
        else:
            secs = text_tools.estimate_seconds(text, lang, speed)
            info = (f"{len(text):,} characters  ·  {text_tools.count_words(text):,} words  ·  "
                    f"~{text_tools.format_duration(secs)} of audio")
            if sel:
                info += f"  ·  {len(sel):,} selected"
        self._char_label.configure(text=info)
        if not self._generating:
            self.btn_generate.configure(
                text="✨  Generate Selection" if sel.strip() else "✨  Generate Speech")
        for key in ("clear", "find", "clean"):
            self._tool_buttons[key].configure(state="disabled" if empty or (
                self._generating and key != "find") else "normal")

    def _selected_text(self) -> str:
        try:
            return self._tk_text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def get_text(self) -> str:
        return self._tk_text.get("1.0", "end-1c").strip()

    def get_generate_text(self):
        """Return (text, is_selection): the selection if any, else everything."""
        sel = self._selected_text().strip()
        if sel:
            return sel, True
        return self.get_text(), False

    def set_text(self, text: str):
        """Replace all text as one undoable step (Ctrl+Z restores the old text)."""
        t = self._tk_text
        with single_undo_step(t):
            t.delete("1.0", "end")
            t.insert("1.0", text)
        t.mark_set("insert", "1.0")
        t.see("1.0")
        self._after_programmatic_edit()

    def insert_text(self, text: str):
        t = self._tk_text
        with single_undo_step(t):
            if t.tag_ranges("sel"):
                t.delete("sel.first", "sel.last")
            t.insert("insert", text)
        self._after_programmatic_edit()

    def load_draft(self, text: str):
        """Restore a saved draft without making it undoable."""
        t = self._tk_text
        t.insert("1.0", text)
        t.edit_reset()
        t.edit_modified(False)
        self.refresh_counts()

    def clean(self) -> bool:
        """Clean the selection (or all text). Returns True if anything changed."""
        if not self._editable():
            return False
        t = self._tk_text
        if t.tag_ranges("sel"):
            start, end = t.index("sel.first"), t.index("sel.last")
        else:
            start, end = "1.0", "end-1c"
        old = t.get(start, end)
        new = text_tools.clean_text(old)
        if new == old:
            return False
        with single_undo_step(t):
            t.delete(start, end)
            t.insert(start, new)
        self._after_programmatic_edit()
        return True

    def clear(self):
        if self._editable() and self.get_text():
            t = self._tk_text
            with single_undo_step(t):
                t.delete("1.0", "end")
            self._after_programmatic_edit()
            t.focus_set()

    def open_find(self, replace: bool = False):
        if not self.get_text():
            return
        self._find_bar.grid(row=2, column=0, sticky="ew", padx=12, pady=(10, 0))
        self._find_bar.open(replace=replace and self._editable())

    @property
    def font_size(self) -> int:
        return self._font_size

    def set_font_size(self, size: int, notify: bool = True):
        size = max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, int(size)))
        if size != self._font_size:
            self._font_size = size
            self.text_input.configure(font=(FONT_FAMILY, size))
            if notify and self._on_change:
                self._on_change()

    def zoom(self, step: int):
        self.set_font_size(self._font_size + step)

    def enable_drop(self, on_files):
        """Accept dropped files (and dropped text). Needs tkinterdnd2 on the root."""
        try:
            from tkinterdnd2 import DND_FILES, DND_TEXT
        except ImportError:
            return False
        t = self._tk_text

        def _drop(event):
            if self._generating or not event.data:
                return event.action
            try:
                paths = list(t.tk.splitlist(event.data))
            except tk.TclError:
                paths = []
            if paths and all(os.path.isfile(p) for p in paths):
                on_files(paths)
            else:
                self.insert_text(event.data)   # dropped text, e.g. from a browser
            return event.action

        try:
            t.drop_target_register(DND_FILES, DND_TEXT)
            t.dnd_bind("<<Drop>>", _drop)
            return True
        except Exception:
            return False

    def set_generating(self, generating: bool, progress_pct: int = 0):
        """While generating, the button turns into Cancel and the text is locked."""
        self._generating = generating
        if generating:
            self.btn_generate.configure(state="normal", text=f"■  Cancel  ·  {progress_pct}%",
                                        fg_color=C["btn_stop"], hover_color="#f06a6a")
            self.text_input.configure(state="disabled", fg_color=C["surface3"])
            self._placeholder.configure(fg_color=C["surface3"])
        else:
            self.btn_generate.configure(state="normal", fg_color=C["accent"],
                                        hover_color=C["accent_h"])
            self.text_input.configure(state="normal", fg_color=C["surface2"])
            self._placeholder.configure(fg_color=C["surface2"])
        self._tool_buttons["open"].configure(state="disabled" if generating else "normal")
        self.refresh_counts()

    def set_cancelling(self):
        self.btn_generate.configure(state="disabled", text="Cancelling…")
