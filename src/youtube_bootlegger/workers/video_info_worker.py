"""Background worker for fetching video information."""

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.exceptions import ValidationError
from ..core.video_info import VideoInfo, fetch_video_info


class VideoInfoSignals(QObject):
    """Signals for video info worker."""

    started = Signal()
    finished = Signal(object)  # VideoInfo
    error = Signal(str)


class VideoInfoWorker(QRunnable):
    """QRunnable worker for fetching video info in background."""

    def __init__(self, url: str):
        """Initialize the worker.

        Args:
            url: YouTube URL to fetch info for.
        """
        super().__init__()
        self.url = url
        self.signals = VideoInfoSignals()

    def run(self) -> None:
        """Fetch video info in background thread."""
        self.signals.started.emit()

        try:
            info = fetch_video_info(self.url)
            self.signals.finished.emit(info)
        except ValidationError as e:
            self.signals.error.emit(str(e))
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {e}")
