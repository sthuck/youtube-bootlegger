"""UI-agnostic orchestration shared by the widget and QML front-ends.

The controller owns all application state and workflow: URL debouncing, video
info fetching, template validation and preview, AI assist, settings writes, and
the download/split pipeline lifecycle. Front-ends bind to its signals and
forward user input to its setters; they contain no workflow logic of their own.
"""

from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, QTimer, Signal

from ..core import (
    DEFAULT_TEMPLATE,
    ParseError,
    parse_tracklist_with_template,
    preview_parse,
    validate_template,
)
from ..core.settings import AppSettings, LlmProvider, get_settings
from ..core.video_info import VideoInfo
from ..llm import is_llm_configured, launch_chatgpt_lite_assist
from ..models import DownloadJob
from ..utils import is_ffmpeg_available, is_valid_youtube_url
from ..workers import PipelineWorker, TracklistAiWorker, VideoInfoWorker
from .settings_schema import SETTING_FIELDS, SETTING_FIELDS_BY_NAME

STAGE_LABELS = {
    "download": "Downloading",
    "split": "Splitting",
    "tagging": "Tagging",
    "complete": "Complete",
}


def stage_label(stage: str) -> str:
    """Return the human-readable label for a pipeline stage id."""
    return STAGE_LABELS.get(stage, stage.title())


class AppController(QObject):
    """Owns application state and workflow for every front-end."""

    URL_DEBOUNCE_MS = 500

    # ── URL and video info ──────────────────────────────────────────
    urlErrorChanged = Signal(str)
    videoLoadingStarted = Signal()
    videoInfoLoaded = Signal(object)  # VideoInfo
    videoInfoFailed = Signal(str)
    videoCleared = Signal()

    # ── Tracklist and template ──────────────────────────────────────
    templateChanged = Signal(str)
    templateErrorChanged = Signal(str)
    tracklistErrorChanged = Signal(str)
    previewChanged = Signal(object)  # ParsePreview

    # ── Metadata ────────────────────────────────────────────────────
    artistChanged = Signal(str)
    albumChanged = Signal(str)
    albumPlaceholderChanged = Signal(str)
    metadataErrorChanged = Signal(str)

    # ── Output directory ────────────────────────────────────────────
    outputDirChanged = Signal(str)
    dirErrorChanged = Signal(str)

    # ── AI assist ───────────────────────────────────────────────────
    aiAvailableChanged = Signal(bool)
    aiAnalyzingChanged = Signal(bool)
    aiExtractionApplied = Signal(object)  # TracklistExtraction
    aiMessage = Signal(str, bool)  # message, is_error

    # ── Pipeline ────────────────────────────────────────────────────
    busyChanged = Signal(bool)
    progressChanged = Signal(str, float, str)  # stage, percent, message
    logMessage = Signal(str, str)  # message, level
    pipelineFinished = Signal(list)  # list[str]
    pipelineFailed = Signal(str)

    # ── Settings ────────────────────────────────────────────────────
    settingChanged = Signal(str, object)  # AppSettings attribute name, value
    ffmpegAvailableChanged = Signal(bool)
    llmConfiguredChanged = Signal(bool)

    def __init__(self, settings: AppSettings | None = None, parent=None):
        """Initialize the controller.

        Args:
            settings: Application settings. Defaults to the shared singleton.
            parent: Optional QObject parent.
        """
        super().__init__(parent)
        self._settings = settings or get_settings()
        self._thread_pool = QThreadPool()

        self._pipeline_worker: PipelineWorker | None = None
        self._video_info_worker: VideoInfoWorker | None = None
        self._ai_worker: TracklistAiWorker | None = None

        self._url = ""
        self._last_fetched_url = ""
        self._video_info: VideoInfo | None = None
        self._template = DEFAULT_TEMPLATE
        self._tracklist_text = ""
        self._artist = ""
        self._album = ""
        self._output_dir = str(Path.home() / "Music")
        self._busy = False
        self._ai_analyzing = False
        self._ai_available = False

        self._ffmpeg_available = is_ffmpeg_available(
            self._settings.resolved_ffmpeg_command()
        )
        self._llm_configured = is_llm_configured(self._settings)

        self._url_debounce = QTimer(self)
        self._url_debounce.setSingleShot(True)
        self._url_debounce.timeout.connect(self._fetch_video_info)

    # ── Read-only state ─────────────────────────────────────────────

    @property
    def settings(self) -> AppSettings:
        """The settings object backing this controller."""
        return self._settings

    @property
    def url(self) -> str:
        """Current YouTube URL."""
        return self._url

    @property
    def template(self) -> str:
        """Current tracklist template, never empty."""
        return self._template or DEFAULT_TEMPLATE

    @property
    def tracklist_text(self) -> str:
        """Raw tracklist text as typed by the user."""
        return self._tracklist_text

    @property
    def artist(self) -> str:
        """Artist name for metadata tags."""
        return self._artist

    @property
    def album(self) -> str:
        """Album name for metadata tags."""
        return self._album

    @property
    def output_dir(self) -> str:
        """Directory where split tracks are written."""
        return self._output_dir

    @property
    def video_info(self) -> VideoInfo | None:
        """Loaded video info, or None when nothing is loaded."""
        return self._video_info

    @property
    def busy(self) -> bool:
        """True while the pipeline is running."""
        return self._busy

    @property
    def ai_analyzing(self) -> bool:
        """True while an LLM extraction is in flight."""
        return self._ai_analyzing

    @property
    def ai_available(self) -> bool:
        """True when AI assist can be triggered right now."""
        return self._ai_available

    @property
    def ffmpeg_available(self) -> bool:
        """True when the configured ffmpeg executable was found."""
        return self._ffmpeg_available

    @property
    def llm_configured(self) -> bool:
        """True when the active LLM provider has the credentials it needs."""
        return self._llm_configured

    # ── Input setters ───────────────────────────────────────────────

    def set_url(self, url: str) -> None:
        """Record a new URL and schedule a debounced video info fetch."""
        url = url.strip()
        if url == self._url:
            return
        self._url = url
        self.urlErrorChanged.emit("")
        self._url_debounce.stop()

        if not url:
            self._last_fetched_url = ""
            self._clear_video()
            return
        if not is_valid_youtube_url(url):
            self._clear_video()
            return
        if url == self._last_fetched_url:
            return
        self._url_debounce.start(self.URL_DEBOUNCE_MS)

    def set_template(self, text: str) -> None:
        """Record a new template, then revalidate and refresh the preview."""
        if text == self._template:
            return
        self._template = text
        self.templateChanged.emit(text)

        validation = validate_template(text)
        self.templateErrorChanged.emit(
            "" if validation.is_valid else (validation.error or "Invalid template")
        )
        self._update_preview()

    def set_tracklist_text(self, text: str) -> None:
        """Record new tracklist text and refresh the preview."""
        if text == self._tracklist_text:
            return
        self._tracklist_text = text
        self.tracklistErrorChanged.emit("")
        self._update_preview()
        self._refresh_ai_available()

    def set_artist(self, text: str) -> None:
        """Record the artist name."""
        text = text.strip()
        if text == self._artist:
            return
        self._artist = text
        self.artistChanged.emit(text)
        self.metadataErrorChanged.emit("")

    def set_album(self, text: str) -> None:
        """Record the album name."""
        text = text.strip()
        if text == self._album:
            return
        self._album = text
        self.albumChanged.emit(text)
        self.metadataErrorChanged.emit("")

    def set_output_dir(self, path: str) -> None:
        """Record the output directory."""
        if path == self._output_dir:
            return
        self._output_dir = path
        self.outputDirChanged.emit(path)
        self.dirErrorChanged.emit("")

    # ── Settings ────────────────────────────────────────────────────

    def read_setting(self, name: str):
        """Return the current value of the named setting."""
        return SETTING_FIELDS_BY_NAME[name].read_from(self._settings)

    def read_all_settings(self) -> dict:
        """Return every setting keyed by its AppSettings attribute name."""
        return {field.name: field.read_from(self._settings) for field in SETTING_FIELDS}

    def update_setting(self, name: str, value) -> None:
        """Persist one setting and refresh anything that depends on it.

        Args:
            name: AppSettings attribute name, as listed in SETTING_FIELDS.
            value: New value; coerced by the field's schema entry if needed.
        """
        field = SETTING_FIELDS_BY_NAME[name]
        field.write_to(self._settings, value)
        self._settings.sync()
        self.settingChanged.emit(name, field.read_from(self._settings))

        if field.affects_ffmpeg:
            self.refresh_ffmpeg_available()
        if field.affects_llm_config:
            self._refresh_llm_configured()

    def refresh_ffmpeg_available(self) -> None:
        """Re-check the configured ffmpeg executable and notify on change."""
        available = is_ffmpeg_available(self._settings.resolved_ffmpeg_command())
        if available != self._ffmpeg_available:
            self._ffmpeg_available = available
            self.ffmpegAvailableChanged.emit(available)

    def _refresh_llm_configured(self) -> None:
        configured = is_llm_configured(self._settings)
        if configured != self._llm_configured:
            self._llm_configured = configured
            self.llmConfiguredChanged.emit(configured)
        self._refresh_ai_available()

    # ── AI assist ───────────────────────────────────────────────────

    def _refresh_ai_available(self) -> None:
        available = (
            bool(self._tracklist_text.strip())
            and self._video_info is not None
            and is_llm_configured(self._settings)
            and not self._ai_analyzing
        )
        if available != self._ai_available:
            self._ai_available = available
            self.aiAvailableChanged.emit(available)

    def analyze_tracklist_with_ai(self) -> None:
        """Infer template and metadata from the tracklist via the active LLM."""
        if self._ai_analyzing:
            return
        if self._video_info is None:
            self.aiMessage.emit(
                "Please wait for video info to load before using AI.", True
            )
            return
        if not self._tracklist_text.strip():
            return
        if not is_llm_configured(self._settings):
            self.aiMessage.emit(
                "LLM is not configured. Add API credentials in Settings.", True
            )
            return

        if self._settings.llm_provider == LlmProvider.CHATGPT_LITE:
            ok, message = launch_chatgpt_lite_assist(
                self._video_info.title,
                self._tracklist_text,
            )
            self.aiMessage.emit(message, not ok)
            return

        self._set_ai_analyzing(True)

        self._ai_worker = TracklistAiWorker(
            self._settings,
            self._video_info.title,
            self._tracklist_text,
        )
        self._ai_worker.setAutoDelete(False)
        self._ai_worker.signals.finished.connect(self._on_ai_finished)
        self._ai_worker.signals.error.connect(self._on_ai_error)
        self._thread_pool.start(self._ai_worker)

    def _set_ai_analyzing(self, analyzing: bool) -> None:
        if analyzing != self._ai_analyzing:
            self._ai_analyzing = analyzing
            self.aiAnalyzingChanged.emit(analyzing)
        self._refresh_ai_available()

    def _on_ai_finished(self, result) -> None:
        self._ai_worker = None
        self._set_ai_analyzing(False)
        self.set_template(result.template)
        if result.artist_name:
            self.set_artist(result.artist_name)
        if result.album_name:
            self.set_album(result.album_name)
        self.aiExtractionApplied.emit(result)

    def _on_ai_error(self, message: str) -> None:
        self._ai_worker = None
        self._set_ai_analyzing(False)
        self.aiMessage.emit(message, True)

    # ── Video info ──────────────────────────────────────────────────

    def _fetch_video_info(self) -> None:
        url = self._url
        if not url or not is_valid_youtube_url(url):
            return
        if url == self._last_fetched_url:
            return

        self._last_fetched_url = url
        self._video_info = None
        self.videoLoadingStarted.emit()
        self._refresh_ai_available()

        self._video_info_worker = VideoInfoWorker(url)
        self._video_info_worker.setAutoDelete(False)
        self._video_info_worker.signals.finished.connect(self._on_video_info_loaded)
        self._video_info_worker.signals.error.connect(self._on_video_info_error)
        self._thread_pool.start(self._video_info_worker)

    def _on_video_info_loaded(self, info: VideoInfo) -> None:
        self._video_info_worker = None
        self._video_info = info
        self.videoInfoLoaded.emit(info)
        self.albumPlaceholderChanged.emit(info.title)
        self._refresh_ai_available()

    def _on_video_info_error(self, message: str) -> None:
        self._video_info_worker = None
        self._video_info = None
        self.videoInfoFailed.emit(message)
        self.urlErrorChanged.emit(message)
        self._refresh_ai_available()

    def _clear_video(self) -> None:
        self._video_info = None
        self.videoCleared.emit()
        self._refresh_ai_available()

    # ── Preview ─────────────────────────────────────────────────────

    def _update_preview(self) -> None:
        self.previewChanged.emit(preview_parse(self._tracklist_text, self.template))

    def current_preview(self):
        """Return a fresh preview of the current tracklist and template."""
        return preview_parse(self._tracklist_text, self.template)

    # ── Pipeline ────────────────────────────────────────────────────

    def _clear_errors(self) -> None:
        self.urlErrorChanged.emit("")
        self.templateErrorChanged.emit("")
        self.tracklistErrorChanged.emit("")
        self.metadataErrorChanged.emit("")
        self.dirErrorChanged.emit("")

    def _validate_output_dir(self) -> str:
        """Return an error message for the output directory, or "" if usable."""
        if not self._output_dir.strip():
            return "Please select an output directory"

        path = Path(self._output_dir.strip())
        if path.exists() and not path.is_dir():
            return "Selected path is not a directory"

        existing = path if path.exists() else path.parent
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        if not existing.exists():
            return "Parent directory does not exist"
        return ""

    def build_job(self) -> DownloadJob | None:
        """Validate all input and build a DownloadJob.

        Emits the relevant ``*ErrorChanged`` signal and returns None when any
        step fails, so both front-ends report the same problems the same way.

        Returns:
            A ready-to-run DownloadJob, or None when validation failed.
        """
        self._clear_errors()

        if not self._url:
            self.urlErrorChanged.emit("Please enter a YouTube URL")
            return None
        if not is_valid_youtube_url(self._url):
            self.urlErrorChanged.emit("Please enter a valid YouTube URL")
            return None
        if self._video_info is None:
            self.urlErrorChanged.emit("Please wait for video info to load")
            return None

        template = self.template
        validation = validate_template(template)
        if not validation.is_valid:
            self.templateErrorChanged.emit(f"Invalid template: {validation.error}")
            return None

        if not self._tracklist_text.strip():
            self.tracklistErrorChanged.emit("Please enter at least one track")
            return None

        try:
            tracks = parse_tracklist_with_template(self._tracklist_text, template)
        except ParseError as e:
            self.tracklistErrorChanged.emit(str(e))
            return None
        if not tracks:
            self.tracklistErrorChanged.emit("No valid tracks found")
            return None

        if not self._artist and not self._album:
            self.metadataErrorChanged.emit("Please enter an artist name or album name")
            return None

        dir_error = self._validate_output_dir()
        if dir_error:
            self.dirErrorChanged.emit(dir_error)
            return None

        return DownloadJob(
            url=self._url,
            output_dir=Path(self._output_dir.strip()),
            tracks=tuple(tracks),
            artist=self._artist or None,
            album=self._album or self._video_info.title,
            thumbnail_url=self._video_info.thumbnail_url,
        )

    def start_pipeline(self) -> bool:
        """Validate input and start the download/split pipeline.

        Returns:
            True when a job was started, False when validation failed.
        """
        job = self.build_job()
        if job is None:
            return False

        self._set_busy(True)
        self.progressChanged.emit("starting", 0.0, "Starting...")
        self.logMessage.emit("Starting...", "info")

        self._pipeline_worker = PipelineWorker(job)
        self._pipeline_worker.setAutoDelete(False)
        signals = self._pipeline_worker.signals
        signals.started.connect(self._on_pipeline_started)
        signals.progress.connect(self._on_pipeline_progress)
        signals.log.connect(self._on_pipeline_log)
        signals.finished.connect(self._on_pipeline_finished)
        signals.error.connect(self._on_pipeline_error)
        self._thread_pool.start(self._pipeline_worker)
        return True

    def cancel_pipeline(self) -> None:
        """Request cancellation of the running pipeline."""
        if self._pipeline_worker is not None:
            self._pipeline_worker.cancel()
            self.logMessage.emit("Cancelling...", "warn")

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    def _on_pipeline_started(self) -> None:
        self.logMessage.emit("Worker started", "info")

    def _on_pipeline_progress(self, stage: str, percent: float, message: str) -> None:
        self.progressChanged.emit(stage, percent, message)
        self.logMessage.emit(message, "info")

    def _on_pipeline_log(self, message: str) -> None:
        self.logMessage.emit(message, "debug")

    def _on_pipeline_finished(self, output_files: list) -> None:
        self._pipeline_worker = None
        self._set_busy(False)
        self.progressChanged.emit("complete", 100.0, "Complete!")
        self.logMessage.emit(
            f"Successfully created {len(output_files)} track(s)!", "info"
        )
        for path in output_files:
            self.logMessage.emit(f"  → {path}", "info")
        self.pipelineFinished.emit(output_files)

    def _on_pipeline_error(self, message: str) -> None:
        self._pipeline_worker = None
        self._set_busy(False)
        self.logMessage.emit(message, "error")
        self.pipelineFailed.emit(message)
