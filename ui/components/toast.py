import customtkinter as ctk
from ui.theme import C, FONT_SMALL


class Toast:
    """Floating toast that slides up from the bottom and auto-dismisses."""

    _KIND = {
        "error": {"bg": "#1a1010", "border": C["status_err"], "icon": "🔴", "fg": C["status_err"]},
        "info":  {"bg": C["surface3"], "border": C["border2"],  "icon": "💡", "fg": C["text"]},
    }

    def __init__(self, root: ctk.CTk, message: str, kind: str = "info"):
        cfg = self._KIND.get(kind, self._KIND["info"])
        self._root = root

        root.update_idletasks()
        rw, rh = root.winfo_width(), root.winfo_height()
        if rw < 100:   # window not yet drawn — use fallback size
            rw = 980
        if rh < 100:
            rh = 680
        fw, fh = 340, 48
        x = (rw - fw) // 2
        self._x, self._fw, self._fh = x, fw, fh

        self._frame = ctk.CTkFrame(root, fg_color=cfg["bg"],
                                   border_color=cfg["border"], border_width=1,
                                   corner_radius=8, width=fw, height=fh)
        ctk.CTkLabel(self._frame, text=cfg["icon"],
                     font=("Segoe UI", 14)).pack(side="left", padx=(10, 4), pady=10)
        ctk.CTkLabel(self._frame, text=message, font=FONT_SMALL,
                     text_color=cfg["fg"]).pack(side="left", padx=(0, 14), pady=10)
        self._frame.bind("<Button-1>", lambda _e: self._dismiss())

        self._frame.place(x=x, y=rh)
        self._slide(rh, rh - fh - 40)

    def _slide(self, y, target):
        if y > target:
            y -= 4
            self._frame.place(x=self._x, y=y)
            self._frame.after(10, lambda: self._slide(y, target))
        else:
            self._frame.after(4000, self._dismiss)

    def _dismiss(self):
        try:
            self._frame.place_forget()
            self._frame.destroy()
        except Exception:
            pass
