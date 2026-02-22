"""Main application window."""

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import parse_tracklist
from ..models import DownloadJob
from ..utils import is_ffmpeg_available
from ..workers import PipelineWorker
from .widgets import (
    DirectoryPickerWidget,
    ProgressPanelWidget,
    TracklistInputWidget,
    UrlInputWidget,
)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self._thread_pool = QThreadPool()
        self._current_worker: PipelineWorker | None = None
        self._setup_ui()
        self._connect_signals()
        self._check_ffmpeg()

    def _setup_ui(self) -> None:
        """Initialize and layout all UI components."""
        self.setWindowTitle("YouTube Bootlegger")
        self.setMinimumSize(600, 500)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self._url_input = UrlInputWidget()
        layout.addWidget(self._url_input)

        self._tracklist_input = TracklistInputWidget()
        layout.addWidget(self._tracklist_input)

        self._directory_picker = DirectoryPickerWidget()
        layout.addWidget(self._directory_picker)

        self._progress_panel = ProgressPanelWidget()
        layout.addWidget(self._progress_panel)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._start_button = QPushButton("Start Download && Split")
        self._start_button.setMinimumWidth(200)
        button_layout.addWidget(self._start_button)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setEnabled(False)
        button_layout.addWidget(self._cancel_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._start_button.clicked.connect(self._on_start_clicked)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)

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

    def _on_start_clicked(self) -> None:
        """Validate inputs and start pipeline worker."""
        self._clear_errors()

        url_valid, url_error = self._url_input.validate()
        if not url_valid:
            self._url_input.set_error(url_error)
            return

        tracks_valid, tracks_error = self._tracklist_input.validate()
        if not tracks_valid:
            self._tracklist_input.set_error(tracks_error)
            return

        dir_valid, dir_error = self._directory_picker.validate()
        if not dir_valid:
            self._directory_picker.set_error(dir_error)
            return

        tracks = parse_tracklist(self._tracklist_input.get_text())
        job = DownloadJob(
            url=self._url_input.get_url(),
            output_dir=self._directory_picker.get_directory(),
            tracks=tuple(tracks),
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
            "complete": "Complete",
        }.get(stage, stage.title())

        self._progress_panel.set_stage(f"{stage_display}: {int(percent)}%")
        self._progress_panel.set_progress(percent)
        self._progress_panel.add_message(message, "info")

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
        self._directory_picker.set_enabled(not busy)
        self._start_button.setEnabled(not busy)
        self._cancel_button.setEnabled(busy)

    def _clear_errors(self) -> None:
        """Clear all validation errors."""
        self._url_input.clear_error()
        self._tracklist_input.clear_error()
        self._directory_picker.clear_error()
