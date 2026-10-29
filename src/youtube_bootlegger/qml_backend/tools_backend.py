"""QML bridge for the runtime-tools downloader (yt-dlp, FFmpeg, Deno).

All decisions and strings come from app_logic.runtime_tools; this object only
runs ToolsDownloadWorker on the thread pool, feeds its signals to the session
and republishes the session's state as Qt properties.
"""

from PySide6.QtCore import Property, QObject, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from ..app_logic import (
    FFMPEG_PATH_PLACEHOLDER,
    TOOLS_SECTION_TITLE,
    YTDLP_PATH_PLACEHOLDER,
    BannerAction,
    RuntimeToolsSession,
    status_text,
)
from ..core.cancellation import CancelToken
from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, urlopen_get
from ..workers import ToolsDownloadWorker

TOOLS_TEXTS = {
    "sectionTitle": TOOLS_SECTION_TITLE,
    "ytdlpPlaceholder": YTDLP_PATH_PLACEHOLDER,
    "ffmpegPlaceholder": FFMPEG_PATH_PLACEHOLDER,
    "downloadMissing": "Download missing",
    "verify": "Verify",
    "openFolder": "Open folder",
}


class ToolsBackend(QObject):
    """Per-window runtime-tools state, exposed to QML as ``backend.tools``."""

    changed = Signal()

    def __init__(
        self,
        settings: AppSettings,
        thread_pool: QThreadPool,
        *,
        http_get: HttpGet = urlopen_get,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._thread_pool = thread_pool
        self._http_get = http_get
        self._session = RuntimeToolsSession(settings)
        # Every running worker is held until it reports back: its signals
        # object must outlive the thread emitting on it.
        self._workers: set[ToolsDownloadWorker] = set()
        self._cancel: CancelToken | None = None
        self._state: dict = {}
        self._refresh()

    # ── Properties ─────────────────────────────────────────────────

    def _get(key):  # noqa: N805 - helper used only while building the class
        return lambda self: self._state[key]

    bannerVisible = Property(bool, _get("bannerVisible"), notify=changed)
    bannerText = Property(str, _get("bannerText"), notify=changed)
    bannerActionLabel = Property(str, _get("bannerActionLabel"), notify=changed)
    bannerIsError = Property(bool, _get("bannerIsError"), notify=changed)
    # 0..1 while the size is known, -1 for an indeterminate (busy) bar.
    bannerProgress = Property(float, _get("bannerProgress"), notify=changed)
    downloading = Property(bool, _get("downloading"), notify=changed)
    startBlockedReason = Property(str, _get("startBlockedReason"), notify=changed)
    statuses = Property("QVariantList", _get("statuses"), notify=changed)
    canOpenFolder = Property(bool, _get("canOpenFolder"), notify=changed)
    texts = Property("QVariantMap", lambda self: TOOLS_TEXTS, constant=True)

    del _get

    # ── Python API for AppBackend ──────────────────────────────────

    def start_blocked_reason(self) -> str | None:
        return self._session.start_blocked_reason()

    # ── Slots ──────────────────────────────────────────────────────

    @Slot()
    def checkAutoDownload(self):
        """At start-up and after a tool setting changed: download what's missing."""
        self._run(self._session.auto_download_ids())

    @Slot()
    def triggerBannerAction(self):
        action = self._session.banner().action
        if action == BannerAction.CANCEL:
            self._cancel_download()
        elif action == BannerAction.DOWNLOAD:
            self._run(self._session.start())

    @Slot()
    def downloadMissing(self):
        self._run(self._session.start())

    @Slot()
    def verify(self):
        self._run(self._session.start(verify=True), verify=True)

    @Slot()
    def openFolder(self):
        tools_dir = self._settings.tools_dir
        if tools_dir is None:
            return
        try:
            tools_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Let the file manager report a folder it can't open.
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(tools_dir)))

    @Slot()
    def shutdown(self):
        """The window is closing: stop a running download."""
        self._cancel_download()

    # ── Internals ──────────────────────────────────────────────────

    def _cancel_download(self):
        if self._cancel is not None:
            self._cancel.cancel()

    def _run(self, tool_ids: list[str], *, verify: bool = False):
        if not tool_ids:
            self._refresh()
            return
        cancel = CancelToken()
        worker = ToolsDownloadWorker(
            tool_ids, self._settings, cancel, verify=verify, http_get=self._http_get
        )
        self._workers.add(worker)
        self._cancel = cancel

        def ended(handler):
            def on_end(*args):
                self._workers.discard(worker)
                if self._cancel is cancel:
                    self._cancel = None
                handler(*args)
                self._refresh()
            return on_end

        def on_progress(progress):
            self._session.on_progress(progress)
            self._refresh()

        worker.signals.progress.connect(on_progress)
        worker.signals.finished.connect(ended(self._session.on_finished))
        worker.signals.cancelled.connect(ended(self._session.on_cancelled))
        worker.signals.error.connect(ended(self._session.on_failed))
        self._thread_pool.start(worker)
        self._refresh()

    def _refresh(self):
        banner = self._session.banner()
        downloading = self._session.downloading
        if banner.progress is not None:
            progress = banner.progress
        else:
            progress = -1.0 if downloading else 0.0
        state = {
            "bannerVisible": banner.visible,
            "bannerText": banner.text,
            "bannerActionLabel": banner.action_label if banner.action != BannerAction.NONE else "",
            "bannerIsError": banner.is_error,
            "bannerProgress": progress,
            "downloading": downloading,
            "startBlockedReason": self._session.start_blocked_reason() or "",
            "statuses": [
                {"id": s.tool_id, "label": s.label, "text": status_text(s)}
                for s in self._session.statuses()
            ],
            "canOpenFolder": self._settings.tools_dir is not None,
        }
        if state != self._state:
            self._state = state
            self.changed.emit()
