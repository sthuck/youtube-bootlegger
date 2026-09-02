"""Metadata input widget for artist and album information."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..theme import ThemeColors


class MetadataInputWidget(QWidget):
    """Widget for entering artist and album metadata."""

    artist_changed = Signal(str)
    album_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._theme = ThemeColors()
        self._setup_ui()
        self._artist_input.textChanged.connect(self._on_artist_changed)
        self._album_input.textChanged.connect(self._on_album_changed)

    def _on_artist_changed(self, text: str) -> None:
        self.clear_error()
        self.artist_changed.emit(text)

    def _on_album_changed(self, text: str) -> None:
        self.clear_error()
        self.album_changed.emit(text)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QLabel("Metadata:")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # Artist input
        artist_label = QLabel("Artist:")
        artist_label.setStyleSheet(f"color: {self._theme.text_secondary}; font-size: 12px;")
        layout.addWidget(artist_label)

        self._artist_input = QLineEdit()
        self._artist_input.setPlaceholderText("Enter artist name")
        layout.addWidget(self._artist_input)

        # Album input
        album_label = QLabel("Album:")
        album_label.setStyleSheet(f"color: {self._theme.text_secondary}; font-size: 12px;")
        layout.addWidget(album_label)

        self._album_input = QLineEdit()
        self._album_input.setPlaceholderText("Defaults to video title")
        layout.addWidget(self._album_input)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

    def get_artist(self) -> str:
        """Return the artist name."""
        return self._artist_input.text().strip()

    def get_album(self) -> str:
        """Return the album name."""
        return self._album_input.text().strip()

    def set_error(self, message: str) -> None:
        """Display a validation error, or clear it when message is empty."""
        if not message:
            self.clear_error()
            return
        self._error_label.setText(message)
        self._error_label.show()
        self._artist_input.setStyleSheet("border: 1px solid red;")
        self._album_input.setStyleSheet("border: 1px solid red;")

    def clear_error(self) -> None:
        """Clear validation error display."""
        self._error_label.hide()
        self._artist_input.setStyleSheet("")
        self._album_input.setStyleSheet("")

    def set_album_placeholder(self, title: str) -> None:
        """Set the album placeholder text to the video title.

        Args:
            title: Video title to use as placeholder.
        """
        if title:
            self._album_input.setPlaceholderText(title)

    def set_artist(self, artist: str) -> None:
        """Set the artist field programmatically."""
        self._artist_input.setText(artist)

    def set_album(self, album: str) -> None:
        """Set the album field programmatically."""
        self._album_input.setText(album)

    def set_default_album(self, title: str) -> None:
        """Set the default album name if empty.

        Args:
            title: Video title to use as default.
        """
        if not self._album_input.text().strip() and title:
            self._album_input.setText(title)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the inputs."""
        self._artist_input.setEnabled(enabled)
        self._album_input.setEnabled(enabled)

    def clear(self) -> None:
        """Clear both inputs."""
        self._artist_input.clear()
        self._album_input.clear()
