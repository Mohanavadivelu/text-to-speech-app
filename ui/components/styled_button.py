import customtkinter as ctk


class StyledButton(ctk.CTkButton):
    """CTkButton with convenience state/text helpers for legacy compatibility."""

    def config_state(self, state: str):
        self.configure(state=state)

    def config_text(self, text: str):
        self.configure(text=text)
