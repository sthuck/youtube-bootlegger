"""Background worker for LLM tracklist analysis."""

from PySide6.QtCore import QObject, QRunnable, Signal

from ..llm import LlmExtractionError, TracklistExtraction, extract_tracklist_metadata
from ..core.settings import AppSettings


class TracklistAiSignals(QObject):
    """Signals for tracklist AI worker."""

    started = Signal()
    finished = Signal(object)  # TracklistExtraction
    error = Signal(str)


class TracklistAiWorker(QRunnable):
    """QRunnable worker for LLM tracklist analysis in a background thread."""

    def __init__(
        self,
        settings: AppSettings,
        video_title: str,
        raw_tracklist: str,
        *,
        http_post=None,
    ):
        super().__init__()
        self._settings = settings
        self._video_title = video_title
        self._raw_tracklist = raw_tracklist
        self._http_post = http_post
        self.signals = TracklistAiSignals()

    def run(self) -> None:
        """Run LLM extraction in a background thread."""
        self.signals.started.emit()
        try:
            result = extract_tracklist_metadata(
                self._settings,
                self._video_title,
                self._raw_tracklist,
                http_post=self._http_post,
            )
            self.signals.finished.emit(result)
        except LlmExtractionError as exc:
            self.signals.error.emit(str(exc))
        except Exception as exc:
            self.signals.error.emit(f"Unexpected error: {exc}")
