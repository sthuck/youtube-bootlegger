"""Runs runtime-tool downloads for the widget UI and keeps the banner current."""

from PySide6.QtCore import QObject, QThreadPool, Signal

from ..app_logic.runtime_tools import BannerAction, RuntimeToolsSession
from ..core.cancellation import CancelToken
from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, InstallProgress, urlopen_get
from ..workers import ToolsDownloadWorker
from .widgets import ToolsBannerWidget


class RuntimeToolsController(QObject):
    """Wires a RuntimeToolsSession to ToolsDownloadWorker and the banner.

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
        self._settings = settings
        self._banner = banner
        self._http_get = http_get
        self._session = RuntimeToolsSession(settings)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        # Held until the worker reports back, so its signals object stays alive.
        self._worker: ToolsDownloadWorker | None = None
        self._cancel: CancelToken | None = None
        banner.action_requested.connect(self._on_banner_action)
        self._refresh()

    @property
    def downloading(self) -> bool:
        return self._session.downloading

    def start_blocked_reason(self) -> str | None:
        return self._session.start_blocked_reason()

    def auto_download(self) -> None:
        """Start-up / after Settings: download what's missing without asking."""
        self._run(self._session.auto_download_ids())

    def download(self, *, verify: bool = False) -> None:
        """Banner button or Settings: download missing tools (and re-check with verify)."""
        self._run(self._session.start(verify=verify), verify=verify)

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.cancel()

    def _run(self, tool_ids: list[str], *, verify: bool = False) -> None:
        if tool_ids:
            self._cancel = CancelToken()
            worker = ToolsDownloadWorker(
                tool_ids, self._settings, self._cancel, verify=verify, http_get=self._http_get
            )
            worker.signals.progress.connect(self._on_progress)
            worker.signals.finished.connect(self._on_finished)
            worker.signals.cancelled.connect(self._on_cancelled)
            worker.signals.error.connect(self._on_error)
            self._worker = worker
            self._pool.start(worker)
        self._refresh()

    def _on_banner_action(self, action: str) -> None:
        if action == BannerAction.CANCEL:
            self.cancel()
        elif action == BannerAction.DOWNLOAD:
            self.download()

    def _on_progress(self, progress: InstallProgress) -> None:
        self._session.on_progress(progress)
        self._refresh()

    def _on_finished(self) -> None:
        self._done()
        self._session.on_finished()
        self._refresh()

    def _on_cancelled(self) -> None:
        self._done()
        self._session.on_cancelled()
        self._refresh()

    def _on_error(self, message: str) -> None:
        self._done()
        self._session.on_failed(message)
        self._refresh()

    def _done(self) -> None:
        self._worker = None
        self._cancel = None

    def _refresh(self) -> None:
        self._banner.render(self._session.banner())
        self.changed.emit()
