"""Theme detection and styling utilities."""

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication


def is_dark_mode() -> bool:
    """Detect if the system is using dark mode.

    Returns:
        True if dark mode is active.
    """
    app = QApplication.instance()
    if app is None:
        return False

    palette = app.palette()
    window_color = palette.color(QPalette.ColorRole.Window)
    text_color = palette.color(QPalette.ColorRole.WindowText)

    # If window is darker than text, we're in dark mode
    return window_color.lightness() < text_color.lightness()


class ThemeColors:
    """Color scheme for light and dark modes."""

    def __init__(self):
        self._dark = is_dark_mode()

    @property
    def is_dark(self) -> bool:
        return self._dark

    # Background colors
    @property
    def preview_bg(self) -> str:
        return "#2d2d2d" if self._dark else "#f5f5f5"

    @property
    def preview_border(self) -> str:
        return "#444" if self._dark else "#ddd"

    @property
    def input_bg(self) -> str:
        return "#1e1e1e" if self._dark else "#fafafa"

    @property
    def input_border(self) -> str:
        return "#555" if self._dark else "#ddd"

    # Text colors
    @property
    def text_primary(self) -> str:
        return "#e0e0e0" if self._dark else "#333"

    @property
    def text_secondary(self) -> str:
        return "#aaa" if self._dark else "#666"

    @property
    def text_muted(self) -> str:
        return "#888" if self._dark else "#999"

    # Status colors
    @property
    def success_bg(self) -> str:
        return "#1b3d1b" if self._dark else "#e8f5e9"

    @property
    def error_bg(self) -> str:
        return "#3d1b1b" if self._dark else "#ffebee"

    @property
    def success_text(self) -> str:
        return "#4caf50" if self._dark else "green"

    @property
    def error_text(self) -> str:
        return "#f44336" if self._dark else "red"

    # Thumbnail placeholder
    @property
    def thumbnail_bg(self) -> str:
        return "#1a1a1a" if self._dark else "#333"
