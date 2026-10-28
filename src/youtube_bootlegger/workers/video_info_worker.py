"""Background worker for fetching video information."""

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.exceptions import ValidationError
from ..core.settings import AppSettings
from ..core.video_info import VideoInfo, fetch_video_info


class VideoInfoSignals(QObject):
    """Signals for video info worker."""

    started = Signal()
    finished = Signal(object)  # VideoInfo
    error = Signal(str)


class VideoInfoWorker(QRunnable):
    """QRunnable worker for fetching video info in background."""

    def __init__(
        self,
        url: str,
        settings: AppSettings | None = None,
        *,
        comment_limit: int = 0,
    ):
        """Initialize the worker.

        Args:
            url: YouTube URL to fetch info for.
            settings: Application settings. Defaults to the shared singleton.
            comment_limit: Passed to fetch_video_info; callers use
                app_logic.preview_comment_limit(settings).
        """
        super().__init__()
        self.url = url
        self.settings = settings
        self.comment_limit = comment_limit
        self.signals = VideoInfoSignals()

    def run(self) -> None:
        """Fetch video info in background thread."""
        self.signals.started.emit()

        try:
            info = fetch_video_info(
                self.url, settings=self.settings, comment_limit=self.comment_limit
            )
            self.signals.finished.emit(info)
        except ValidationError as e:
            self.signals.error.emit(str(e))
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {e}")
