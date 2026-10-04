import customtkinter as ctk
from ui.theme import C, FONT_TINY, FONT_SMALL


class StatusBar(ctk.CTkFrame):
    """28 px status bar at the bottom of the window."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C["titlebar"], height=28,
                         border_color=C["border"], border_width=1,
                         corner_radius=0, **kwargs)
        self.pack_propagate(False)
        self._pulse_after = None
        self._build()

    def _build(self):
        inner = ctk.CTkFrame(self, fg_color=C["titlebar"])
        # Extra right padding: a maximized Windows window extends ~11 px past
        # the screen edge, which hid the end of the device label.
        inner.pack(fill="x", padx=(14, 28), pady=0)

        self._dot = ctk.CTkLabel(inner, text="●", font=FONT_TINY,
                                 text_color=C["status_ok"])
        self._dot.pack(side="left", padx=(0, 4))

        self._msg = ctk.CTkLabel(inner, text="Ready", font=FONT_SMALL,
                                 text_color=C["text2"])
        self._msg.pack(side="left")

        # Right side
        right = ctk.CTkFrame(inner, fg_color=C["titlebar"])
        right.pack(side="right")

        from core.engine import DEVICE
        import torch
        if DEVICE == "cuda":
            # Shorten to "CUDA · RTX 3050 Ti" style (strip "NVIDIA GeForce " prefix)
            full = torch.cuda.get_device_name(0)
            short = full.replace("NVIDIA GeForce ", "").replace(" Laptop GPU", "")
            dev_info = f"CUDA · {short}"
        else:
            import os
            dev_info = f"CPU · {os.cpu_count()} threads"
        # Icon and text are separate labels: Tk under-measures the emoji's
        # width, which clipped the last letter when they shared one label.
        ctk.CTkLabel(right, text=dev_info, font=FONT_TINY,
                     text_color=C["text3"]).pack(side="right", padx=(0, 2))
        ctk.CTkLabel(right, text="🖥", font=FONT_TINY,
                     text_color=C["text3"]).pack(side="right", padx=(0, 6))

    def set_status(self, message: str, state: str = "ok"):
        colours = {"ok": C["status_ok"], "busy": C["status_busy"], "error": C["status_err"]}
        colour = colours.get(state, C["status_ok"])
        self._dot.configure(text_color=colour)
        self._msg.configure(text=message, text_color=C["text2"] if state == "ok" else colour)

        if self._pulse_after:
            self.after_cancel(self._pulse_after)
            self._pulse_after = None

        if state == "busy":
            self._pulse(colour, True)

    def _pulse(self, colour: str, show: bool):
        try:
            self._dot.configure(text_color=colour if show else C["titlebar"])
            self._pulse_after = self.after(500, lambda: self._pulse(colour, not show))
        except Exception:
            # Widget destroyed (window closed) — stop pulsing silently
            self._pulse_after = None
