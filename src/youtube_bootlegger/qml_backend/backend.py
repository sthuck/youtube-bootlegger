"""QML adapter exposing :class:`AppController` state as Qt properties.

This object holds no workflow logic; it translates controller signals into the
property/notify shape QML binds to, and forwards QML calls back. Settings
properties, their notify signals and their setter slots are generated from
``SETTING_FIELDS`` rather than hand-written one per field.
"""

from PySide6.QtCore import (
    Property,
    QObject,
    Signal,
    Slot,
)

from ..controller import (
    SETTING_FIELDS,
    SETTING_FIELDS_BY_NAME,
    AppController,
    stage_label,
)
from .help_content import build_help_content
from .models import StatusLogModel, TrackPreviewModel

MAX_TITLE_LENGTH = 80


def _getter(attr):
    """Create a property getter for a private attribute."""
    def fget(self):
        return getattr(self, attr)
    return fget


def _setting_getter(field):
    """Create a property getter reading a cached settings value."""
    def fget(self):
        return self._setting_values[field.name]
    return fget


def _setting_slot(field):
    """Create an invokable setter forwarding to the controller."""
    def setter(self, value):
        self._controller.update_setting(field.name, value)
    setter.__name__ = field.slot_name
    return Slot(field.value_type)(setter)


class _BackendMeta(type(QObject)):
    """Injects one property/signal/slot triple per declared setting."""

    def __new__(mcls, name, bases, namespace, **kwargs):
        for field in SETTING_FIELDS:
            notify = Signal()
            namespace[field.signal_name] = notify
            namespace[field.qml_name] = Property(
                field.value_type, _setting_getter(field), notify=notify
            )
            namespace[field.slot_name] = _setting_slot(field)
        return super().__new__(mcls, name, bases, namespace, **kwargs)


class AppBackend(QObject, metaclass=_BackendMeta):
    """Central backend object registered as a QML context property."""

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
    tracklistErrorChanged = Signal()
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
    llmConfiguredChanged = Signal()
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
    videoThumbnailUrl = Property(
        str, _getter("_video_thumbnail_url"), notify=videoThumbnailUrlChanged
    )
    videoLoading = Property(bool, _getter("_video_loading"), notify=videoLoadingChanged)
    videoLoaded = Property(bool, _getter("_video_loaded"), notify=videoLoadedChanged)
    videoError = Property(str, _getter("_video_error"), notify=videoErrorChanged)
    templateError = Property(str, _getter("_template_error"), notify=templateErrorChanged)
    tracklistError = Property(
        str, _getter("_tracklist_error"), notify=tracklistErrorChanged
    )
    previewStatus = Property(str, _getter("_preview_status"), notify=previewStatusChanged)
    previewValid = Property(bool, _getter("_preview_valid"), notify=previewValidChanged)
    albumPlaceholder = Property(
        str, _getter("_album_placeholder"), notify=albumPlaceholderChanged
    )
    metadataError = Property(str, _getter("_metadata_error"), notify=metadataErrorChanged)
    outputDir = Property(str, _getter("_output_dir"), notify=outputDirChanged)
    dirError = Property(str, _getter("_dir_error"), notify=dirErrorChanged)
    busy = Property(bool, _getter("_busy"), notify=busyChanged)
    progressPercent = Property(
        float, _getter("_progress_percent"), notify=progressPercentChanged
    )
    progressStage = Property(str, _getter("_progress_stage"), notify=progressStageChanged)
    ffmpegMissing = Property(bool, _getter("_ffmpeg_missing"), notify=ffmpegMissingChanged)
    llmConfigured = Property(bool, _getter("_llm_configured"), notify=llmConfiguredChanged)
    currentTemplate = Property(str, _getter("_template"), notify=currentTemplateChanged)
    artistName = Property(str, _getter("_artist"), notify=artistNameChanged)
    albumName = Property(str, _getter("_album"), notify=albumNameChanged)
    aiAnalyzing = Property(bool, _getter("_ai_analyzing"), notify=aiAnalyzingChanged)
    aiAvailable = Property(bool, _getter("_ai_available"), notify=aiAvailableChanged)

    trackPreviewModel = Property(QObject, _getter("_track_model"), constant=True)
    statusLogModel = Property(QObject, _getter("_log_model"), constant=True)
    helpContent = Property("QVariantMap", _getter("_help_content"), constant=True)

    def __init__(self, controller: AppController | None = None, parent=None):
        """Initialize the backend.

        Args:
            controller: Shared application controller. Created if omitted.
            parent: Optional QObject parent.
        """
        super().__init__(parent)
        self._controller = controller or AppController(parent=self)

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
        self._template = self._controller.template
        self._template_error = ""
        self._tracklist_error = ""
        self._preview_status = ""
        self._preview_valid = True
        self._artist = self._controller.artist
        self._album = self._controller.album
        self._album_placeholder = "Defaults to video title"
        self._metadata_error = ""
        self._output_dir = self._controller.output_dir
        self._dir_error = ""
        self._busy = False
        self._progress_percent = 0.0
        self._progress_stage = "Ready"
        self._ffmpeg_missing = not self._controller.ffmpeg_available
        self._llm_configured = self._controller.llm_configured
        self._ai_analyzing = False
        self._ai_available = False

        self._setting_values = self._controller.read_all_settings()

        self._track_model = TrackPreviewModel(self)
        self._log_model = StatusLogModel(self)
        self._help_content = build_help_content()

        self._connect_controller()

    # ── Private helpers ─────────────────────────────────────────────

    def _emit(self, attr, value, signal):
        if getattr(self, attr) != value:
            setattr(self, attr, value)
            signal.emit()

    def _connect_controller(self):
        c = self._controller
        c.urlErrorChanged.connect(
            lambda m: self._emit("_url_error", m, self.urlErrorChanged)
        )
        c.videoLoadingStarted.connect(self._on_video_loading)
        c.videoInfoLoaded.connect(self._on_video_info_loaded)
        c.videoInfoFailed.connect(self._on_video_info_error)
        c.videoCleared.connect(self._on_video_cleared)

        c.templateChanged.connect(
            lambda t: self._emit("_template", t, self.currentTemplateChanged)
        )
        c.templateErrorChanged.connect(
            lambda m: self._emit("_template_error", m, self.templateErrorChanged)
        )
        c.tracklistErrorChanged.connect(
            lambda m: self._emit("_tracklist_error", m, self.tracklistErrorChanged)
        )
        c.previewChanged.connect(self._on_preview_changed)

        c.artistChanged.connect(
            lambda v: self._emit("_artist", v, self.artistNameChanged)
        )
        c.albumChanged.connect(lambda v: self._emit("_album", v, self.albumNameChanged))
        c.albumPlaceholderChanged.connect(
            lambda v: self._emit("_album_placeholder", v, self.albumPlaceholderChanged)
        )
        c.metadataErrorChanged.connect(
            lambda m: self._emit("_metadata_error", m, self.metadataErrorChanged)
        )
        c.outputDirChanged.connect(
            lambda v: self._emit("_output_dir", v, self.outputDirChanged)
        )
        c.dirErrorChanged.connect(
            lambda m: self._emit("_dir_error", m, self.dirErrorChanged)
        )

        c.aiAnalyzingChanged.connect(
            lambda v: self._emit("_ai_analyzing", v, self.aiAnalyzingChanged)
        )
        c.aiAvailableChanged.connect(
            lambda v: self._emit("_ai_available", v, self.aiAvailableChanged)
        )
        c.aiMessage.connect(
            lambda message, is_error: self.showMessage.emit(
                "AI Assist", message, is_error
            )
        )

        c.busyChanged.connect(self._on_busy_changed)
        c.progressChanged.connect(self._on_progress)
        c.logMessage.connect(self._log_model.append)
        c.pipelineFinished.connect(self._on_finished)
        c.pipelineFailed.connect(self._on_error)

        c.settingChanged.connect(self._on_setting_changed)
        c.ffmpegAvailableChanged.connect(
            lambda available: self._emit(
                "_ffmpeg_missing", not available, self.ffmpegMissingChanged
            )
        )
        c.llmConfiguredChanged.connect(
            lambda v: self._emit("_llm_configured", v, self.llmConfiguredChanged)
        )

    def _on_setting_changed(self, name, value):
        self._setting_values[name] = value
        getattr(self, SETTING_FIELDS_BY_NAME[name].signal_name).emit()

    # ── Slots (called from QML) ─────────────────────────────────────

    @Slot(str)
    def setUrl(self, url):
        self._controller.set_url(url)

    @Slot(str)
    def setTemplate(self, text):
        self._controller.set_template(text)

    @Slot(str)
    def setTracklistText(self, text):
        self._controller.set_tracklist_text(text)

    @Slot(str)
    def setArtist(self, text):
        self._controller.set_artist(text)

    @Slot(str)
    def setAlbum(self, text):
        self._controller.set_album(text)

    @Slot(str)
    def setOutputDir(self, path):
        self._controller.set_output_dir(path)

    @Slot()
    def analyzeTracklistWithAi(self):
        self._controller.analyze_tracklist_with_ai()

    @Slot()
    def startPipeline(self):
        self._controller.start_pipeline()

    @Slot()
    def cancelPipeline(self):
        self._controller.cancel_pipeline()

    # ── Video info ──────────────────────────────────────────────────

    def _on_video_loading(self):
        self._emit("_video_title", "Loading video info...", self.videoTitleChanged)
        self._emit("_video_channel", "", self.videoChannelChanged)
        self._emit("_video_duration", "", self.videoDurationChanged)
        self._emit("_video_views", "", self.videoViewsChanged)
        self._emit("_video_date", "", self.videoDateChanged)
        self._emit("_video_loading", True, self.videoLoadingChanged)
        self._emit("_video_loaded", False, self.videoLoadedChanged)
        self._emit("_video_error", "", self.videoErrorChanged)

    def _on_video_info_loaded(self, info):
        title = info.title
        if len(title) > MAX_TITLE_LENGTH:
            title = title[: MAX_TITLE_LENGTH - 3] + "..."
        self._emit("_video_title", title, self.videoTitleChanged)
        self._emit("_video_channel", info.channel, self.videoChannelChanged)
        self._emit(
            "_video_duration",
            f"Duration: {info.duration_string}",
            self.videoDurationChanged,
        )
        self._emit("_video_views", info.formatted_views, self.videoViewsChanged)
        date_str = f"Uploaded: {info.formatted_date}" if info.formatted_date else ""
        self._emit("_video_date", date_str, self.videoDateChanged)
        self._emit(
            "_video_thumbnail_url", info.thumbnail_url, self.videoThumbnailUrlChanged
        )
        self._emit("_video_loading", False, self.videoLoadingChanged)
        self._emit("_video_loaded", True, self.videoLoadedChanged)
        self._emit("_video_error", "", self.videoErrorChanged)

    def _on_video_info_error(self, message):
        self._emit("_video_error", message, self.videoErrorChanged)
        self._emit("_video_loading", False, self.videoLoadingChanged)
        self._emit("_video_loaded", False, self.videoLoadedChanged)

    def _on_video_cleared(self):
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

    # ── Preview ─────────────────────────────────────────────────────

    def _on_preview_changed(self, preview):
        self._track_model.update(preview.tracks)

        if preview.total_lines == 0:
            self._emit("_preview_status", "", self.previewStatusChanged)
            self._emit("_preview_valid", True, self.previewValidChanged)
        elif preview.is_valid:
            self._emit(
                "_preview_status",
                f"{preview.total_lines} tracks",
                self.previewStatusChanged,
            )
            self._emit("_preview_valid", True, self.previewValidChanged)
        else:
            self._emit(
                "_preview_status",
                f"{preview.error_count} error(s)",
                self.previewStatusChanged,
            )
            self._emit("_preview_valid", False, self.previewValidChanged)

    # ── Pipeline ────────────────────────────────────────────────────

    def _on_busy_changed(self, busy):
        if busy:
            self._log_model.clear_all()
            self._emit("_progress_percent", 0.0, self.progressPercentChanged)
        self._emit("_busy", busy, self.busyChanged)

    def _on_progress(self, stage, percent, message):
        if stage == "starting":
            label = "Starting..."
        else:
            label = f"{stage_label(stage)}: {int(percent)}%"
        self._emit("_progress_stage", label, self.progressStageChanged)
        self._emit("_progress_percent", percent, self.progressPercentChanged)

    def _on_finished(self, output_files):
        self._emit("_progress_percent", 100.0, self.progressPercentChanged)
        self._emit("_progress_stage", "Complete!", self.progressStageChanged)
        self.showMessage.emit(
            "Complete",
            f"Successfully split audio into {len(output_files)} track(s)!",
            False,
        )

    def _on_error(self, message):
        self._emit("_progress_stage", "Error", self.progressStageChanged)
        self.showMessage.emit("Error", message, True)
