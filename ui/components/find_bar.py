import tkinter as tk
import customtkinter as ctk
from ui.theme import C, FONT_SMALL, FONT_TINY
from ui.components.text_undo import single_undo_step

_MAX_HIGHLIGHTS = 5000


class FindBar(ctk.CTkFrame):
    """Find / replace bar for a tk.Text widget (case-insensitive)."""

    def __init__(self, master, text: tk.Text, on_close=None, **kwargs):
        super().__init__(master, fg_color=C["surface2"], corner_radius=8,
                         border_color=C["border"], border_width=1, **kwargs)
        self._text = text
        self._on_close = on_close
        self._matches: list[tuple[str, str]] = []
        self._current = -1
        self._replace_mode = False
        self._refresh_after = None

        text.tag_configure("find_match", background="#4a3d1a")
        text.tag_configure("find_current", background="#b8860b", foreground="#ffffff")
        text.tag_raise("find_current")
        text.tag_raise("sel")

        self.grid_columnconfigure(0, weight=1)
        entry_kw = dict(fg_color=C["surface"], border_color=C["border"], text_color=C["text"],
                        corner_radius=6, height=28, font=FONT_SMALL)
        btn_kw = dict(fg_color=C["surface3"], hover_color=C["border2"], text_color=C["text"],
                      corner_radius=6, height=28, font=FONT_SMALL)

        self.find_entry = ctk.CTkEntry(self, placeholder_text="Find", **entry_kw)
        self.find_entry.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=6)
        self._count = ctk.CTkLabel(self, text="", font=FONT_TINY, text_color=C["text3"], width=70)
        self._count.grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(self, text="↑", width=30, command=self.prev, **btn_kw).grid(row=0, column=2, padx=(0, 4))
        ctk.CTkButton(self, text="↓", width=30, command=self.next, **btn_kw).grid(row=0, column=3, padx=(0, 4))
        ctk.CTkButton(self, text="✕", width=30, command=self.close, **btn_kw).grid(row=0, column=4, padx=(0, 8))

        self.replace_entry = ctk.CTkEntry(self, placeholder_text="Replace with", **entry_kw)
        self._replace_btn = ctk.CTkButton(self, text="Replace", width=70, command=self.replace_one, **btn_kw)
        self._replace_all_btn = ctk.CTkButton(self, text="All", width=40, command=self.replace_all, **btn_kw)

        for entry in (self.find_entry, self.replace_entry):
            entry.bind("<Escape>", lambda _e: (self.close(), "break")[1])
            entry.bind("<Shift-Return>", lambda _e: (self.prev(), "break")[1])
        self.find_entry.bind("<Return>", lambda _e: (self.next(), "break")[1])
        self.replace_entry.bind("<Return>", lambda _e: (self.replace_one(), "break")[1])
        self.find_entry.bind("<KeyRelease>", self._on_query_changed)

    # ── public API ────────────────────────────────────────────────────────────

    def open(self, replace: bool = False):
        self._replace_mode = replace
        if replace:
            self.replace_entry.grid(row=1, column=0, sticky="ew", padx=(8, 6), pady=(0, 6))
            self._replace_btn.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 4), pady=(0, 6))
            self._replace_all_btn.grid(row=1, column=3, columnspan=2, sticky="ew", padx=(0, 8), pady=(0, 6))
        else:
            for w in (self.replace_entry, self._replace_btn, self._replace_all_btn):
                w.grid_remove()
        # Pre-fill with the selected text when it is short and on one line
        try:
            sel = self._text.get("sel.first", "sel.last")
            if sel and "\n" not in sel and len(sel) < 100:
                self.find_entry.delete(0, "end")
                self.find_entry.insert(0, sel)
        except tk.TclError:
            pass
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")
        self.refresh()

    def close(self):
        self._clear_tags()
        self._matches, self._current = [], -1
        if self._on_close:
            self._on_close()
        self._text.focus_set()

    def refresh(self):
        """Re-scan the text (call after the text changes while the bar is open)."""
        query = self.find_entry.get()
        self._clear_tags()
        self._matches = []
        if query:
            start = "1.0"
            count = tk.IntVar()
            while len(self._matches) < _MAX_HIGHLIGHTS:
                pos = self._text.search(query, start, stopindex="end", nocase=True, count=count)
                if not pos or count.get() == 0:
                    break
                end = f"{pos}+{count.get()}c"
                self._matches.append((pos, end))
                self._text.tag_add("find_match", pos, end)
                start = end
        insert = self._text.index("insert")
        self._current = next((i for i, (s, _e) in enumerate(self._matches)
                              if self._text.compare(s, ">=", insert)), 0) if self._matches else -1
        self._show_current(scroll=False)

    def next(self):
        if self._matches:
            self._current = (self._current + 1) % len(self._matches)
            self._show_current()

    def prev(self):
        if self._matches:
            self._current = (self._current - 1) % len(self._matches)
            self._show_current()

    def replace_one(self):
        if not self._editable() or not self._matches or self._current < 0:
            return
        start, end = self._matches[self._current]
        with single_undo_step(self._text):
            self._text.delete(start, end)
            self._text.insert(start, self.replace_entry.get())
        self._text.mark_set("insert", f"{start}+{len(self.replace_entry.get())}c")
        self.refresh()
        self._text.event_generate("<<TextReplaced>>")

    def replace_all(self) -> int:
        if not self._editable() or not self._matches:
            return 0
        new = self.replace_entry.get()
        with single_undo_step(self._text):
            for start, end in reversed(self._matches):
                self._text.delete(start, end)
                self._text.insert(start, new)
        n = len(self._matches)
        self.refresh()
        self._count.configure(text=f"Replaced {n}")
        self._text.event_generate("<<TextReplaced>>")
        return n

    # ── internals ─────────────────────────────────────────────────────────────

    def _editable(self) -> bool:
        return str(self._text.cget("state")) == "normal"

    def _on_query_changed(self, event=None):
        if event is not None and event.keysym in ("Return", "Escape", "Shift_L", "Shift_R"):
            return
        if self._refresh_after:
            self.after_cancel(self._refresh_after)
        self._refresh_after = self.after(150, self.refresh)

    def _clear_tags(self):
        self._text.tag_remove("find_match", "1.0", "end")
        self._text.tag_remove("find_current", "1.0", "end")

    def _show_current(self, scroll: bool = True):
        self._text.tag_remove("find_current", "1.0", "end")
        if not self.find_entry.get():
            self._count.configure(text="")
            return
        if not self._matches:
            self._count.configure(text="No results")
            return
        start, end = self._matches[self._current]
        self._text.tag_add("find_current", start, end)
        if scroll:
            self._text.see(start)
            self._text.mark_set("insert", end)
        more = "+" if len(self._matches) >= _MAX_HIGHLIGHTS else ""
        self._count.configure(text=f"{self._current + 1} of {len(self._matches)}{more}")
