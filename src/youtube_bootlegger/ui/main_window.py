"""Main application window."""

from PySide6.QtCore import QThreadPool, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..app_logic import (
    AiButtonMode,
    CancelReason,
    FormValues,
    LogLine,
    TrackFinderSession,
    ai_button_label,
    ai_button_mode,
    check_find_ready,
    preview_comment_limit,
    should_auto_find,
    video_sources_log_line,
)
from ..core import parse_tracklist_with_template
from ..core.video_info import VideoInfo
from ..llm import is_llm_configured, launch_chatgpt_lite_assist
from ..core.settings import LlmProvider, get_settings
from ..models import DownloadJob
from ..utils import is_ffmpeg_available, is_valid_youtube_url
from ..resources import APP_LOGO_PNG
from ..workers import (
    PipelineWorker,
    TracklistAiWorker,
    TracklistFindWorker,
    VideoInfoWorker,
)
from .widgets import (
    DirectoryPickerWidget,
    MetadataInputWidget,
    ProgressPanelWidget,
    SettingsDialog,
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
        self._tracklist_ai_worker: TracklistAiWorker | None = None
        self._ai_analyzing = False
        self._finder = TrackFinderSession()
        self._find_worker: TracklistFindWorker | None = None
        self._find_video_id = ""
        self._find_manual = False
        self._url_debounce_timer = QTimer()
        self._url_debounce_timer.setSingleShot(True)
        self._url_debounce_timer.timeout.connect(self._fetch_video_info)
        self._last_fetched_url = ""
        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self._check_ffmpeg()

    def _setup_ui(self) -> None:
        """Initialize and layout all UI components."""
        self.setWindowTitle("YouTube Bootlegger")
        self.setWindowIcon(QIcon(str(APP_LOGO_PNG)))
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

    def _setup_menu(self) -> None:
        """Set up the menu bar with a Settings entry."""
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings_dialog)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(settings_action)

    def _open_settings_dialog(self) -> None:
        """Open the settings dialog and re-check ffmpeg availability afterward."""
        dialog = SettingsDialog(self)
        if dialog.exec():
            self._check_ffmpeg()
            self._update_ai_availability()

    def _update_ai_availability(self) -> None:
        """Refresh the AI button and the finder rows from the current state.

        The button finds a track list when the box is empty and detects the
        format otherwise; detecting still needs a configured LLM, finding
        explains on click what's missing.
        """
        settings = get_settings()
        tracklist = self._tracklist_input.get_text()
        info = self._video_preview.get_video_info()
        mode = ai_button_mode(tracklist)
        idle = not self._ai_analyzing and not self._finder.searching
        ready = mode == AiButtonMode.FIND or is_llm_configured(settings)

        self._tracklist_input.set_ai_button_label(ai_button_label(mode))
        self._tracklist_input.set_ai_available(info is not None and idle and ready)
        self._tracklist_input.set_find_state(
            self._finder.searching,
            self._finder.banner,
            self._finder.show_api_hint(settings, info, tracklist),
        )
        self._tracklist_input.set_template_set_by_ai(
            self._finder.template_set_by_ai(self._tracklist_input.get_template())
        )

    def _on_ai_requested(self) -> None:
        """Find a track list (empty box) or detect its format (filled box)."""
        if self._ai_analyzing or self._finder.searching:
            return
        if ai_button_mode(self._tracklist_input.get_text()) == AiButtonMode.FIND:
            self._on_find_requested()
        else:
            self._detect_format()

    def _on_find_requested(self) -> None:
        """Handle a "Find with AI" click."""
        info = self._video_preview.get_video_info()
        problem = check_find_ready(info, get_settings())
        if problem:
            QMessageBox.warning(self, "AI Assist", problem)
            return
        self._start_find(info, manual=True)

    def _start_find(self, info: VideoInfo, *, manual: bool) -> None:
        """Search for a track list in the video, or reuse this session's result."""
        token = self._finder.begin(info.video_id)
        self._find_video_id = info.video_id
        self._find_manual = manual

        cached = self._finder.cached(info.video_id)
        if cached is not None:
            self._on_find_finished(token, cached)
            return

        worker = TracklistFindWorker(get_settings(), info, token)
        worker.signals.finished.connect(self._on_find_finished)
        worker.signals.error.connect(self._on_find_error)
        self._find_worker = worker
        self._thread_pool.start(worker)
        self._update_ai_availability()

    def _on_find_finished(self, token: int, result) -> None:
        """Apply a finished search, unless it was stopped or superseded."""
        application = self._finder.complete(
            token, self._find_video_id, result, self._form_values()
        )
        if application is None:
            return
        if application.values is not None:
            self._write_form_values(application.values)
        for line in application.log:
            self._log(line)
        self._update_ai_availability()

    def _on_find_error(self, token: int, message: str) -> None:
        """Log a failed search; a manual click also shows the message."""
        line = self._finder.fail(token, message)
        if line is None:
            return
        self._log(line)
        self._update_ai_availability()
        if self._find_manual:
            QMessageBox.critical(self, "AI Assist", message)

    def _on_stop_find(self) -> None:
        """Stop the running search; its result will be discarded."""
        self._log(self._finder.cancel(CancelReason.STOPPED))
        self._update_ai_availability()

    def _on_undo_find(self) -> None:
        """Restore the form as it was before the AI filled it."""
        values = self._finder.undo()
        if values is not None:
            self._write_form_values(values)
        self._update_ai_availability()

    def _on_find_banner_dismissed(self) -> None:
        self._finder.dismiss_banner()
        self._update_ai_availability()

    def _on_api_hint_dismissed(self) -> None:
        self._finder.dismiss_api_hint()
        self._update_ai_availability()

    def _on_tracklist_changed(self) -> None:
        """Typing during a search stops it; editing an AI fill ends the banner."""
        self._log(self._finder.on_tracklist_edited(self._tracklist_input.get_text()))
        self._update_ai_availability()

    def _on_video_changed(self) -> None:
        """Cancel a search and clear an unedited AI fill; it was for the old video."""
        values, line = self._finder.on_video_changed()
        self._log(line)
        if values is not None:
            self._write_form_values(values)

    def _form_values(self) -> FormValues:
        return FormValues(
            tracklist=self._tracklist_input.get_text(),
            template=self._tracklist_input.get_template(),
            artist=self._metadata_input.get_artist(),
            album=self._metadata_input.get_album(),
        )

    def _write_form_values(self, values: FormValues) -> None:
        # Template first, so the track list preview parses with the right one.
        self._tracklist_input.set_template(values.template)
        self._tracklist_input.set_text(values.tracklist)
        self._metadata_input.set_artist(values.artist)
        self._metadata_input.set_album(values.album)

    def _log(self, line: LogLine | None) -> None:
        if line is not None:
            self._progress_panel.add_message(line.text, line.level)

    def _detect_format(self) -> None:
        """Run LLM analysis on the raw track list."""
        video_info = self._video_preview.get_video_info()
        if video_info is None:
            QMessageBox.warning(
                self,
                "AI Assist",
                "Please wait for video info to load before using AI.",
            )
            return

        raw_tracklist = self._tracklist_input.get_text()
        if not raw_tracklist.strip():
            return

        settings = get_settings()
        if not is_llm_configured(settings):
            QMessageBox.warning(
                self,
                "AI Assist",
                "LLM is not configured. Add API credentials in Settings.",
            )
            return

        if settings.llm_provider == LlmProvider.CHATGPT_LITE:
            ok, message = launch_chatgpt_lite_assist(
                video_info.title,
                raw_tracklist,
            )
            if ok:
                QMessageBox.information(self, "AI Assist", message)
            else:
                QMessageBox.warning(self, "AI Assist", message)
            return

        self._ai_analyzing = True
        self._tracklist_input.set_ai_loading(True)
        self._update_ai_availability()

        self._tracklist_ai_worker = TracklistAiWorker(
            get_settings(),
            video_info.title,
            raw_tracklist,
        )
        self._tracklist_ai_worker.signals.finished.connect(self._on_ai_finished)
        self._tracklist_ai_worker.signals.error.connect(self._on_ai_error)
        self._thread_pool.start(self._tracklist_ai_worker)

    def _on_ai_finished(self, result) -> None:
        """Apply LLM extraction results to the form."""
        self._ai_analyzing = False
        self._tracklist_input.set_ai_loading(False)
        self._tracklist_input.set_template(result.template)
        if result.artist_name:
            self._metadata_input.set_artist(result.artist_name)
        if result.album_name:
            self._metadata_input.set_album(result.album_name)
        self._update_ai_availability()

    def _on_ai_error(self, message: str) -> None:
        """Display an AI extraction error."""
        self._ai_analyzing = False
        self._tracklist_input.set_ai_loading(False)
        self._update_ai_availability()
        QMessageBox.critical(self, "AI Assist", message)

    def _connect_signals(self) -> None:
        """Connect widget signals to slots."""
        self._start_button.clicked.connect(self._on_start_clicked)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        self._url_input.url_changed.connect(self._on_url_changed)
        self._tracklist_input.tracklist_changed.connect(self._on_tracklist_changed)
        self._tracklist_input.template_changed.connect(self._update_ai_availability)
        self._tracklist_input.ai_requested.connect(self._on_ai_requested)
        self._tracklist_input.stop_find_requested.connect(self._on_stop_find)
        self._tracklist_input.undo_find_requested.connect(self._on_undo_find)
        self._tracklist_input.find_banner_dismissed.connect(self._on_find_banner_dismissed)
        self._tracklist_input.open_settings_requested.connect(self._open_settings_dialog)
        self._tracklist_input.api_hint_dismissed.connect(self._on_api_hint_dismissed)
        self._update_ai_availability()

    def _check_ffmpeg(self) -> None:
        """Check if ffmpeg is available."""
        ffmpeg_command = get_settings().resolved_ffmpeg_command()
        if not is_ffmpeg_available(ffmpeg_command):
            QMessageBox.warning(
                self,
                "FFmpeg Not Found",
                f"FFmpeg was not found at '{ffmpeg_command}'.\n\n"
                "Please install FFmpeg, ensure it's in your PATH, or set a "
                "custom path in Settings.\n\n"
                "On Linux: sudo apt install ffmpeg\n"
                "On macOS: brew install ffmpeg\n"
                "On Windows: Download from ffmpeg.org",
            )

    def _on_url_changed(self, url: str) -> None:
        """Handle URL input changes with debouncing."""
        self._url_debounce_timer.stop()

        if url != self._last_fetched_url:
            self._on_video_changed()

        if not url:
            self._video_preview.clear()
            self._last_fetched_url = ""
            self._update_ai_availability()
            return

        if not is_valid_youtube_url(url):
            self._video_preview.clear()
            self._update_ai_availability()
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

        worker = VideoInfoWorker(
            url, comment_limit=preview_comment_limit(get_settings())
        )
        # Ignore results from a fetch that a newer URL has replaced.
        worker.signals.finished.connect(
            lambda info: self._on_video_info_loaded(info)
            if worker is self._video_info_worker else None
        )
        worker.signals.error.connect(
            lambda message: self._on_video_info_error(message)
            if worker is self._video_info_worker else None
        )
        self._video_info_worker = worker

        self._thread_pool.start(worker)

    def _on_video_info_loaded(self, info) -> None:
        """Handle successful video info fetch; may start finding a track list."""
        self._video_preview.set_video_info(info)
        # Set default album name to video title
        self._metadata_input.set_album_placeholder(info.title)
        self._log(video_sources_log_line(info, get_settings()))
        self._update_ai_availability()
        if should_auto_find(get_settings(), info, self._tracklist_input.get_text()):
            self._start_find(info, manual=False)

    def _on_video_info_error(self, message: str) -> None:
        """Handle video info fetch error."""
        self._video_preview.set_error(message)
        self._url_input.set_error(message)
        self._update_ai_availability()

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

        metadata_valid, metadata_error = self._metadata_input.validate()
        if not metadata_valid:
            self._metadata_input.set_error(metadata_error)
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
        """Handle completion; an empty result means the job was cancelled."""
        self._set_ui_busy(False)
        if not output_files:
            self._progress_panel.set_stage("Cancelled")
            self._progress_panel.add_message("Cancelled.", "warn")
            return

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
        self._metadata_input.clear_error()
        self._directory_picker.clear_error()
