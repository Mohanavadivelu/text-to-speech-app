import ctypes
import time
import tkinter as tk
import customtkinter as ctk
from ui.theme import C, FONT_SMALL

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


def _round_corners(window):
    """Ask Windows 11 to round the popup's corners; silently ignored elsewhere."""
    try:
        hwnd = int(window.wm_frame(), 16)
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


class PopupMenu(tk.Toplevel):
    """Borderless menu drawn with the app's theme colours.

    items: list of (label, accelerator, enabled, callback) or None for a separator.
    Closes on click elsewhere, focus loss, Escape or after an item runs.
    Arrow keys move the highlight, Enter runs it.
    """

    def __init__(self, master, items, x, y):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=C["border2"])

        scale = ctk.ScalingTracker.get_window_scaling(master.winfo_toplevel())
        px = lambda v: max(1, int(round(v * scale)))
        self._rows = []        # (frame, label, accel_label, enabled, callback)
        self._active = -1
        self._closed = False
        self._opened_at = None

        body = tk.Frame(self, bg=C["surface2"], padx=px(4), pady=px(4))
        body.pack(fill="both", expand=True, padx=1, pady=1)
        body.grid_columnconfigure(0, weight=1)

        r = 0
        for item in items:
            if item is None:
                tk.Frame(body, bg=C["border"], height=1).grid(
                    row=r, column=0, sticky="ew", padx=px(8), pady=px(4))
                r += 1
                continue
            label, accel, enabled, callback = item
            fg = C["text"] if enabled else C["text3"]
            row = tk.Frame(body, bg=C["surface2"], cursor="hand2" if enabled else "arrow")
            row.grid(row=r, column=0, sticky="ew")
            row.grid_columnconfigure(0, weight=1)
            lbl = tk.Label(row, text=label, bg=C["surface2"], fg=fg, font=FONT_SMALL,
                           anchor="w", padx=px(12), pady=px(5))
            lbl.grid(row=0, column=0, sticky="ew")
            acc = tk.Label(row, text=accel, bg=C["surface2"], fg=C["text3"], font=FONT_SMALL,
                           anchor="e", padx=px(12), pady=px(5))
            acc.grid(row=0, column=1, sticky="e")
            idx = len(self._rows)
            self._rows.append((row, lbl, acc, enabled, callback))
            for w in (row, lbl, acc):
                w.bind("<Enter>", lambda _e, i=idx: self._highlight(i))
                w.bind("<Leave>", lambda _e, i=idx: self._highlight(-1) if self._active == i else None)
                w.bind("<ButtonRelease-1>", lambda _e, i=idx: self._activate(i))
            r += 1

        # Place on screen, flipping left/up near the edges
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sx, sy = self.winfo_vrootx(), self.winfo_vrooty()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if x + w > sx + sw:
            x = max(sx, x - w)
        if y + h > sy + sh:
            y = max(sy, y - h)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        _round_corners(self)
        self.lift()
        self.focus_force()
        self._opened_at = time.monotonic()

        self.bind("<Escape>", lambda _e: self.close())
        self.bind("<FocusOut>", lambda _e: self.after(10, self._close_if_unfocused))
        self.bind("<Up>", lambda _e: self._move(-1))
        self.bind("<Down>", lambda _e: self._move(+1))
        self.bind("<Return>", lambda _e: self._activate(self._active))
        # Clicking anywhere else in the app closes the menu
        self._root_click = master.winfo_toplevel().bind("<Button>", self._on_root_click, add="+")

    # ── behaviour ─────────────────────────────────────────────────────────────

    def _highlight(self, idx):
        if self._active >= 0:
            row, lbl, acc, enabled, _cb = self._rows[self._active]
            for w in (row, lbl, acc):
                w.configure(bg=C["surface2"])
            lbl.configure(fg=C["text"] if enabled else C["text3"])
            acc.configure(fg=C["text3"])
        self._active = -1
        if idx >= 0 and self._rows[idx][3]:
            row, lbl, acc, _enabled, _cb = self._rows[idx]
            for w in (row, lbl, acc):
                w.configure(bg=C["accent"])
            lbl.configure(fg="#ffffff")
            acc.configure(fg="#e6dcff")
            self._active = idx

    def _move(self, step):
        enabled = [i for i, r in enumerate(self._rows) if r[3]]
        if not enabled:
            return
        if self._active not in enabled:
            target = enabled[0] if step > 0 else enabled[-1]
        else:
            target = enabled[(enabled.index(self._active) + step) % len(enabled)]
        self._highlight(target)

    def _activate(self, idx):
        if idx < 0 or not self._rows[idx][3]:
            return
        callback = self._rows[idx][4]
        self.close()
        callback()

    def _on_root_click(self, event):
        if not self._closed and event.widget.winfo_toplevel() is not self:
            self.close()

    def _close_if_unfocused(self):
        if self._closed:
            return
        # Windows may refuse focus right after opening (e.g. app not in the
        # foreground); that spurious focus-out must not close the menu.
        if self._opened_at is not None and time.monotonic() - self._opened_at < 0.4:
            return
        focus = self.focus_get()
        if focus is None or focus.winfo_toplevel() is not self:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.master.winfo_toplevel().unbind("<Button>", self._root_click)
        except Exception:
            pass
        self.destroy()


class TextContextMenu:
    """Themed right-click menu for a tk.Text widget.

    *actions* maps action keys to callables for items the text widget can't do
    by itself (find, replace, clean, speak_selection, clear).
    """

    def __init__(self, text: tk.Text, actions: dict):
        self._text = text
        self._actions = actions
        self._popup = None
        text.bind("<Button-3>", self._show, add="+")
        text.bind("<Shift-F10>", self._show_at_cursor, add="+")
        text.bind("<App>", self._show_at_cursor, add="+")

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

    def _enabled_states(self) -> dict:
        editable = str(self._text.cget("state")) == "normal"
        has_text = bool(self._text.get("1.0", "end-1c").strip())
        sel = self._has_selection()
        return {
            "undo": editable and self._can("canundo"),
            "redo": editable and self._can("canredo"),
            "cut": editable and sel, "copy": sel,
            "paste": editable and self._clipboard_has_text(),
            "delete": editable and sel, "select_all": has_text,
            "find": has_text, "replace": editable and has_text,
            "clean": editable and has_text, "speak_selection": sel,
            "clear": editable and has_text,
        }

    def _show(self, event):
        self.open_at(event.x_root, event.y_root)
        return "break"

    def _show_at_cursor(self, _event=None):
        bbox = self._text.bbox("insert")
        x, y = (bbox[0], bbox[1] + bbox[3]) if bbox else (10, 10)
        self.open_at(self._text.winfo_rootx() + x, self._text.winfo_rooty() + y)
        return "break"

    def open_at(self, x: int, y: int):
        if self._popup is not None and self._popup.winfo_exists():
            self._popup.close()
        enabled = self._enabled_states()
        items = [None if it is None else
                 (it[0], it[1], enabled.get(it[2], False), lambda k=it[2]: self._run(k))
                 for it in _ITEMS]
        self._text.focus_set()
        self._popup = PopupMenu(self._text, items, x, y)

    def _run(self, key: str):
        t = self._text
        t.focus_set()
        virtual = {"undo": "<<Undo>>", "redo": "<<Redo>>", "cut": "<<Cut>>",
                   "copy": "<<Copy>>", "paste": "<<Paste>>", "select_all": "<<SelectAll>>"}
        if key in virtual:
            t.event_generate(virtual[key])
        elif key == "delete":
            if self._has_selection():
                t.delete("sel.first", "sel.last")
        elif key in self._actions:
            self._actions[key]()
