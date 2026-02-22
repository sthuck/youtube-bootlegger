"""Metadata input widget for artist and album information."""

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..theme import ThemeColors


class MetadataInputWidget(QWidget):
    """Widget for entering artist and album metadata."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._theme = ThemeColors()
        self._setup_ui()

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

    def get_artist(self) -> str:
        """Return the artist name."""
        return self._artist_input.text().strip()

    def get_album(self) -> str:
        """Return the album name."""
        return self._album_input.text().strip()

    def set_album_placeholder(self, title: str) -> None:
        """Set the album placeholder text to the video title.

        Args:
            title: Video title to use as placeholder.
        """
        if title:
            self._album_input.setPlaceholderText(title)

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
