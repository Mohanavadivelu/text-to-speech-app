import tkinter as tk
from ui.theme import C

# (label, accelerator, action-key) ; None = separator
_ITEMS = [
    ("Undo", "Ctrl+Z", "undo"), ("Redo", "Ctrl+Y", "redo"), None,
    ("Cut", "Ctrl+X", "cut"), ("Copy", "Ctrl+C", "copy"), ("Paste", "Ctrl+V", "paste"),
    ("Delete", "Del", "delete"), None,
    ("Select All", "Ctrl+A", "select_all"), None,
    ("Find…", "Ctrl+F", "find"), ("Replace…", "Ctrl+H", "replace"),
    ("Clean text", "", "clean"), None,
    ("Speak selection", "Ctrl+Enter", "speak_selection"),
    ("Clear all", "", "clear"),
]


class TextContextMenu:
    """Dark right-click menu for a tk.Text widget.

    *actions* maps action keys to callables for items the text widget can't do
    by itself (find, replace, clean, speak_selection, clear).
    """

    def __init__(self, text: tk.Text, actions: dict):
        self._text = text
        self._actions = actions
        self._menu = tk.Menu(text, tearoff=0, bg=C["surface2"], fg=C["text"],
                             activebackground=C["accent"], activeforeground="#ffffff",
                             disabledforeground=C["text3"], bd=1, relief="flat",
                             font=("Segoe UI", 10))
        self._index = {}
        for item in _ITEMS:
            if item is None:
                self._menu.add_separator()
                continue
            label, accel, key = item
            self._menu.add_command(label=label, accelerator=accel,
                                   command=lambda k=key: self._run(k))
            self._index[key] = self._menu.index("end")
        text.bind("<Button-3>", self._show, add="+")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _has_selection(self) -> bool:
        return bool(self._text.tag_ranges("sel"))

    def _clipboard_has_text(self) -> bool:
        try:
            return bool(self._text.clipboard_get())
        except tk.TclError:
            return False

    def _can(self, what: str) -> bool:
        try:
            return bool(int(self._text.tk.call(self._text._w, "edit", what)))
        except tk.TclError:
            return True

    def _show(self, event):
        editable = str(self._text.cget("state")) == "normal"
        has_text = bool(self._text.get("1.0", "end-1c").strip())
        sel = self._has_selection()
        enabled = {
            "undo": editable and self._can("canundo"),
            "redo": editable and self._can("canredo"),
            "cut": editable and sel, "copy": sel,
            "paste": editable and self._clipboard_has_text(),
            "delete": editable and sel, "select_all": has_text,
            "find": has_text, "replace": editable and has_text,
            "clean": editable and has_text, "speak_selection": sel,
            "clear": editable and has_text,
        }
        for key, idx in self._index.items():
            self._menu.entryconfigure(idx, state="normal" if enabled.get(key) else "disabled")
        self._text.focus_set()
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
        return "break"

    def _run(self, key: str):
        t = self._text
        virtual = {"undo": "<<Undo>>", "redo": "<<Redo>>", "cut": "<<Cut>>",
                   "copy": "<<Copy>>", "paste": "<<Paste>>", "select_all": "<<SelectAll>>"}
        if key in virtual:
            t.event_generate(virtual[key])
        elif key == "delete":
            if self._has_selection():
                t.delete("sel.first", "sel.last")
        elif key in self._actions:
            self._actions[key]()
