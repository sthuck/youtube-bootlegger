"""Central QML backend object exposing application state and business logic."""

from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QThreadPool,
    QTimer,
    Property,
    Signal,
    Slot,
)

from ..core import (
    DEFAULT_TEMPLATE,
    ParseError,
    parse_tracklist_with_template,
    preview_parse,
    validate_template,
)
from ..llm import is_llm_configured, launch_chatgpt_lite_assist
from ..core.settings import LlmProvider, get_settings
from ..core.video_info import VideoInfo
from ..models import DownloadJob
from ..utils import is_ffmpeg_available, is_valid_youtube_url
from ..workers import PipelineWorker, TracklistAiWorker, VideoInfoWorker
from .models import StatusLogModel, TrackPreviewModel


def _getter(attr):
    """Create a property getter for a private attribute."""
    def fget(self):
        return getattr(self, attr)
    return fget


class AppBackend(QObject):
    """Central backend object registered as a QML context property.

    Exposes all application state as Qt properties and business-logic
    entry-points as invokable slots.
    """

    URL_DEBOUNCE_MS = 500

    # ── Notify signals ──────────────────────────────────────────────
    urlErrorChanged = Signal()
    videoTitleChanged = Signal()
    videoChannelChanged = Signal()
    videoDurationChanged = Signal()
    videoViewsChanged = Signal()
    videoDateChanged = Signal()
    videoThumbnailUrlChanged = Signal()
    videoLoadingChanged = Signal()
    videoLoadedChanged = Signal()
    videoErrorChanged = Signal()
    templateErrorChanged = Signal()
    previewStatusChanged = Signal()
    previewValidChanged = Signal()
    albumPlaceholderChanged = Signal()
    metadataErrorChanged = Signal()
    outputDirChanged = Signal()
    dirErrorChanged = Signal()
    busyChanged = Signal()
    progressPercentChanged = Signal()
    progressStageChanged = Signal()
    ffmpegMissingChanged = Signal()
    defaultTemplateChanged = Signal()
    useExternalYtdlpChanged = Signal()
    ytdlpPathChanged = Signal()
    ffmpegPathChanged = Signal()
    llmProviderChanged = Signal()
    llmConfiguredChanged = Signal()
    openaiApiKeyChanged = Signal()
    openaiModelChanged = Signal()
    anthropicApiKeyChanged = Signal()
    anthropicModelChanged = Signal()
    vertexApiKeyChanged = Signal()
    vertexModelChanged = Signal()
    compatibleBaseUrlChanged = Signal()
    compatibleBearerTokenChanged = Signal()
    compatibleModelChanged = Signal()
    currentTemplateChanged = Signal()
    artistNameChanged = Signal()
    albumNameChanged = Signal()
    aiAnalyzingChanged = Signal()
    aiAvailableChanged = Signal()

    showMessage = Signal(str, str, bool)  # title, message, isError

    # ── Qt Properties (read-only from QML) ──────────────────────────
    urlError = Property(str, _getter("_url_error"), notify=urlErrorChanged)
    videoTitle = Property(str, _getter("_video_title"), notify=videoTitleChanged)
    videoChannel = Property(str, _getter("_video_channel"), notify=videoChannelChanged)
    videoDuration = Property(str, _getter("_video_duration"), notify=videoDurationChanged)
    videoViews = Property(str, _getter("_video_views"), notify=videoViewsChanged)
    videoDate = Property(str, _getter("_video_date"), notify=videoDateChanged)
    videoThumbnailUrl = Property(str, _getter("_video_thumbnail_url"), notify=videoThumbnailUrlChanged)
    videoLoading = Property(bool, _getter("_video_loading"), notify=videoLoadingChanged)
    videoLoaded = Property(bool, _getter("_video_loaded"), notify=videoLoadedChanged)
    videoError = Property(str, _getter("_video_error"), notify=videoErrorChanged)
    templateError = Property(str, _getter("_template_error"), notify=templateErrorChanged)
    previewStatus = Property(str, _getter("_preview_status"), notify=previewStatusChanged)
    previewValid = Property(bool, _getter("_preview_valid"), notify=previewValidChanged)
    albumPlaceholder = Property(str, _getter("_album_placeholder"), notify=albumPlaceholderChanged)
    metadataError = Property(str, _getter("_metadata_error"), notify=metadataErrorChanged)
    outputDir = Property(str, _getter("_output_dir"), notify=outputDirChanged)
    dirError = Property(str, _getter("_dir_error"), notify=dirErrorChanged)
    busy = Property(bool, _getter("_busy"), notify=busyChanged)
    progressPercent = Property(float, _getter("_progress_percent"), notify=progressPercentChanged)
    progressStage = Property(str, _getter("_progress_stage"), notify=progressStageChanged)
    ffmpegMissing = Property(bool, _getter("_ffmpeg_missing"), notify=ffmpegMissingChanged)
    defaultTemplate = Property(str, _getter("_default_template"), notify=defaultTemplateChanged)
    useExternalYtdlp = Property(bool, _getter("_use_external_ytdlp"), notify=useExternalYtdlpChanged)
    ytdlpPath = Property(str, _getter("_ytdlp_path"), notify=ytdlpPathChanged)
    ffmpegPath = Property(str, _getter("_ffmpeg_path"), notify=ffmpegPathChanged)
    llmProvider = Property(str, _getter("_llm_provider"), notify=llmProviderChanged)
    llmConfigured = Property(bool, _getter("_llm_configured"), notify=llmConfiguredChanged)
    openaiApiKey = Property(str, _getter("_openai_api_key"), notify=openaiApiKeyChanged)
    openaiModel = Property(str, _getter("_openai_model"), notify=openaiModelChanged)
    anthropicApiKey = Property(str, _getter("_anthropic_api_key"), notify=anthropicApiKeyChanged)
    anthropicModel = Property(str, _getter("_anthropic_model"), notify=anthropicModelChanged)
    vertexApiKey = Property(str, _getter("_vertex_api_key"), notify=vertexApiKeyChanged)
    vertexModel = Property(str, _getter("_vertex_model"), notify=vertexModelChanged)
    compatibleBaseUrl = Property(str, _getter("_compatible_base_url"), notify=compatibleBaseUrlChanged)
    compatibleBearerToken = Property(
        str, _getter("_compatible_bearer_token"), notify=compatibleBearerTokenChanged
    )
    compatibleModel = Property(str, _getter("_compatible_model"), notify=compatibleModelChanged)
    currentTemplate = Property(str, _getter("_template"), notify=currentTemplateChanged)
    artistName = Property(str, _getter("_artist"), notify=artistNameChanged)
    albumName = Property(str, _getter("_album"), notify=albumNameChanged)
    aiAnalyzing = Property(bool, _getter("_ai_analyzing"), notify=aiAnalyzingChanged)
    aiAvailable = Property(bool, _getter("_ai_available"), notify=aiAvailableChanged)

    trackPreviewModel = Property(QObject, _getter("_track_model"), constant=True)
    statusLogModel = Property(QObject, _getter("_log_model"), constant=True)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread_pool = QThreadPool()
        self._current_worker: PipelineWorker | None = None
        self._video_info_worker: VideoInfoWorker | None = None
        self._tracklist_ai_worker: TracklistAiWorker | None = None
        self._video_info: VideoInfo | None = None
        self._last_fetched_url = ""

        self._url_debounce = QTimer(self)
        self._url_debounce.setSingleShot(True)
        self._url_debounce.timeout.connect(self._fetch_video_info)

        self._url = ""
        self._url_error = ""
        self._video_title = ""
        self._video_channel = ""
        self._video_duration = ""
        self._video_views = ""
        self._video_date = ""
        self._video_thumbnail_url = ""
        self._video_loading = False
        self._video_loaded = False
        self._video_error = ""
        self._template = DEFAULT_TEMPLATE
        self._default_template = DEFAULT_TEMPLATE
        self._template_error = ""
        self._tracklist_text = ""
        self._preview_status = ""
        self._preview_valid = True
        self._artist = ""
        self._album = ""
        self._album_placeholder = "Defaults to video title"
        self._metadata_error = ""
        self._output_dir = str(Path.home() / "Music")
        self._dir_error = ""
        self._busy = False
        self._progress_percent = 0.0
        self._progress_stage = "Ready"

        self._app_settings = get_settings()
        self._use_external_ytdlp = self._app_settings.use_external_ytdlp
        self._ytdlp_path = self._app_settings.ytdlp_path
        self._ffmpeg_path = self._app_settings.ffmpeg_path
        self._ffmpeg_missing = not is_ffmpeg_available(self._app_settings.resolved_ffmpeg_command())
        self._llm_provider = self._app_settings.llm_provider.value
        self._llm_configured = is_llm_configured(self._app_settings)
        self._openai_api_key = self._app_settings.openai_api_key
        self._openai_model = self._app_settings.openai_model
        self._anthropic_api_key = self._app_settings.anthropic_api_key
        self._anthropic_model = self._app_settings.anthropic_model
        self._vertex_api_key = self._app_settings.vertex_api_key
        self._vertex_model = self._app_settings.vertex_model
        self._compatible_base_url = self._app_settings.compatible_base_url
        self._compatible_bearer_token = self._app_settings.compatible_bearer_token
        self._compatible_model = self._app_settings.compatible_model
        self._ai_analyzing = False
        self._ai_available = False

        self._track_model = TrackPreviewModel(self)
        self._log_model = StatusLogModel(self)
        self._refresh_ai_available()

    # ── Private helpers ─────────────────────────────────────────────

    def _emit(self, attr, value, signal):
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            signal.emit()

    def _refresh_ai_available(self):
        has_tracklist = bool(self._tracklist_text.strip())
        has_video = self._video_info is not None
        configured = is_llm_configured(self._app_settings)
        self._emit(
            "_ai_available",
            has_tracklist and has_video and configured and not self._ai_analyzing,
            self.aiAvailableChanged,
        )

    def _refresh_llm_configured(self):
        self._emit(
            "_llm_configured",
            is_llm_configured(self._app_settings),
            self.llmConfiguredChanged,
        )
        self._refresh_ai_available()

    # ── Slots (called from QML) ─────────────────────────────────────

    @Slot(str)
    def setUrl(self, url):
        url = url.strip()
        self._url = url
        self._emit("_url_error", "", self.urlErrorChanged)
        self._url_debounce.stop()

        if not url:
            self._clear_video()
            self._last_fetched_url = ""
            return
        if not is_valid_youtube_url(url):
            self._clear_video()
            return
        if url == self._last_fetched_url:
            return
        self._url_debounce.start(self.URL_DEBOUNCE_MS)

    @Slot(str)
    def setTemplate(self, text):
        self._template = text
        self.currentTemplateChanged.emit()
        v = validate_template(text)
        self._emit(
            "_template_error",
            "" if v.is_valid else (v.error or "Invalid template"),
            self.templateErrorChanged,
        )
        self._update_preview()

    @Slot(str)
    def setTracklistText(self, text):
        self._tracklist_text = text
        self._update_preview()
        self._refresh_ai_available()

    @Slot(str)
    def setArtist(self, text):
        self._artist = text.strip()
        self.artistNameChanged.emit()
        self._emit("_metadata_error", "", self.metadataErrorChanged)

    @Slot(str)
    def setAlbum(self, text):
        self._album = text.strip()
        self.albumNameChanged.emit()
        self._emit("_metadata_error", "", self.metadataErrorChanged)

    @Slot(str)
    def setOutputDir(self, path):
        self._output_dir = path
        self._emit("_dir_error", "", self.dirErrorChanged)

    @Slot(bool)
    def setUseExternalYtdlp(self, enabled):
        self._app_settings.use_external_ytdlp = enabled
        self._app_settings.sync()
        self._emit("_use_external_ytdlp", enabled, self.useExternalYtdlpChanged)

    @Slot(str)
    def setYtdlpPath(self, path):
        self._app_settings.ytdlp_path = path
        self._app_settings.sync()
        self._emit("_ytdlp_path", self._app_settings.ytdlp_path, self.ytdlpPathChanged)

    @Slot(str)
    def setFfmpegPath(self, path):
        self._app_settings.ffmpeg_path = path
        self._app_settings.sync()
        self._emit("_ffmpeg_path", self._app_settings.ffmpeg_path, self.ffmpegPathChanged)
        self._emit(
            "_ffmpeg_missing",
            not is_ffmpeg_available(self._app_settings.resolved_ffmpeg_command()),
            self.ffmpegMissingChanged,
        )

    @Slot(str)
    def setLlmProvider(self, provider):
        try:
            parsed = LlmProvider(provider)
        except ValueError:
            parsed = LlmProvider.CHATGPT_LITE
        if parsed == LlmProvider.NONE:
            parsed = LlmProvider.CHATGPT_LITE
        self._app_settings.llm_provider = parsed
        self._app_settings.sync()
        self._emit("_llm_provider", parsed.value, self.llmProviderChanged)
        self._refresh_llm_configured()

    @Slot(str)
    def setOpenaiApiKey(self, value):
        self._app_settings.openai_api_key = value
        self._app_settings.sync()
        self._emit("_openai_api_key", self._app_settings.openai_api_key, self.openaiApiKeyChanged)
        self._refresh_llm_configured()

    @Slot(str)
    def setOpenaiModel(self, value):
        self._app_settings.openai_model = value
        self._app_settings.sync()
        self._emit("_openai_model", self._app_settings.openai_model, self.openaiModelChanged)

    @Slot(str)
    def setAnthropicApiKey(self, value):
        self._app_settings.anthropic_api_key = value
        self._app_settings.sync()
        self._emit(
            "_anthropic_api_key",
            self._app_settings.anthropic_api_key,
            self.anthropicApiKeyChanged,
        )
        self._refresh_llm_configured()

    @Slot(str)
    def setAnthropicModel(self, value):
        self._app_settings.anthropic_model = value
        self._app_settings.sync()
        self._emit(
            "_anthropic_model",
            self._app_settings.anthropic_model,
            self.anthropicModelChanged,
        )

    @Slot(str)
    def setVertexApiKey(self, value):
        self._app_settings.vertex_api_key = value
        self._app_settings.sync()
        self._emit("_vertex_api_key", self._app_settings.vertex_api_key, self.vertexApiKeyChanged)
        self._refresh_llm_configured()

    @Slot(str)
    def setVertexModel(self, value):
        self._app_settings.vertex_model = value
        self._app_settings.sync()
        self._emit("_vertex_model", self._app_settings.vertex_model, self.vertexModelChanged)

    @Slot(str)
    def setCompatibleBaseUrl(self, value):
        self._app_settings.compatible_base_url = value
        self._app_settings.sync()
        self._emit(
            "_compatible_base_url",
            self._app_settings.compatible_base_url,
            self.compatibleBaseUrlChanged,
        )
        self._refresh_llm_configured()

    @Slot(str)
    def setCompatibleBearerToken(self, value):
        self._app_settings.compatible_bearer_token = value
        self._app_settings.sync()
        self._emit(
            "_compatible_bearer_token",
            self._app_settings.compatible_bearer_token,
            self.compatibleBearerTokenChanged,
        )

    @Slot(str)
    def setCompatibleModel(self, value):
        self._app_settings.compatible_model = value
        self._app_settings.sync()
        self._emit(
            "_compatible_model",
            self._app_settings.compatible_model,
            self.compatibleModelChanged,
        )

    @Slot()
    def analyzeTracklistWithAi(self):
        if self._ai_analyzing:
            return
        if self._video_info is None:
            self.showMessage.emit(
                "AI Assist",
                "Please wait for video info to load before using AI.",
                True,
            )
            return
        if not self._tracklist_text.strip():
            return
        if not is_llm_configured(self._app_settings):
            self.showMessage.emit(
                "AI Assist",
                "LLM is not configured. Add API credentials in Settings.",
                True,
            )
            return

        if self._app_settings.llm_provider == LlmProvider.CHATGPT_LITE:
            ok, message = launch_chatgpt_lite_assist(
                self._video_info.title,
                self._tracklist_text,
            )
            self.showMessage.emit("AI Assist", message, not ok)
            return

        self._emit("_ai_analyzing", True, self.aiAnalyzingChanged)

        self._tracklist_ai_worker = TracklistAiWorker(
            self._app_settings,
            self._video_info.title,
            self._tracklist_text,
        )
        self._tracklist_ai_worker.signals.finished.connect(self._on_ai_finished)
        self._tracklist_ai_worker.signals.error.connect(self._on_ai_error)
        self._thread_pool.start(self._tracklist_ai_worker)

    def _on_ai_finished(self, result):
        self._emit("_ai_analyzing", False, self.aiAnalyzingChanged)
        self.setTemplate(result.template)
        if result.artist_name:
            self.setArtist(result.artist_name)
        if result.album_name:
            self.setAlbum(result.album_name)
        self._refresh_ai_available()

    def _on_ai_error(self, message: str):
        self._emit("_ai_analyzing", False, self.aiAnalyzingChanged)
        self._refresh_ai_available()
        self.showMessage.emit("AI Assist", message, True)

    @Slot()
    def startPipeline(self):
        self._emit("_url_error", "", self.urlErrorChanged)
        self._emit("_dir_error", "", self.dirErrorChanged)
        self._emit("_metadata_error", "", self.metadataErrorChanged)

        if not self._url:
            self._emit("_url_error", "Please enter a YouTube URL", self.urlErrorChanged)
            return
        if not is_valid_youtube_url(self._url):
            self._emit("_url_error", "Please enter a valid YouTube URL", self.urlErrorChanged)
            return
        if self._video_info is None:
            self._emit("_url_error", "Please wait for video info to load", self.urlErrorChanged)
            return

        template = self._template or DEFAULT_TEMPLATE
        tv = validate_template(template)
        if not tv.is_valid:
            self._emit(
                "_template_error",
                f"Invalid template: {tv.error}",
                self.templateErrorChanged,
            )
            return

        text = self._tracklist_text
        if not text.strip():
            return

        try:
            tracks = parse_tracklist_with_template(text, template)
            if not tracks:
                return
        except ParseError:
            return

        if not self._artist and not self._album:
            self._emit(
                "_metadata_error",
                "Please enter an artist name or album name",
                self.metadataErrorChanged,
            )
            return

        if not self._output_dir.strip():
            self._emit("_dir_error", "Please select an output directory", self.dirErrorChanged)
            return

        artist = self._artist or None
        album = self._album or self._video_info.title

        job = DownloadJob(
            url=self._url,
            output_dir=Path(self._output_dir),
            tracks=tuple(tracks),
            artist=artist,
            album=album,
            thumbnail_url=self._video_info.thumbnail_url,
        )
        self._run_pipeline(job)

    @Slot()
    def cancelPipeline(self):
        if self._current_worker:
            self._current_worker.cancel()
            self._log_model.append("Cancelling...", "warn")

    # ── Video info fetching ─────────────────────────────────────────

    def _fetch_video_info(self):
        url = self._url
        if not url or not is_valid_youtube_url(url):
            return
        if url == self._last_fetched_url:
            return

        self._last_fetched_url = url
        self._set_video_loading()

        self._video_info_worker = VideoInfoWorker(url)
        self._video_info_worker.signals.finished.connect(self._on_video_info_loaded)
        self._video_info_worker.signals.error.connect(self._on_video_info_error)
        self._thread_pool.start(self._video_info_worker)

    def _on_video_info_loaded(self, info: VideoInfo):
        self._video_info = info
        title = info.title[:77] + "..." if len(info.title) > 80 else info.title
        self._emit("_video_title", title, self.videoTitleChanged)
        self._emit("_video_channel", info.channel, self.videoChannelChanged)
        self._emit("_video_duration", f"Duration: {info.duration_string}", self.videoDurationChanged)
        self._emit("_video_views", info.formatted_views, self.videoViewsChanged)
        date_str = f"Uploaded: {info.formatted_date}" if info.formatted_date else ""
        self._emit("_video_date", date_str, self.videoDateChanged)
        self._emit("_video_thumbnail_url", info.thumbnail_url, self.videoThumbnailUrlChanged)
        self._emit("_video_loading", False, self.videoLoadingChanged)
        self._emit("_video_loaded", True, self.videoLoadedChanged)
        self._emit("_video_error", "", self.videoErrorChanged)
        self._emit("_album_placeholder", info.title, self.albumPlaceholderChanged)
        self._refresh_ai_available()

    def _on_video_info_error(self, message: str):
        self._emit("_video_error", message, self.videoErrorChanged)
        self._emit("_video_loading", False, self.videoLoadingChanged)
        self._emit("_video_loaded", False, self.videoLoadedChanged)
        self._emit("_url_error", message, self.urlErrorChanged)
        self._refresh_ai_available()

    def _set_video_loading(self):
        self._video_info = None
        self._emit("_video_title", "Loading video info...", self.videoTitleChanged)
        self._emit("_video_channel", "", self.videoChannelChanged)
        self._emit("_video_duration", "", self.videoDurationChanged)
        self._emit("_video_views", "", self.videoViewsChanged)
        self._emit("_video_date", "", self.videoDateChanged)
        self._emit("_video_loading", True, self.videoLoadingChanged)
        self._emit("_video_loaded", False, self.videoLoadedChanged)
        self._emit("_video_error", "", self.videoErrorChanged)
        self._refresh_ai_available()

    def _clear_video(self):
        self._video_info = None
        for attr, sig in [
            ("_video_title", self.videoTitleChanged),
            ("_video_channel", self.videoChannelChanged),
            ("_video_duration", self.videoDurationChanged),
            ("_video_views", self.videoViewsChanged),
            ("_video_date", self.videoDateChanged),
            ("_video_thumbnail_url", self.videoThumbnailUrlChanged),
            ("_video_error", self.videoErrorChanged),
        ]:
            self._emit(attr, "", sig)
        self._emit("_video_loading", False, self.videoLoadingChanged)
        self._emit("_video_loaded", False, self.videoLoadedChanged)
        self._refresh_ai_available()

    # ── Preview ─────────────────────────────────────────────────────

    def _update_preview(self):
        template = self._template or DEFAULT_TEMPLATE
        preview = preview_parse(self._tracklist_text, template)

        self._track_model.update(preview.tracks)

        if preview.total_lines == 0:
            self._emit("_preview_status", "", self.previewStatusChanged)
            self._emit("_preview_valid", True, self.previewValidChanged)
        elif preview.is_valid:
            self._emit("_preview_status", f"{preview.total_lines} tracks", self.previewStatusChanged)
            self._emit("_preview_valid", True, self.previewValidChanged)
        else:
            self._emit("_preview_status", f"{preview.error_count} error(s)", self.previewStatusChanged)
            self._emit("_preview_valid", False, self.previewValidChanged)

    # ── Pipeline execution ──────────────────────────────────────────

    def _run_pipeline(self, job: DownloadJob):
        self._emit("_busy", True, self.busyChanged)
        self._log_model.clear_all()
        self._emit("_progress_percent", 0.0, self.progressPercentChanged)
        self._emit("_progress_stage", "Starting...", self.progressStageChanged)
        self._log_model.append("Starting...", "info")

        self._current_worker = PipelineWorker(job)
        self._current_worker.signals.started.connect(self._on_worker_started)
        self._current_worker.signals.progress.connect(self._on_progress)
        self._current_worker.signals.log.connect(self._on_log)
        self._current_worker.signals.finished.connect(self._on_finished)
        self._current_worker.signals.error.connect(self._on_error)
        self._thread_pool.start(self._current_worker)

    def _on_worker_started(self):
        self._log_model.append("Worker started", "info")

    def _on_progress(self, stage: str, percent: float, message: str):
        display = {
            "download": "Downloading",
            "split": "Splitting",
            "tagging": "Tagging",
            "complete": "Complete",
        }.get(stage, stage.title())

        self._emit("_progress_stage", f"{display}: {int(percent)}%", self.progressStageChanged)
        self._emit("_progress_percent", percent, self.progressPercentChanged)
        self._log_model.append(message, "info")

    def _on_log(self, message: str):
        self._log_model.append(message, "debug")

    def _on_finished(self, output_files: list):
        self._emit("_busy", False, self.busyChanged)
        self._emit("_progress_percent", 100.0, self.progressPercentChanged)
        self._emit("_progress_stage", "Complete!", self.progressStageChanged)
        self._log_model.append(f"Successfully created {len(output_files)} track(s)!", "info")
        for p in output_files:
            self._log_model.append(f"  → {p}", "info")
        self.showMessage.emit(
            "Complete",
            f"Successfully split audio into {len(output_files)} track(s)!",
            False,
        )

    def _on_error(self, message: str):
        self._emit("_busy", False, self.busyChanged)
        self._emit("_progress_stage", "Error", self.progressStageChanged)
        self._log_model.append(message, "error")
        self.showMessage.emit("Error", message, True)
