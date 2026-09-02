"""Main application window.

A thin view over :class:`AppController`: it lays widgets out, forwards their
input to the controller, and renders whatever the controller reports back.
All workflow and validation logic lives in the controller, shared with the
QML front-end.
"""

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..controller import AppController, stage_label
from ..resources import APP_LOGO_PNG
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

    def __init__(self, controller: AppController | None = None):
        """Initialize the window.

        Args:
            controller: Shared application controller. Created if omitted.
        """
        super().__init__()
        self._controller = controller or AppController(parent=self)
        self._setup_ui()
        self._setup_menu()
        self._connect_widgets()
        self._connect_controller()
        self._sync_initial_state()

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
        """Open the settings dialog; the controller applies any changes."""
        SettingsDialog(self._controller, self).exec()

    # ── Wiring ──────────────────────────────────────────────────────

    def _connect_widgets(self) -> None:
        """Forward widget input to the controller."""
        c = self._controller
        self._url_input.url_changed.connect(c.set_url)
        self._tracklist_input.template_changed.connect(c.set_template)
        self._tracklist_input.tracklist_changed.connect(c.set_tracklist_text)
        self._tracklist_input.ai_requested.connect(c.analyze_tracklist_with_ai)
        self._metadata_input.artist_changed.connect(c.set_artist)
        self._metadata_input.album_changed.connect(c.set_album)
        self._directory_picker.directory_changed.connect(c.set_output_dir)
        # Wrapped so QAbstractButton.clicked's "checked" argument is dropped.
        self._start_button.clicked.connect(lambda: c.start_pipeline())
        self._cancel_button.clicked.connect(lambda: c.cancel_pipeline())

    def _connect_controller(self) -> None:
        """Render controller state changes in the widgets."""
        c = self._controller

        c.urlErrorChanged.connect(self._url_input.set_error)
        c.videoLoadingStarted.connect(self._video_preview.set_loading)
        c.videoInfoLoaded.connect(self._video_preview.set_video_info)
        c.videoInfoFailed.connect(self._video_preview.set_error)
        c.videoCleared.connect(self._video_preview.clear)

        c.templateChanged.connect(self._tracklist_input.set_template)
        c.templateErrorChanged.connect(self._tracklist_input.set_template_error)
        c.tracklistErrorChanged.connect(self._tracklist_input.set_error)
        c.previewChanged.connect(self._tracklist_input.set_preview)

        c.artistChanged.connect(self._metadata_input.set_artist)
        c.albumChanged.connect(self._metadata_input.set_album)
        c.albumPlaceholderChanged.connect(self._metadata_input.set_album_placeholder)
        c.metadataErrorChanged.connect(self._metadata_input.set_error)
        c.dirErrorChanged.connect(self._directory_picker.set_error)

        c.aiAvailableChanged.connect(self._tracklist_input.set_ai_available)
        c.aiAnalyzingChanged.connect(self._tracklist_input.set_ai_loading)
        c.aiMessage.connect(self._on_ai_message)

        c.busyChanged.connect(self._on_busy_changed)
        c.progressChanged.connect(self._on_progress)
        c.logMessage.connect(self._progress_panel.add_message)
        c.pipelineFinished.connect(self._on_finished)
        c.pipelineFailed.connect(self._on_error)

        c.ffmpegAvailableChanged.connect(self._on_ffmpeg_availability_changed)

    def _sync_initial_state(self) -> None:
        """Push the controller's starting state into the freshly built widgets."""
        self._tracklist_input.set_ai_available(self._controller.ai_available)
        self._tracklist_input.set_preview(self._controller.current_preview())
        if not self._controller.ffmpeg_available:
            self._warn_ffmpeg_missing()

    # ── Controller event handlers ───────────────────────────────────

    def _on_ai_message(self, message: str, is_error: bool) -> None:
        """Show an AI assist message."""
        if is_error:
            QMessageBox.warning(self, "AI Assist", message)
        else:
            QMessageBox.information(self, "AI Assist", message)

    def _on_busy_changed(self, busy: bool) -> None:
        """Enable/disable UI during processing."""
        if busy:
            self._progress_panel.clear()
            self._progress_panel.reset_style()

        self._url_input.set_enabled(not busy)
        self._tracklist_input.set_enabled(not busy)
        self._metadata_input.set_enabled(not busy)
        self._directory_picker.set_enabled(not busy)
        self._start_button.setEnabled(not busy)
        self._cancel_button.setEnabled(busy)

    def _on_progress(self, stage: str, percent: float, _message: str) -> None:
        """Update the progress display."""
        if stage == "starting":
            self._progress_panel.set_stage("Starting...")
        else:
            self._progress_panel.set_stage(f"{stage_label(stage)}: {int(percent)}%")
        self._progress_panel.set_progress(percent)

    def _on_finished(self, output_files: list) -> None:
        """Handle successful completion."""
        self._progress_panel.set_complete()
        QMessageBox.information(
            self,
            "Complete",
            f"Successfully split audio into {len(output_files)} track(s)!",
        )

    def _on_error(self, message: str) -> None:
        """Display a pipeline error."""
        self._progress_panel.set_error()
        QMessageBox.critical(self, "Error", message)

    def _on_ffmpeg_availability_changed(self, available: bool) -> None:
        """Warn when a settings change made ffmpeg unreachable."""
        if not available:
            self._warn_ffmpeg_missing()

    def _warn_ffmpeg_missing(self) -> None:
        """Tell the user where ffmpeg was expected and how to install it."""
        command = self._controller.settings.resolved_ffmpeg_command()
        QMessageBox.warning(
            self,
            "FFmpeg Not Found",
            f"FFmpeg was not found at '{command}'.\n\n"
            "Please install FFmpeg, ensure it's in your PATH, or set a "
            "custom path in Settings.\n\n"
            "On Linux: sudo apt install ffmpeg\n"
            "On macOS: brew install ffmpeg\n"
            "On Windows: Download from ffmpeg.org",
        )
