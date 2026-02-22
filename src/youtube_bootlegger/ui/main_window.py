"""Main application window."""

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import parse_tracklist_with_template
from ..models import DownloadJob
from ..utils import is_ffmpeg_available, is_valid_youtube_url
from ..workers import PipelineWorker, VideoInfoWorker
from .widgets import (
    DirectoryPickerWidget,
    MetadataInputWidget,
    ProgressPanelWidget,
    TracklistInputWidget,
    UrlInputWidget,
    VideoPreviewWidget,
)


class MainWindow(QMainWindow):
    """Main application window."""

    URL_DEBOUNCE_MS = 500

    def __init__(self):
        super().__init__()
        self._thread_pool = QThreadPool()
        self._current_worker: PipelineWorker | None = None
        self._video_info_worker: VideoInfoWorker | None = None
        self._url_debounce_timer = QTimer()
        self._url_debounce_timer.setSingleShot(True)
        self._url_debounce_timer.timeout.connect(self._fetch_video_info)
        self._last_fetched_url = ""
        self._setup_ui()
        self._connect_signals()
        self._check_ffmpeg()

    def _setup_ui(self) -> None:
        """Initialize and layout all UI components."""
        self.setWindowTitle("YouTube Bootlegger")
        self.setMinimumSize(1000, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left column (wider) - Video input and tracklist
        left_column = QVBoxLayout()
        left_column.setSpacing(15)

        self._url_input = UrlInputWidget()
        left_column.addWidget(self._url_input)

        self._video_preview = VideoPreviewWidget()
        left_column.addWidget(self._video_preview)

        self._tracklist_input = TracklistInputWidget()
        left_column.addWidget(self._tracklist_input, 1)  # Expand to fill

        main_layout.addLayout(left_column, 3)  # Wider column

        # Right column (smaller) - Settings and controls
        right_column = QVBoxLayout()
        right_column.setSpacing(15)

        self._metadata_input = MetadataInputWidget()
        right_column.addWidget(self._metadata_input)

        self._directory_picker = DirectoryPickerWidget()
        right_column.addWidget(self._directory_picker)

        self._progress_panel = ProgressPanelWidget()
        right_column.addWidget(self._progress_panel, 1)  # Expand to fill

        # Buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(8)

        self._start_button = QPushButton("Start Download && Split")
        self._start_button.setMinimumHeight(40)
        button_layout.addWidget(self._start_button)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setEnabled(False)
        button_layout.addWidget(self._cancel_button)

        right_column.addLayout(button_layout)

        main_layout.addLayout(right_column, 2)  # Narrower column

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._start_button.clicked.connect(self._on_start_clicked)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        self._url_input.url_changed.connect(self._on_url_changed)

    def _check_ffmpeg(self) -> None:
        """Check if ffmpeg is available."""
        if not is_ffmpeg_available():
            QMessageBox.warning(
                self,
                "FFmpeg Not Found",
                "FFmpeg is not installed or not in your PATH.\n\n"
                "Please install FFmpeg to use this application.\n\n"
                "On Linux: sudo apt install ffmpeg\n"
                "On macOS: brew install ffmpeg\n"
                "On Windows: Download from ffmpeg.org",
            )

    def _on_url_changed(self, url: str) -> None:
        """Handle URL input changes with debouncing."""
        self._url_debounce_timer.stop()

        if not url:
            self._video_preview.clear()
            self._last_fetched_url = ""
            return

        if not is_valid_youtube_url(url):
            self._video_preview.clear()
            return

        if url == self._last_fetched_url:
            return

        self._url_debounce_timer.start(self.URL_DEBOUNCE_MS)

    def _fetch_video_info(self) -> None:
        """Fetch video info for the current URL."""
        url = self._url_input.get_url()

        if not url or not is_valid_youtube_url(url):
            return

        if url == self._last_fetched_url:
            return

        self._last_fetched_url = url
        self._video_preview.set_loading()

        self._video_info_worker = VideoInfoWorker(url)
        self._video_info_worker.signals.finished.connect(self._on_video_info_loaded)
        self._video_info_worker.signals.error.connect(self._on_video_info_error)

        self._thread_pool.start(self._video_info_worker)

    def _on_video_info_loaded(self, info) -> None:
        """Handle successful video info fetch."""
        self._video_preview.set_video_info(info)
        # Set default album name to video title
        self._metadata_input.set_album_placeholder(info.title)

    def _on_video_info_error(self, message: str) -> None:
        """Handle video info fetch error."""
        self._video_preview.set_error(message)
        self._url_input.set_error(message)

    def _on_start_clicked(self) -> None:
        """Validate inputs and start pipeline worker."""
        self._clear_errors()

        url_valid, url_error = self._url_input.validate()
        if not url_valid:
            self._url_input.set_error(url_error)
            return

        video_info = self._video_preview.get_video_info()
        if video_info is None:
            self._url_input.set_error("Please wait for video info to load")
            return

        tracks_valid, tracks_error = self._tracklist_input.validate()
        if not tracks_valid:
            self._tracklist_input.set_error(tracks_error)
            return

        dir_valid, dir_error = self._directory_picker.validate()
        if not dir_valid:
            self._directory_picker.set_error(dir_error)
            return

        tracks = parse_tracklist_with_template(
            self._tracklist_input.get_text(),
            self._tracklist_input.get_template(),
        )

        # Get metadata - album defaults to video title if not specified
        artist = self._metadata_input.get_artist() or None
        album = self._metadata_input.get_album() or video_info.title

        job = DownloadJob(
            url=self._url_input.get_url(),
            output_dir=self._directory_picker.get_directory(),
            tracks=tuple(tracks),
            artist=artist,
            album=album,
            thumbnail_url=video_info.thumbnail_url,
        )

        self._start_pipeline(job)

    def _start_pipeline(self, job: DownloadJob) -> None:
        """Start the pipeline worker."""
        self._set_ui_busy(True)
        self._progress_panel.clear()
        self._progress_panel.reset_style()
        self._progress_panel.add_message("Starting...", "info")

        self._current_worker = PipelineWorker(job)
        self._current_worker.signals.started.connect(self._on_worker_started)
        self._current_worker.signals.progress.connect(self._on_progress)
        self._current_worker.signals.log.connect(self._on_log)
        self._current_worker.signals.finished.connect(self._on_finished)
        self._current_worker.signals.error.connect(self._on_error)

        self._thread_pool.start(self._current_worker)

    def _on_cancel_clicked(self) -> None:
        """Cancel the current operation."""
        if self._current_worker:
            self._current_worker.cancel()
            self._progress_panel.add_message("Cancelling...", "warn")

    def _on_worker_started(self) -> None:
        """Handle worker start."""
        self._progress_panel.add_message("Worker started", "info")

    def _on_progress(self, stage: str, percent: float, message: str) -> None:
        """Update progress display."""
        stage_display = {
            "download": "Downloading",
            "split": "Splitting",
            "tagging": "Tagging",
            "complete": "Complete",
        }.get(stage, stage.title())

        self._progress_panel.set_stage(f"{stage_display}: {int(percent)}%")
        self._progress_panel.set_progress(percent)
        self._progress_panel.add_message(message, "info")

    def _on_log(self, message: str) -> None:
        """Handle log messages from pipeline."""
        self._progress_panel.add_message(message, "debug")

    def _on_finished(self, output_files: list) -> None:
        """Handle successful completion."""
        self._set_ui_busy(False)
        self._progress_panel.set_complete()

        self._progress_panel.add_message(
            f"Successfully created {len(output_files)} track(s)!",
            "info",
        )

        for path in output_files:
            self._progress_panel.add_message(f"  - {path}", "info")

        QMessageBox.information(
            self,
            "Complete",
            f"Successfully split audio into {len(output_files)} track(s)!",
        )

    def _on_error(self, message: str) -> None:
        """Display error to user."""
        self._set_ui_busy(False)
        self._progress_panel.set_error()
        self._progress_panel.add_message(message, "error")

        QMessageBox.critical(
            self,
            "Error",
            message,
        )

    def _set_ui_busy(self, busy: bool) -> None:
        """Enable/disable UI during processing."""
        self._url_input.set_enabled(not busy)
        self._tracklist_input.set_enabled(not busy)
        self._metadata_input.set_enabled(not busy)
        self._directory_picker.set_enabled(not busy)
        self._start_button.setEnabled(not busy)
        self._cancel_button.setEnabled(busy)

    def _clear_errors(self) -> None:
        """Clear all validation errors."""
        self._url_input.clear_error()
        self._tracklist_input.clear_error()
        self._directory_picker.clear_error()
