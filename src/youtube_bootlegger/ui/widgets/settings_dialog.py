"""Settings dialog for configuring external tool paths."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.settings import AppSettings, get_settings


class SettingsDialog(QDialog):
    """Modal dialog for editing persisted application settings."""

    def __init__(self, parent: QWidget | None = None, settings: AppSettings | None = None):
        super().__init__(parent)
        self._settings = settings or get_settings()
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        self._use_external_checkbox = QCheckBox("Use external yt-dlp executable")
        self._use_external_checkbox.toggled.connect(self._on_use_external_toggled)
        form.addRow(self._use_external_checkbox)

        self._ytdlp_path_input, ytdlp_row = self._make_path_row(
            "Select yt-dlp executable",
            placeholder='Leave empty to use "yt-dlp" from PATH',
        )
        form.addRow("yt-dlp path:", ytdlp_row)

        self._ffmpeg_path_input, ffmpeg_row = self._make_path_row(
            "Select ffmpeg executable",
            placeholder='Leave empty to use "ffmpeg" from PATH',
        )
        form.addRow("ffmpeg path:", ffmpeg_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_path_row(self, dialog_title: str, placeholder: str) -> tuple[QLineEdit, QWidget]:
        """Build a text input + browse button row for picking an executable path."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        path_input = QLineEdit()
        path_input.setPlaceholderText(placeholder)
        row_layout.addWidget(path_input)

        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(lambda: self._on_browse(path_input, dialog_title))
        row_layout.addWidget(browse_button)

        return path_input, row

    def _on_browse(self, target: QLineEdit, dialog_title: str) -> None:
        """Open a file picker and write the chosen path into the target field."""
        path, _ = QFileDialog.getOpenFileName(self, dialog_title)
        if path:
            target.setText(path)

    def _on_use_external_toggled(self, checked: bool) -> None:
        """Enable the yt-dlp path field only when external mode is active."""
        self._ytdlp_path_input.setEnabled(checked)

    def _load_settings(self) -> None:
        """Populate the form from the current persisted settings."""
        self._use_external_checkbox.setChecked(self._settings.use_external_ytdlp)
        self._ytdlp_path_input.setText(self._settings.ytdlp_path)
        self._ffmpeg_path_input.setText(self._settings.ffmpeg_path)
        self._ytdlp_path_input.setEnabled(self._settings.use_external_ytdlp)

    def _on_save(self) -> None:
        """Persist the form values and close the dialog."""
        self._settings.use_external_ytdlp = self._use_external_checkbox.isChecked()
        self._settings.ytdlp_path = self._ytdlp_path_input.text()
        self._settings.ffmpeg_path = self._ffmpeg_path_input.text()
        self._settings.sync()
        self.accept()
