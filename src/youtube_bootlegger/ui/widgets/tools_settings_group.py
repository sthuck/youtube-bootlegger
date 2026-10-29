"""Settings group listing the runtime tools, with download/verify buttons."""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton

from ...app_logic.runtime_tools import TOOLS_SECTION_TITLE, status_text
from ...core.tools import ToolStatus
from ...workers.tools_download_runner import open_tools_folder


class ToolsSettingsGroup(QGroupBox):
    """Lists each tool's status; the owner runs the downloads it requests.

    Signals:
        download_requested: "Download missing" was clicked.
        verify_requested: "Verify" was clicked.
    """

    download_requested = Signal()
    verify_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(TOOLS_SECTION_TITLE, parent)
        self.setObjectName("toolsGroup")
        self._tools_dir: Path | None = None
        self._form = QFormLayout(self)
        self._form.setSpacing(8)
        self._status_labels: dict[str, QLabel] = {}

        buttons = QHBoxLayout()
        self._download_button = QPushButton("Download missing")
        self._download_button.setObjectName("toolsDownloadButton")
        self._download_button.clicked.connect(self.download_requested)
        self._verify_button = QPushButton("Verify")
        self._verify_button.setObjectName("toolsVerifyButton")
        self._verify_button.clicked.connect(self.verify_requested)
        self._open_button = QPushButton("Open folder")
        self._open_button.setObjectName("toolsOpenFolderButton")
        self._open_button.clicked.connect(self._open_folder)
        for button in (self._download_button, self._verify_button, self._open_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self._buttons_row = buttons
        self._buttons_added = False

    def refresh(self, statuses: list[ToolStatus], tools_dir: Path | None, downloading: bool) -> None:
        """Show the current statuses; disable downloads while one runs."""
        self._tools_dir = tools_dir
        for status in statuses:
            label = self._status_labels.get(status.tool_id)
            if label is None:
                label = QLabel()
                label.setObjectName(f"toolStatus_{status.tool_id}")
                label.setWordWrap(True)
                self._status_labels[status.tool_id] = label
                self._form.addRow(f"{status.label}:", label)
            label.setText(status_text(status))
        if not self._buttons_added:
            self._form.addRow(self._buttons_row)
            self._buttons_added = True
        self._download_button.setEnabled(not downloading)
        self._verify_button.setEnabled(not downloading)
        self._open_button.setEnabled(tools_dir is not None)

    def _open_folder(self) -> None:
        open_tools_folder(self._tools_dir)
