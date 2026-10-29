"""Runs a window's runtime-tool downloads on a Qt thread pool.

Shared by the QML and widget front-ends: both wrap one ToolsDownloadRunner and
only render its session. (The TUI uses daemon threads instead; see tui/.)
"""

from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from ..app_logic.runtime_tools import BannerAction, RuntimeToolsSession
from ..core.cancellation import CancelToken
from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, InstallProgress, urlopen_get
from .tools_download_worker import ToolsDownloadWorker


def open_tools_folder(tools_dir: Path | None) -> bool:
    """Show the tools folder in the file manager, creating it first if needed."""
    if tools_dir is None:
        return False
    try:
        tools_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(tools_dir)))


class ToolsDownloadRunner(QObject):
    """Owns a RuntimeToolsSession and runs ToolsDownloadWorker for it.

    Signals:
        changed: The session's state changed (start, progress, end).
    """

    changed = Signal()

    def __init__(
        self,
        settings: AppSettings,
        thread_pool: QThreadPool,
        *,
        http_get: HttpGet = urlopen_get,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.session = RuntimeToolsSession(settings)
        self._settings = settings
        self._thread_pool = thread_pool
        self._http_get = http_get
        # Every running worker is held until it reports back: its signals
        # object must outlive the thread emitting on it.
        self._workers: set[ToolsDownloadWorker] = set()
        self._cancel: CancelToken | None = None

    @property
    def downloading(self) -> bool:
        return self.session.downloading

    def auto_download(self) -> None:
        """At start-up and after a tool setting changed: download what's missing."""
        self._run(self.session.auto_download_ids())

    def download(self, *, verify: bool = False) -> None:
        """Banner Download/Retry, or Settings "Download missing" / "Verify"."""
        self._run(self.session.start(verify=verify), verify=verify)

    def trigger_banner_action(self) -> None:
        action = self.session.banner().action
        if action == BannerAction.CANCEL:
            self.cancel()
        elif action == BannerAction.DOWNLOAD:
            self.download()

    def cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.cancel()

    def open_folder(self) -> bool:
        return open_tools_folder(self._settings.tools_dir)

    def _run(self, tool_ids: list[str], *, verify: bool = False) -> None:
        if not tool_ids:
            self.changed.emit()
            return
        cancel = CancelToken()
        worker = ToolsDownloadWorker(
            tool_ids, self._settings, cancel, verify=verify, http_get=self._http_get
        )
        self._workers.add(worker)
        self._cancel = cancel

        def ended(outcome):
            def on_end(*args):
                self._workers.discard(worker)
                if self._cancel is cancel:
                    self._cancel = None
                outcome(*args)
                self.changed.emit()
            return on_end

        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(ended(self.session.on_finished))
        worker.signals.cancelled.connect(ended(self.session.on_cancelled))
        worker.signals.error.connect(ended(self.session.on_failed))
        self._thread_pool.start(worker)
        self.changed.emit()

    def _on_progress(self, progress: InstallProgress) -> None:
        self.session.on_progress(progress)
        self.changed.emit()
