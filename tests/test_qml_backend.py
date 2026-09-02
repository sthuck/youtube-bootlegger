"""Unit tests for the QML backend adapter and its generated settings API."""

import pytest

from src.youtube_bootlegger.controller import SETTING_FIELDS, AppController
from src.youtube_bootlegger.qml_backend import AppBackend

TRACKLIST = "Opening Number - 0:00\nSecond Song - 4:32\nThird Song - 8:15"

# Properties Main.qml and its panels bind to. Losing one breaks the UI
# silently, so pin the contract here.
VIEW_PROPERTIES = [
    "urlError",
    "videoTitle",
    "videoChannel",
    "videoDuration",
    "videoViews",
    "videoDate",
    "videoThumbnailUrl",
    "videoLoading",
    "videoLoaded",
    "videoError",
    "templateError",
    "previewStatus",
    "previewValid",
    "albumPlaceholder",
    "metadataError",
    "outputDir",
    "dirError",
    "busy",
    "progressPercent",
    "progressStage",
    "ffmpegMissing",
    "currentTemplate",
    "artistName",
    "albumName",
    "aiAnalyzing",
    "aiAvailable",
    "trackPreviewModel",
    "statusLogModel",
    "helpContent",
]

VIEW_SLOTS = [
    "setUrl",
    "setTemplate",
    "setTracklistText",
    "setArtist",
    "setAlbum",
    "setOutputDir",
    "analyzeTracklistWithAi",
    "startPipeline",
    "cancelPipeline",
]


@pytest.fixture
def controller(qapp, settings):
    return AppController(settings=settings)


@pytest.fixture
def backend(controller):
    return AppBackend(controller)


def qt_property_names(obj):
    """Return the property names registered in the Qt meta-object."""
    meta = obj.metaObject()
    return {meta.property(i).name() for i in range(meta.propertyCount())}


class TestGeneratedSettingsApi:
    """Each declared setting yields a real property, signal and slot."""

    @pytest.mark.parametrize("field", SETTING_FIELDS, ids=lambda f: f.name)
    def test_property_is_registered_with_qt(self, backend, field):
        assert field.qml_name in qt_property_names(backend)

    @pytest.mark.parametrize("field", SETTING_FIELDS, ids=lambda f: f.name)
    def test_signal_and_slot_exist(self, backend, field):
        assert hasattr(backend, field.signal_name)
        assert callable(getattr(backend, field.slot_name))

    @pytest.mark.parametrize("field", SETTING_FIELDS, ids=lambda f: f.name)
    def test_initial_value_matches_the_controller(self, backend, controller, field):
        assert getattr(backend, field.qml_name) == controller.read_setting(field.name)

    def test_string_setter_round_trips_through_the_controller(
        self, backend, controller
    ):
        backend.setOpenaiApiKey("  sk-test  ")
        assert backend.openaiApiKey == "sk-test"
        assert controller.read_setting("openai_api_key") == "sk-test"

    def test_bool_setter_round_trips(self, backend, controller):
        backend.setUseExternalYtdlp(True)
        assert backend.useExternalYtdlp is True
        assert controller.read_setting("use_external_ytdlp") is True

    def test_setter_emits_the_notify_signal(self, backend):
        fired = []
        backend.openaiModelChanged.connect(lambda: fired.append(True))
        backend.setOpenaiModel("gpt-4o-mini")
        assert fired == [True]

    def test_provider_setter_normalizes_legacy_values(self, backend):
        backend.setLlmProvider("none")
        assert backend.llmProvider == "chatgpt_lite"

    def test_controller_side_change_updates_the_property(self, backend, controller):
        controller.update_setting("vertex_model", "gemini-2.0-flash")
        assert backend.vertexModel == "gemini-2.0-flash"


class TestViewApi:
    """The hand-written half of the QML contract stays intact."""

    @pytest.mark.parametrize("name", VIEW_PROPERTIES)
    def test_property_is_registered_with_qt(self, backend, name):
        assert name in qt_property_names(backend)

    @pytest.mark.parametrize("name", VIEW_SLOTS)
    def test_slot_exists(self, backend, name):
        assert callable(getattr(backend, name))


class TestStateMapping:
    """Controller events land in the properties QML binds to."""

    def test_video_info_populates_the_preview(self, backend, controller, video_info):
        controller._on_video_info_loaded(video_info)
        assert backend.videoTitle == video_info.title
        assert backend.videoChannel == video_info.channel
        assert backend.videoDuration == "Duration: 1:00:00"
        assert backend.videoLoaded is True
        assert backend.albumPlaceholder == video_info.title

    def test_long_titles_are_truncated(self, backend, controller, video_info):
        long_title = "A" * 120
        controller._on_video_info_loaded(
            type(video_info)(**{**video_info.__dict__, "title": long_title})
        )
        assert len(backend.videoTitle) == 80
        assert backend.videoTitle.endswith("...")

    def test_video_error_clears_loaded_state(self, backend, controller, video_info):
        controller._on_video_info_loaded(video_info)
        controller._on_video_info_error("This video is private")
        assert backend.videoLoaded is False
        assert backend.videoError == "This video is private"

    def test_tracklist_drives_the_preview_model(self, backend):
        backend.setTracklistText(TRACKLIST)
        assert backend.previewStatus == "3 tracks"
        assert backend.previewValid is True
        assert backend.trackPreviewModel.rowCount() == 3

    def test_preview_reports_errors(self, backend):
        backend.setTracklistText("nonsense")
        assert backend.previewValid is False
        assert backend.previewStatus == "1 error(s)"

    def test_template_error_surfaces(self, backend):
        backend.setTemplate("no placeholders")
        assert backend.templateError != ""
        backend.setTemplate("%songname% - %mm%:%ss%")
        assert backend.templateError == ""

    def test_start_without_input_reports_instead_of_silently_failing(self, backend):
        backend.startPipeline()
        assert backend.urlError == "Please enter a YouTube URL"

    def test_progress_maps_to_a_stage_label(self, backend, controller):
        controller.progressChanged.emit("download", 42.0, "Downloading...")
        assert backend.progressStage == "Downloading: 42%"
        assert backend.progressPercent == 42.0

    def test_starting_stage_has_its_own_label(self, backend, controller):
        controller.progressChanged.emit("starting", 0.0, "Starting...")
        assert backend.progressStage == "Starting..."

    def test_busy_resets_the_log(self, backend, controller):
        controller.logMessage.emit("stale", "info")
        assert backend.statusLogModel.rowCount() == 1
        controller._set_busy(True)
        assert backend.statusLogModel.rowCount() == 0
        assert backend.busy is True

    def test_completion_shows_a_message(self, backend, controller):
        messages = []
        backend.showMessage.connect(
            lambda title, message, is_error: messages.append(
                (title, message, is_error)
            )
        )
        controller._on_pipeline_finished(["/tmp/01.mp3"])
        assert backend.progressStage == "Complete!"
        assert messages == [
            ("Complete", "Successfully split audio into 1 track(s)!", False)
        ]

    def test_failure_shows_an_error_message(self, backend, controller):
        messages = []
        backend.showMessage.connect(
            lambda title, message, is_error: messages.append(
                (title, message, is_error)
            )
        )
        controller._on_pipeline_error("boom")
        assert backend.progressStage == "Error"
        assert messages == [("Error", "boom", True)]

    def test_ai_message_is_forwarded(self, backend, controller):
        messages = []
        backend.showMessage.connect(
            lambda title, message, is_error: messages.append(
                (title, message, is_error)
            )
        )
        controller.aiMessage.emit("no credentials", True)
        assert messages == [("AI Assist", "no credentials", True)]
