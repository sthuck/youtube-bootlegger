"""Background worker that downloads the runtime tools."""

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.cancellation import CancelToken
from ..core.exceptions import OperationCancelledError, ToolInstallError
from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, install_tools, urlopen_get


class ToolsDownloadSignals(QObject):
    """Signals for the tools download worker."""

    progress = Signal(object)  # InstallProgress
    finished = Signal()
    cancelled = Signal()
    error = Signal(str)


class ToolsDownloadWorker(QRunnable):
    """Install tools off the UI thread; cancel through the given token."""

    def __init__(
        self,
        tool_ids: list[str],
        settings: AppSettings,
        cancel: CancelToken,
        *,
        verify: bool = False,
        http_get: HttpGet = urlopen_get,
    ):
        super().__init__()
        self.tool_ids = tool_ids
        self.settings = settings
        self.cancel = cancel
        self.verify = verify
        self.http_get = http_get
        self.signals = ToolsDownloadSignals()

    def run(self) -> None:
        try:
            install_tools(
                self.tool_ids,
                self.settings.tool_store,
                verify=self.verify,
                http_get=self.http_get,
                on_progress=self.signals.progress.emit,
                cancel=self.cancel,
            )
            self.signals.finished.emit()
        except OperationCancelledError:
            self.signals.cancelled.emit()
        except ToolInstallError as e:
            self.signals.error.emit(str(e))
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {e}")
