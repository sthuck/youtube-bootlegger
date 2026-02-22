"""Theme detection and styling utilities.

Color palette inspired by Material Design 3.
https://m3.material.io/styles/color
"""

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
    """Color scheme for light and dark modes.

    Uses Material Design 3 inspired color palette.
    """

    # Material Design Colors
    # Primary: Indigo
    _PRIMARY_LIGHT = "#3F51B5"
    _PRIMARY_DARK = "#7986CB"

    # Secondary: Teal
    _SECONDARY_LIGHT = "#009688"
    _SECONDARY_DARK = "#4DB6AC"

    # Success: Green
    _SUCCESS_50 = "#E8F5E9"
    _SUCCESS_100 = "#C8E6C9"
    _SUCCESS_400 = "#66BB6A"
    _SUCCESS_500 = "#4CAF50"
    _SUCCESS_700 = "#388E3C"
    _SUCCESS_900 = "#1B5E20"

    # Error: Red
    _ERROR_50 = "#FFEBEE"
    _ERROR_100 = "#FFCDD2"
    _ERROR_400 = "#EF5350"
    _ERROR_500 = "#F44336"
    _ERROR_700 = "#D32F2F"
    _ERROR_900 = "#B71C1C"

    # Warning: Amber
    _WARNING_400 = "#FFCA28"
    _WARNING_700 = "#FFA000"

    # Neutral: Blue Grey
    _NEUTRAL_50 = "#ECEFF1"
    _NEUTRAL_100 = "#CFD8DC"
    _NEUTRAL_200 = "#B0BEC5"
    _NEUTRAL_300 = "#90A4AE"
    _NEUTRAL_400 = "#78909C"
    _NEUTRAL_500 = "#607D8B"
    _NEUTRAL_600 = "#546E7A"
    _NEUTRAL_700 = "#455A64"
    _NEUTRAL_800 = "#37474F"
    _NEUTRAL_900 = "#263238"

    # Surface colors
    _SURFACE_LIGHT = "#FFFFFF"
    _SURFACE_LIGHT_DIM = "#F5F7FA"
    _SURFACE_LIGHT_CONTAINER = "#ECEEF3"

    _SURFACE_DARK = "#1C1B1F"
    _SURFACE_DARK_DIM = "#141218"
    _SURFACE_DARK_CONTAINER = "#2B2930"

    def __init__(self):
        self._dark = is_dark_mode()

    @property
    def is_dark(self) -> bool:
        return self._dark

    # Background colors
    @property
    def preview_bg(self) -> str:
        return self._SURFACE_DARK_CONTAINER if self._dark else self._SURFACE_LIGHT_DIM

    @property
    def preview_border(self) -> str:
        return self._NEUTRAL_700 if self._dark else self._NEUTRAL_200

    @property
    def input_bg(self) -> str:
        return self._SURFACE_DARK_DIM if self._dark else self._SURFACE_LIGHT

    @property
    def input_border(self) -> str:
        return self._NEUTRAL_600 if self._dark else self._NEUTRAL_300

    # Text colors
    @property
    def text_primary(self) -> str:
        return "#E6E1E5" if self._dark else self._NEUTRAL_900

    @property
    def text_secondary(self) -> str:
        return self._NEUTRAL_300 if self._dark else self._NEUTRAL_600

    @property
    def text_muted(self) -> str:
        return self._NEUTRAL_400 if self._dark else self._NEUTRAL_400

    # Status colors - Success
    @property
    def success_bg(self) -> str:
        return "#1E3A2F" if self._dark else self._SUCCESS_50

    @property
    def success_text(self) -> str:
        return self._SUCCESS_400 if self._dark else self._SUCCESS_700

    @property
    def success_border(self) -> str:
        return self._SUCCESS_700 if self._dark else self._SUCCESS_100

    # Status colors - Error
    @property
    def error_bg(self) -> str:
        return "#3D1F1F" if self._dark else self._ERROR_50

    @property
    def error_text(self) -> str:
        return self._ERROR_400 if self._dark else self._ERROR_700

    @property
    def error_border(self) -> str:
        return self._ERROR_700 if self._dark else self._ERROR_100

    # Status colors - Warning
    @property
    def warning_text(self) -> str:
        return self._WARNING_400 if self._dark else self._WARNING_700

    # Accent colors
    @property
    def primary(self) -> str:
        return self._PRIMARY_DARK if self._dark else self._PRIMARY_LIGHT

    @property
    def secondary(self) -> str:
        return self._SECONDARY_DARK if self._dark else self._SECONDARY_LIGHT

    # Thumbnail placeholder
    @property
    def thumbnail_bg(self) -> str:
        return self._SURFACE_DARK_DIM if self._dark else self._NEUTRAL_800

    @property
    def thumbnail_text(self) -> str:
        return self._NEUTRAL_400 if self._dark else self._NEUTRAL_300
