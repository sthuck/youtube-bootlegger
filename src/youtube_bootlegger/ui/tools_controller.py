"""Keeps the widget UI's tools banner in step with the shared download runner."""

from PySide6.QtCore import QObject, QThreadPool, Signal

from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, urlopen_get
from ..workers.tools_download_runner import ToolsDownloadRunner
from .widgets import ToolsBannerWidget


class RuntimeToolsController(QObject):
    """Wires a ToolsDownloadRunner to the banner widget.

    Signals:
        changed: The session's state changed (progress, finish, failure...).
    """

    changed = Signal()

    def __init__(
        self,
        settings: AppSettings,
        banner: ToolsBannerWidget,
        *,
        http_get: HttpGet = urlopen_get,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._banner = banner
        pool = QThreadPool(self)
        pool.setMaxThreadCount(1)
        self._runner = ToolsDownloadRunner(settings, pool, http_get=http_get, parent=self)
        self.session = self._runner.session
        self._runner.changed.connect(self._refresh)
        banner.action_requested.connect(lambda _action: self._runner.trigger_banner_action())
        self._refresh()

    @property
    def downloading(self) -> bool:
        return self._runner.downloading

    def start_blocked_reason(self) -> str | None:
        return self.session.start_blocked_reason()

    def auto_download(self) -> None:
        """Start-up / after Settings: download what's missing without asking."""
        self._runner.auto_download()

    def download(self, *, verify: bool = False) -> None:
        """Banner button or Settings: download missing tools (and re-check with verify)."""
        self._runner.download(verify=verify)

    def cancel(self) -> None:
        self._runner.cancel()

    def open_folder(self) -> None:
        self._runner.open_folder()

    def _refresh(self) -> None:
        self._banner.render(self.session.banner())
        self.changed.emit()
