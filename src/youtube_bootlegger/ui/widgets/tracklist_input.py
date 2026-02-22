"""Tracklist/timestamp input widget."""

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ...core import ParseError, parse_tracklist


class TracklistInputWidget(QWidget):
    """Widget for tracklist/timestamp input."""

    PLACEHOLDER = """Enter one track per line in the format:
Song Name - mm:ss

Example:
Opening Number - 0:00
Second Song - 4:32
Third Song - 8:15
Final Song - 12:47"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Track List (format: Song Name - mm:ss):")
        layout.addWidget(self._label)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText(self.PLACEHOLDER)
        self._input.setMinimumHeight(150)
        layout.addWidget(self._input)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

    def get_text(self) -> str:
        """Return the tracklist text."""
        return self._input.toPlainText()

    def validate(self) -> tuple[bool, str]:
        """Validate tracklist format.

        Returns:
            Tuple of (is_valid, error_message).
        """
        text = self.get_text()
        if not text.strip():
            return False, "Please enter at least one track"

        try:
            tracks = parse_tracklist(text)
            if not tracks:
                return False, "No valid tracks found"
            return True, ""
        except ParseError as e:
            return False, str(e)

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
