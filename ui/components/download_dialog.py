import threading
import customtkinter as ctk
from ui.theme import C, FONT_SUBLABEL, FONT_SMALL, FONT_TINY, FONT_LABEL


class DownloadDialog(ctk.CTkToplevel):
    """Modal progress dialog that runs *task(progress, cancel_event)* in a thread.

    progress(done_bytes, total_bytes, label) may be called from the worker.
    on_done(success: bool) runs on the UI thread when the task ends (or is closed).
    """

    def __init__(self, master, title: str, message: str, task, on_done=None,
                 allow_close_after_error: bool = True):
        super().__init__(master)
        self.title(title)
        self.configure(fg_color=C["surface"])
        self.geometry("480x230")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._task = task
        self._on_done = on_done
        self._cancel = threading.Event()
        self._finished = False
        self._latest = (0, 1, "")
        self._poll_after = None

        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=FONT_SUBLABEL, text_color=C["text"],
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 2))
        self._msg = ctk.CTkLabel(self, text=message, font=FONT_TINY, text_color=C["text2"], anchor="w",
                                 justify="left", wraplength=440)
        self._msg.grid(row=1, column=0, sticky="ew", padx=18)
        self._bar = ctk.CTkProgressBar(self, progress_color=C["accent"], fg_color=C["surface3"], height=10)
        self._bar.set(0)
        self._bar.grid(row=2, column=0, sticky="ew", padx=18, pady=(14, 4))
        self._detail = ctk.CTkLabel(self, text="Starting…", font=FONT_TINY, text_color=C["text3"], anchor="w")
        self._detail.grid(row=3, column=0, sticky="ew", padx=18)
        btns = ctk.CTkFrame(self, fg_color=C["surface"])
        btns.grid(row=4, column=0, sticky="e", padx=18, pady=(12, 14))
        self._retry = ctk.CTkButton(btns, text="Retry", width=80, font=FONT_LABEL, fg_color=C["accent"],
                                    hover_color=C["accent_h"], command=self._start)
        self._close = ctk.CTkButton(btns, text="Cancel", width=80, font=FONT_SMALL, fg_color="transparent",
                                    border_color=C["border2"], border_width=1, hover_color=C["surface3"],
                                    text_color=C["text2"], command=self._on_cancel)
        self._close.pack(side="right")
        self.after(150, self._grab)
        self._start()

    def _grab(self):
        try:
            self.lift()
            self.grab_set()
        except Exception:
            pass

    # ── worker ────────────────────────────────────────────────────────────────
    def _start(self):
        self._retry.pack_forget()
        self._close.configure(text="Cancel")
        self._cancel.clear()
        self._error = None
        self._done_ok = False
        self._msg.configure(text_color=C["text2"])
        threading.Thread(target=self._run, daemon=True).start()
        self._poll()

    def _progress(self, done, total, label):
        self._latest = (done, max(total, 1), label)

    def _run(self):
        try:
            self._task(self._progress, self._cancel)
            self._done_ok = True
        except Exception as exc:  # includes DownloadCancelled
            self._error = exc
        finally:
            self._finished_run = True

    def _poll(self):
        done, total, label = self._latest
        self._bar.set(min(1.0, done / total))
        if total > 1:
            self._detail.configure(text=f"{done / 1e6:,.0f} / {total / 1e6:,.0f} MB  ·  {label}")
        if getattr(self, "_finished_run", False):
            self._finished_run = False
            self._finish()
            return
        self._poll_after = self.after(200, self._poll)

    def _finish(self):
        if self._done_ok:
            self._close_dialog(True)
            return
        if self._cancel.is_set():
            self._close_dialog(False)
            return
        self._msg.configure(text=f"Download failed: {self._error}\nCheck your internet connection and try again.",
                            text_color=C["status_err"])
        self._detail.configure(text="Completed parts are kept; Retry resumes where it stopped.")
        self._close.configure(text="Close")
        self._retry.pack(side="right", padx=(0, 8))

    def _on_cancel(self):
        if self._retry.winfo_ismapped() or self._done_ok:
            self._close_dialog(False)
        else:
            self._cancel.set()
            self._detail.configure(text="Cancelling…")

    def _close_dialog(self, success: bool):
        if self._finished:
            return
        self._finished = True
        if self._poll_after:
            self.after_cancel(self._poll_after)
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self._on_done:
            self._on_done(success)
