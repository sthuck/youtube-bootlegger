"""YouTube URL input widget."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from ...utils import is_valid_youtube_url


class UrlInputWidget(QWidget):
    """Widget for YouTube URL input with validation."""

    url_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()
        self._input.textChanged.connect(self._on_text_changed)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("YouTube URL:")
        layout.addWidget(self._label)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "https://www.youtube.com/watch?v=... or https://youtu.be/..."
        )
        layout.addWidget(self._input)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

    def get_url(self) -> str:
        """Return the entered URL."""
        return self._input.text().strip()

    def validate(self) -> tuple[bool, str]:
        """Validate URL format.

        Returns:
            Tuple of (is_valid, error_message).
        """
        url = self.get_url()
        if not url:
            return False, "Please enter a YouTube URL"
        if not is_valid_youtube_url(url):
            return False, "Please enter a valid YouTube URL"
        return True, ""

    def set_error(self, message: str) -> None:
        """Display validation error."""
        self._error_label.setText(message)
        self._error_label.show()
        self._input.setStyleSheet("border: 1px solid red;")

    def clear_error(self) -> None:
        """Clear validation error display."""
        self._error_label.hide()
        self._input.setStyleSheet("")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the input."""
        self._input.setEnabled(enabled)

    def _on_text_changed(self, text: str) -> None:
        """Handle text changes and emit url_changed signal."""
        self.clear_error()
        self.url_changed.emit(text.strip())
