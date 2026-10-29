"""Background worker for the AI track-list finder (widgets and QML front-ends)."""

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.settings import AppSettings
from ..core.video_info import VideoInfo
from ..llm.http import PostJson, post_json
from ..llm.track_finder import TracklistFindError, find_tracklist


class TracklistFindSignals(QObject):
    """Signals for the track-list find worker.

    Both carry the TrackFinderSession token the search was started with, so
    the receiver can drop stale results (session.complete/fail do that).
    """

    finished = Signal(int, object)  # token, TracklistFindResult
    error = Signal(int, str)  # token, message


class TracklistFindWorker(QRunnable):
    """Run llm.find_tracklist in a background thread.

    There's no way to abort the HTTP request: Stop just makes the session
    discard the result. Receivers must keep the worker referenced until it
    emits, as the preview workers are (its signals object must outlive the
    emitting thread).
    """

    def __init__(
        self,
        settings: AppSettings,
        info: VideoInfo,
        token: int,
        *,
        http_post: PostJson = post_json,
    ):
        super().__init__()
        self._settings = settings
        self._info = info
        self._token = token
        self._http_post = http_post
        self.signals = TracklistFindSignals()

    def run(self) -> None:
        """Emit finished(token, result), or error(token, message) on
        TracklistFindError or any unexpected exception ("Unexpected error: ...")."""
        try:
            result = find_tracklist(self._settings, self._info, http_post=self._http_post)
        except TracklistFindError as exc:
            self.signals.error.emit(self._token, str(exc))
        except Exception as exc:
            self.signals.error.emit(self._token, f"Unexpected error: {exc}")
        else:
            self.signals.finished.emit(self._token, result)
