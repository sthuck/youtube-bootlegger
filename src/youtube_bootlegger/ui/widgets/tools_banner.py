"""Banner showing runtime-tool download state above the main form."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from ...app_logic.runtime_tools import BannerAction, ToolsBanner

_NORMAL_STYLE = (
    "#toolsBanner { background-color: rgba(80, 140, 220, 40);"
    " border: 1px solid rgba(80, 140, 220, 120); border-radius: 6px; }"
)
_ERROR_STYLE = (
    "#toolsBanner { background-color: rgba(220, 60, 60, 40);"
    " border: 1px solid rgba(220, 60, 60, 140); border-radius: 6px; }"
)
_PROGRESS_STEPS = 1000


class ToolsBannerWidget(QFrame):
    """Renders a ToolsBanner; emits action_requested with the banner's action."""

    action_requested = Signal(str)  # BannerAction value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toolsBanner")
        self._action = BannerAction.NONE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        self._label = QLabel()
        self._label.setObjectName("toolsBannerText")
        self._label.setWordWrap(True)
        row.addWidget(self._label, 1)

        self._button = QPushButton()
        self._button.setObjectName("toolsBannerButton")
        self._button.clicked.connect(self._on_clicked)
        row.addWidget(self._button)
        layout.addLayout(row)

        self._progress = QProgressBar()
        self._progress.setObjectName("toolsBannerProgress")
        self._progress.setTextVisible(False)
        self._progress.setMaximumHeight(8)
        layout.addWidget(self._progress)

        self.render(ToolsBanner(visible=False))

    def render(self, banner: ToolsBanner) -> None:
        """Show exactly what the session's banner() describes."""
        self.setVisible(banner.visible)
        self._label.setText(banner.text)
        self._action = banner.action
        self._button.setVisible(banner.action != BannerAction.NONE)
        self._button.setText(banner.action_label)
        self.setStyleSheet(_ERROR_STYLE if banner.is_error else _NORMAL_STYLE)
        self.setProperty("isError", banner.is_error)

        downloading = banner.action == BannerAction.CANCEL
        self._progress.setVisible(banner.progress is not None or downloading)
        if banner.progress is None:
            self._progress.setRange(0, 0)  # busy indicator
        else:
            self._progress.setRange(0, _PROGRESS_STEPS)
            self._progress.setValue(int(banner.progress * _PROGRESS_STEPS))

    def _on_clicked(self) -> None:
        if self._action != BannerAction.NONE:
            self.action_requested.emit(str(self._action))
