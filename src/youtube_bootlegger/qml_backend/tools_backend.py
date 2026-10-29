"""QML bridge for the runtime-tools downloader (yt-dlp, FFmpeg, Deno).

All decisions and strings come from app_logic.runtime_tools and downloads run
through the shared ToolsDownloadRunner; this object only republishes the
session's state as Qt properties.
"""

from PySide6.QtCore import Property, QObject, QThreadPool, Signal, Slot

from ..app_logic import (
    FFMPEG_PATH_PLACEHOLDER,
    TOOLS_SECTION_TITLE,
    YTDLP_PATH_PLACEHOLDER,
    BannerAction,
    status_text,
)
from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, urlopen_get
from ..workers.tools_download_runner import ToolsDownloadRunner

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
        self._runner = ToolsDownloadRunner(settings, thread_pool, http_get=http_get, parent=self)
        self._session = self._runner.session
        self._runner.changed.connect(self._refresh)
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
        self._runner.auto_download()

    @Slot()
    def triggerBannerAction(self):
        self._runner.trigger_banner_action()

    @Slot()
    def downloadMissing(self):
        self._runner.download()

    @Slot()
    def verify(self):
        self._runner.download(verify=True)

    @Slot()
    def openFolder(self):
        self._runner.open_folder()

    @Slot()
    def shutdown(self):
        """The window is closing: stop a running download."""
        self._runner.cancel()

    # ── Internals ──────────────────────────────────────────────────

    def _refresh(self):
        view = self._session.view()  # one tool lookup per refresh
        banner = view.banner
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
            "startBlockedReason": view.start_blocked_reason or "",
            "statuses": [
                {"id": s.tool_id, "label": s.label, "text": status_text(s)}
                for s in view.statuses
            ],
            "canOpenFolder": self._settings.tools_dir is not None,
        }
        if state != self._state:
            self._state = state
            self.changed.emit()
