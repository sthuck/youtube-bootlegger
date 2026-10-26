"""Textual theme matching the QML UI's dark palette."""

from textual.theme import Theme

BOOTLEGGER_THEME = Theme(
    name="bootlegger",
    primary="#7c3aed",
    secondary="#8b5cf6",
    accent="#8b5cf6",
    foreground="#e2e8f0",
    background="#0c0c14",
    surface="#13131f",
    panel="#1a1a2e",
    success="#22c55e",
    warning="#f59e0b",
    error="#ef4444",
    dark=True,
)
