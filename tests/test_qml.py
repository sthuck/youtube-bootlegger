"""End-to-end interaction tests for the QML UI, driven headlessly with QTest."""

import json
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QModelIndex, QObject, QPointF, Qt
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.app_qml import create_qml_engine
from src.youtube_bootlegger.core.exceptions import DownloadError, ValidationError
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.core.video_info import VideoInfo
from src.youtube_bootlegger.llm import DEFAULT_OPENAI_MODEL, LlmError
from src.youtube_bootlegger.llm.client import OPENAI_CHAT_URL
from src.youtube_bootlegger.qml_backend import AppBackend
from src.youtube_bootlegger.qml_backend import backend as backend_module
from src.youtube_bootlegger.workers import pipeline_worker as pipeline_worker_module
from src.youtube_bootlegger.workers import tracklist_ai_worker as ai_worker_module
from src.youtube_bootlegger.workers import video_info_worker as video_worker_module

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class DictBackend:
    """In-memory QSettings stand-in for isolated test runs."""

    def __init__(self):
        self.data = {}
        self.synced = 0

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def sync(self):
        self.synced += 1


def make_video(**overrides) -> VideoInfo:
    fields = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Live at the Venue",
        "channel": "Band Channel",
        "duration": 3600,
        "duration_string": "1:00:00",
        "thumbnail_url": "",
        "view_count": 1_500,
        "upload_date": "20240131",
    }
    fields.update(overrides)
    return VideoInfo(**fields)


class FakePipeline:
    """Stands in for DownloadSplitPipeline; behaviour configured per test."""

    instances: list["FakePipeline"] = []
    outcome: object = None
    gate: threading.Event | None = None

    def __init__(self, progress_callback=None, log_callback=None, settings=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.settings = settings
        self.cancelled = False
        self.job = None
        FakePipeline.instances.append(self)

    def execute(self, job):
        self.job = job
        if self.log_callback:
            self.log_callback("Starting fake pipeline")
        if self.progress_callback:
            self.progress_callback("download", 50.0, "Downloading 50%")
        if FakePipeline.gate is not None:
            FakePipeline.gate.wait(timeout=5)
        if self.cancelled:
            return []
        if isinstance(FakePipeline.outcome, Exception):
            raise FakePipeline.outcome
        return FakePipeline.outcome

    def cancel(self):
        self.cancelled = True


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def settings():
    return AppSettings(DictBackend())


@pytest.fixture
def fake_pipeline(monkeypatch):
    FakePipeline.instances = []
    FakePipeline.outcome = [Path("/out/01 - Intro.mp3"), Path("/out/02 - Song.mp3")]
    FakePipeline.gate = None
    monkeypatch.setattr(pipeline_worker_module, "DownloadSplitPipeline", FakePipeline)
    return FakePipeline


@pytest.fixture
def fake_video(monkeypatch):
    calls = []

    def fetch(url, settings=None):
        calls.append((url, settings))
        return make_video()

    monkeypatch.setattr(video_worker_module, "fetch_video_info", fetch)
    monkeypatch.setattr(backend_module, "is_ffmpeg_available", lambda cmd: True)
    return calls


@pytest.fixture
def qml_harness(qapp, settings, fake_video):
    """Create and tear down the QML ApplicationWindow + AppBackend."""
    backend = AppBackend(settings=settings)
    backend.URL_DEBOUNCE_MS = 10

    warnings = []
    engine = create_qml_engine(backend)
    engine.warnings.connect(lambda w_list: warnings.extend(w_list))

    roots = engine.rootObjects()
    assert roots, f"QML failed to load: {warnings}"
    window: QQuickWindow = roots[0]
    QTest.qWaitForWindowExposed(window)
    qapp.processEvents()

    yield window, backend, settings, warnings

    backend._thread_pool.waitForDone(2000)
    window.close()
    qapp.processEvents()
    del window
    del roots
    del engine
    qapp.processEvents()


def _walk_visual_items(item: QQuickItem, object_name: str) -> QQuickItem | None:
    if item.objectName() == object_name:
        return item
    for child in item.childItems():
        found = _walk_visual_items(child, object_name)
        if found is not None:
            return found
    return None


def find_item(window: QQuickWindow, object_name: str) -> QObject:
    """Look up a QML object by objectName across both QObject and visual item trees."""
    item = window.findChild(QObject, object_name)
    if item is not None:
        return item
    if isinstance(window, QQuickWindow) and window.contentItem() is not None:
        item = _walk_visual_items(window.contentItem(), object_name)
    assert item is not None, f"QML item {object_name!r} not found"
    return item


def click_item(window: QQuickWindow, object_name: str) -> None:
    """Click the center of a visible QQuickItem using QTest.mouseClick.

    If the item is inside a Flickable/ScrollView and currently scrolled outside
    the Flickable's viewport, scrolls the enclosing Flickable first.
    """
    item = find_item(window, object_name)
    assert isinstance(item, QQuickItem), f"{object_name!r} is not a QQuickItem"
    local_center = QPointF(item.width() / 2, item.height() / 2)
    parent = item.parentItem()
    while parent is not None:
        if parent.metaObject().indexOfProperty("contentY") != -1:
            in_flick = item.mapToItem(parent, local_center)
            if in_flick.y() >= parent.height() or in_flick.y() < 0:
                current_y = parent.property("contentY")
                delta = in_flick.y() - (parent.height() / 2)
                parent.setProperty("contentY", max(0.0, current_y + delta))
                QApplication.processEvents()
            break
        parent = parent.parentItem()
    center = item.mapToScene(local_center)
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        center.toPoint(),
    )
    QApplication.processEvents()


def set_text(window: QQuickWindow, object_name: str, value: str) -> None:
    """Set the text property on a QML TextInput / TextArea and process events."""
    item = find_item(window, object_name)
    item.setProperty("text", value)
    QApplication.processEvents()


def prop(window: QQuickWindow, object_name: str, property_name: str = "text"):
    """Read a QML property from a named item."""
    return find_item(window, object_name).property(property_name)


def wait_until(condition, timeout_ms: int = 2000, step_ms: int = 15) -> None:
    """Spin the Qt event loop until condition() is truthy or timeout expires."""
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
        QTest.qWait(step_ms)
    QApplication.processEvents()
    assert condition(), "Timed out waiting for condition"


def load_video(window: QQuickWindow, backend: AppBackend, url: str = VALID_URL) -> None:
    set_text(window, "urlField", url)
    wait_until(lambda: backend.videoLoaded)


def fill_form(
    window: QQuickWindow,
    backend: AppBackend,
    artist: str = "The Band",
    output_dir: str = "/tmp",
) -> None:
    load_video(window, backend)
    set_text(window, "tracklistArea", "Intro - 0:00\nSong - 4:30")
    set_text(window, "artistField", artist)
    set_text(window, "dirField", output_dir)


class TestStartup:
    def test_loads_without_qml_warnings(self, qml_harness):
        window, backend, _settings, warnings = qml_harness
        assert warnings == []
        assert window.title() == "YouTube Bootlegger"
        assert prop(window, "msgOverlay", "visible") is False

    def test_ffmpeg_missing_shows_warning_modal_on_startup(self, qapp, settings, monkeypatch):
        monkeypatch.setattr(backend_module, "is_ffmpeg_available", lambda cmd: False)
        backend = AppBackend(settings=settings)
        engine = create_qml_engine(backend)
        window = engine.rootObjects()[0]
        QTest.qWaitForWindowExposed(window)
        qapp.processEvents()

        try:
            assert backend.ffmpegMissing is True
            assert prop(window, "msgOverlay", "visible") is True
            assert prop(window, "msgTitle") == "FFmpeg Not Found"
            assert "FFmpeg is not installed" in prop(window, "msgBody")

            click_item(window, "msgCloseButton")
            assert prop(window, "msgOverlay", "visible") is False
        finally:
            window.close()
            del window
            del engine
            qapp.processEvents()


class TestVideoInfo:
    def test_valid_url_fetches_and_updates_qml_preview(self, qml_harness, fake_video):
        window, backend, settings, _warnings = qml_harness
        load_video(window, backend)

        assert fake_video == [(VALID_URL, settings)]
        assert prop(window, "videoTitleText") == "Live at the Venue"
        assert prop(window, "videoChannelText") == "Band Channel"
        assert prop(window, "videoDurationText") == "1:00:00"
        assert prop(window, "albumPlaceholderText") == "Live at the Venue"

    def test_invalid_url_does_not_fetch(self, qml_harness, fake_video):
        window, backend, _settings, _warnings = qml_harness
        set_text(window, "urlField", "https://example.com/not-youtube")
        QTest.qWait(50)

        assert fake_video == []
        assert backend.videoLoaded is False
        assert prop(window, "videoTitleText") == ""

    def test_fetch_error_is_displayed_in_qml(self, qml_harness, monkeypatch):
        window, backend, _settings, _warnings = qml_harness

        def failing_fetch(url, settings=None):
            raise ValidationError("Video unavailable")

        monkeypatch.setattr(video_worker_module, "fetch_video_info", failing_fetch)
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: "unavailable" in prop(window, "urlErrorText"))

        assert prop(window, "urlErrorText", "visible") is True
        assert "Video unavailable" in prop(window, "urlErrorText")
        assert backend.videoLoaded is False


class TestUrlEditing:
    def test_editing_url_clears_previous_video_immediately(
        self, qml_harness, fake_pipeline
    ):
        window, backend, _settings, _warnings = qml_harness
        fill_form(window, backend)
        assert prop(window, "albumPlaceholderText") == "Live at the Venue"

        backend.URL_DEBOUNCE_MS = 10_000
        set_text(window, "urlField", "https://youtu.be/different")

        assert backend.videoLoaded is False
        assert prop(window, "videoTitleText") == ""
        assert prop(window, "albumPlaceholderText") == "Defaults to video title"

        click_item(window, "startButton")
        assert fake_pipeline.instances == []
        assert "wait" in prop(window, "urlErrorText").lower()

    def test_returning_to_same_url_refetches(self, qml_harness, fake_video):
        window, backend, settings, _warnings = qml_harness
        load_video(window, backend)
        assert len(fake_video) == 1

        set_text(window, "urlField", "not a url")
        assert backend.videoLoaded is False

        load_video(window, backend)
        assert fake_video == [(VALID_URL, settings), (VALID_URL, settings)]

    def test_stale_video_result_is_ignored(self, qml_harness):
        _window, backend, _settings, _warnings = qml_harness
        backend._last_fetched_url = "https://youtu.be/new"
        backend._on_video_info_loaded(make_video(title="Old"), url=VALID_URL)
        assert backend.videoLoaded is False
        assert backend.videoTitle == ""


class TestPreview:
    def test_tracklist_preview_populates_listview_model(self, qml_harness):
        window, backend, _settings, _warnings = qml_harness
        set_text(window, "tracklistArea", "Opening - 0:00\nEncore - 4:32")

        preview_list = find_item(window, "previewList")
        assert preview_list.property("count") == 2
        assert prop(window, "previewStatusText") == "2 tracks"
        assert backend.previewValid is True

        model = backend.trackPreviewModel
        idx0 = model.index(0, 0)
        assert model.data(idx0, model.NameRole) == "Opening"
        assert model.data(idx0, model.TimestampRole) == "0:00"
        assert model.data(idx0, model.IsValidRole) is True

    def test_bad_line_marks_preview_invalid(self, qml_harness):
        window, backend, _settings, _warnings = qml_harness
        set_text(window, "tracklistArea", "Opening - 0:00\nbad line without time")

        assert prop(window, "previewStatusText") == "1 error(s)"
        assert backend.previewValid is False

        model = backend.trackPreviewModel
        idx1 = model.index(1, 0)
        assert model.data(idx1, model.IsValidRole) is False
        assert model.data(idx1, model.ErrorRole) != ""

    def test_invalid_template_shows_error_in_qml(self, qml_harness):
        window, _backend, _settings, _warnings = qml_harness
        set_text(window, "templateField", "%songname%")

        assert prop(window, "templateErrorText", "visible") is True
        assert prop(window, "templateErrorText") != ""


class TestPipeline:
    def test_start_without_url_shows_error(self, qml_harness, fake_pipeline):
        window, _backend, _settings, _warnings = qml_harness
        click_item(window, "startButton")

        assert "Please enter a YouTube URL" in prop(window, "urlErrorText")
        assert prop(window, "urlErrorText", "visible") is True
        assert fake_pipeline.instances == []

    def test_start_without_artist_or_album_shows_metadata_error(
        self, qml_harness, fake_pipeline
    ):
        window, backend, _settings, _warnings = qml_harness
        fill_form(window, backend, artist="")
        click_item(window, "startButton")

        assert "artist name or album" in prop(window, "metadataErrorText")
        assert prop(window, "metadataErrorText", "visible") is True
        assert fake_pipeline.instances == []

    def test_start_with_empty_output_dir_shows_dir_error(
        self, qml_harness, fake_pipeline
    ):
        window, backend, _settings, _warnings = qml_harness
        fill_form(window, backend, output_dir="")
        click_item(window, "startButton")

        assert "Please select an output directory" in prop(window, "dirErrorText")
        assert prop(window, "dirErrorText", "visible") is True
        assert fake_pipeline.instances == []

    def test_successful_pipeline_run_updates_progress_and_shows_completion_modal(
        self, qml_harness, fake_pipeline, tmp_path
    ):
        window, backend, settings, _warnings = qml_harness
        fill_form(window, backend, output_dir=str(tmp_path))

        click_item(window, "startButton")
        wait_until(lambda: not backend.busy and len(fake_pipeline.instances) == 1)

        instance = fake_pipeline.instances[0]
        assert instance.settings is settings
        assert instance.job.url == VALID_URL
        assert instance.job.artist == "The Band"
        assert instance.job.album == "Live at the Venue"
        assert [t.name for t in instance.job.tracks] == ["Intro", "Song"]

        assert prop(window, "progressStageText") == "Complete!"
        assert prop(window, "progressPercentText") == "100%"
        assert find_item(window, "logList").property("count") >= 3
        assert prop(window, "msgOverlay", "visible") is True
        assert prop(window, "msgTitle") == "Complete"
        assert "2 track(s)" in prop(window, "msgBody")

    def test_pipeline_error_is_shown_in_modal_and_log(
        self, qml_harness, fake_pipeline, tmp_path
    ):
        fake_pipeline.outcome = DownloadError("network down")
        window, backend, _settings, _warnings = qml_harness
        fill_form(window, backend, output_dir=str(tmp_path))

        click_item(window, "startButton")
        wait_until(lambda: prop(window, "progressStageText") == "Error")

        assert backend.busy is False
        assert prop(window, "msgOverlay", "visible") is True
        assert prop(window, "msgTitle") == "Error"
        assert "network down" in prop(window, "msgBody")

    def test_cancel_running_job(self, qml_harness, fake_pipeline, tmp_path):
        fake_pipeline.gate = threading.Event()
        window, backend, _settings, _warnings = qml_harness
        fill_form(window, backend, output_dir=str(tmp_path))

        click_item(window, "startButton")
        wait_until(lambda: "Downloading" in prop(window, "progressStageText"))

        assert backend.busy is True
        assert prop(window, "startButton", "enabled") is False
        assert prop(window, "cancelButton", "enabled") is True

        click_item(window, "cancelButton")
        assert fake_pipeline.instances[0].cancelled is True

        fake_pipeline.gate.set()
        wait_until(lambda: not backend.busy)
        assert prop(window, "progressStageText") == "Cancelled"


class TestAiAssist:
    def test_ai_button_disabled_until_video_and_tracklist_ready(self, qml_harness):
        window, backend, _settings, _warnings = qml_harness
        assert prop(window, "aiButtonRect", "enabled") is False

        set_text(window, "tracklistArea", "Intro - 0:00")
        assert prop(window, "aiButtonRect", "enabled") is False

        load_video(window, backend)
        assert prop(window, "aiButtonRect", "enabled") is True

    def test_api_provider_populates_template_artist_and_album(
        self, qml_harness, monkeypatch
    ):
        window, backend, _settings, _warnings = qml_harness
        backend.setLlmProvider(LlmProvider.OPENAI.value)
        backend.setOpenaiApiKey("sk-test-key")

        captured = {}

        def fake_post(url, headers, body):
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["body"] = body
            content = json.dumps(
                {
                    "template": "%mm%:%ss% %songname%",
                    "artist_name": "AI Band",
                    "album_name": "AI Album",
                }
            )
            return {"choices": [{"message": {"content": content}}]}

        monkeypatch.setattr(ai_worker_module, "post_json", fake_post)

        load_video(window, backend)
        # User manually edits fields first; AI Assist must still overwrite them in QML.
        set_text(window, "templateField", "%songname% - %mm%:%ss%")
        set_text(window, "artistField", "Manual Draft")
        set_text(window, "tracklistArea", "0:00 Intro\n4:30 Song")
        assert prop(window, "aiButtonRect", "enabled") is True

        click_item(window, "aiButton")
        wait_until(lambda: prop(window, "artistField") == "AI Band")

        assert captured["url"] == OPENAI_CHAT_URL
        assert captured["headers"]["Authorization"] == "Bearer sk-test-key"
        assert captured["body"]["model"] == DEFAULT_OPENAI_MODEL
        assert prop(window, "templateField") == "%mm%:%ss% %songname%"
        assert prop(window, "albumField") == "AI Album"
        assert backend.aiAnalyzing is False
        assert prop(window, "previewStatusText") == "2 tracks"

    def test_api_provider_error_shows_message_overlay(
        self, qml_harness, monkeypatch
    ):
        window, backend, _settings, _warnings = qml_harness
        backend.setLlmProvider(LlmProvider.OPENAI.value)
        backend.setOpenaiApiKey("sk-bad-key")

        def failing_post(url, headers, body):
            raise LlmError("LLM request failed: HTTP 401: invalid api key")

        monkeypatch.setattr(ai_worker_module, "post_json", failing_post)

        load_video(window, backend)
        set_text(window, "tracklistArea", "0:00 Intro\n4:30 Song")
        click_item(window, "aiButton")

        wait_until(lambda: prop(window, "msgOverlay", "visible") is True)
        assert prop(window, "msgTitle") == "AI Assist"
        assert "invalid api key" in prop(window, "msgBody")
        assert backend.aiAnalyzing is False

    def test_chatgpt_lite_launches_and_shows_message_overlay(
        self, qml_harness, monkeypatch
    ):
        window, backend, _settings, _warnings = qml_harness
        called = []

        def fake_lite(title, text):
            called.append((title, text))
            return True, "Prompt copied to clipboard and opened ChatGPT."

        monkeypatch.setattr(backend_module, "launch_chatgpt_lite_assist", fake_lite)

        load_video(window, backend)
        set_text(window, "tracklistArea", "Intro - 0:00")
        click_item(window, "aiButton")

        assert called == [("Live at the Venue", "Intro - 0:00")]
        assert prop(window, "msgOverlay", "visible") is True
        assert prop(window, "msgTitle") == "AI Assist"
        assert "Prompt copied" in prop(window, "msgBody")


class TestPanelsAndDialogs:
    def test_help_panel_opens_and_closes(self, qml_harness):
        window, _backend, _settings, _warnings = qml_harness
        help_panel = find_item(window, "helpPanel")
        assert help_panel.property("open") is False

        help_action = find_item(window, "helpMenuAction")
        help_action.trigger(None)
        QApplication.processEvents()

        assert help_panel.property("open") is True
        assert help_panel.property("visible") is True
        assert "YouTube Bootlegger" in prop(window, "helpTitleText")

        click_item(window, "helpCloseButton")
        assert help_panel.property("open") is False
        assert help_panel.property("visible") is False

    def test_settings_panel_edits_persist_on_done(self, qml_harness):
        window, backend, settings, _warnings = qml_harness
        settings_panel = find_item(window, "settingsPanel")
        assert settings_panel.property("open") is False

        settings_action = find_item(window, "settingsMenuAction")
        settings_action.trigger(None)
        QApplication.processEvents()
        assert settings_panel.property("open") is True

        click_item(window, "externalYtdlpToggle")
        assert backend.useExternalYtdlp is True
        assert prop(window, "ytdlpPathSection", "enabled") is True

        click_item(window, "provider_anthropic")
        assert backend.llmProvider == "anthropic"
        assert prop(window, "anthropicSection", "visible") is True
        assert prop(window, "openaiSection", "visible") is False

        set_text(window, "ytdlpPathField", "/opt/yt-dlp")
        set_text(window, "ffmpegPathField", "/opt/ffmpeg")
        set_text(window, "anthropicKeyField", "sk-ant-123")
        set_text(window, "anthropicModelField", "claude-custom")

        click_item(window, "settingsDoneButton")

        assert settings_panel.property("open") is False
        assert settings.use_external_ytdlp is True
        assert settings.ytdlp_path == "/opt/yt-dlp"
        assert settings.ffmpeg_path == "/opt/ffmpeg"
        assert settings.llm_provider == LlmProvider.ANTHROPIC
        assert settings.anthropic_api_key == "sk-ant-123"
        assert settings.anthropic_model == "claude-custom"
        assert backend.llmConfigured is True
