"""Output directory picker widget."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DirectoryPickerWidget(QWidget):
    """Widget for selecting output directory."""

    directory_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()
        self._input.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        self.clear_error()
        self.directory_changed.emit(text.strip())

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Output Directory:")
        layout.addWidget(self._label)

        row_layout = QHBoxLayout()

        self._input = QLineEdit()
        self._input.setPlaceholderText("Select output directory...")
        self._input.setText(str(Path.home() / "Music"))
        row_layout.addWidget(self._input)

        self._browse_button = QPushButton("Browse...")
        self._browse_button.clicked.connect(self._on_browse)
        row_layout.addWidget(self._browse_button)

        layout.addLayout(row_layout)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red;")
        self._error_label.hide()
        layout.addWidget(self._error_label)

    def get_directory(self) -> Path:
        """Return selected directory path."""
        return Path(self._input.text().strip())

    def set_error(self, message: str) -> None:
        """Display a validation error, or clear it when message is empty."""
        if not message:
            self.clear_error()
            return
        self._error_label.setText(message)
        self._error_label.show()
        self._input.setStyleSheet("border: 1px solid red;")

    def clear_error(self) -> None:
        """Clear validation error display."""
        self._error_label.hide()
        self._input.setStyleSheet("")

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the widget."""
        self._input.setEnabled(enabled)
        self._browse_button.setEnabled(enabled)

    def _on_browse(self) -> None:
        """Handle browse button click."""
        current = self.get_directory()
        start_dir = str(current) if current.exists() else str(Path.home())

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            start_dir,
        )

        if directory:
            self._input.setText(directory)
            self.clear_error()
