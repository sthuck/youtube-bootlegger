"""End-to-end interaction tests for the QML UI, driven headlessly with QTest."""

import inspect
import json
import threading
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.core.exceptions import DownloadError, ValidationError
from src.youtube_bootlegger.core.pipeline import DownloadSplitPipeline
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.llm import DEFAULT_OPENAI_MODEL, LlmError
from src.youtube_bootlegger.llm.client import OPENAI_CHAT_URL
from src.youtube_bootlegger.qml_backend import AppBackend
from src.youtube_bootlegger.qml_backend import backend as backend_module
from src.youtube_bootlegger.workers import TracklistAiWorker
from src.youtube_bootlegger.workers import video_info_worker as video_worker_module
from tests.qml_support import (
    OTHER_URL,
    VALID_URL,
    FakePipeline,
    click_item,
    fill_form,
    find_item,
    load_video,
    open_window,
    press_key,
    prop,
    set_text,
    type_text,
    wait_for_workers,
    wait_until,
)


def use_ai_http(monkeypatch, http_post) -> None:
    """Make the backend build TracklistAiWorkers that post through http_post."""
    monkeypatch.setattr(
        backend_module,
        "TracklistAiWorker",
        partial(TracklistAiWorker, http_post=http_post),
    )


def open_settings(window):
    find_item(window, "settingsMenuAction").trigger(None)
    QApplication.processEvents()
    return find_item(window, "settingsPanel")


class TestStartup:
    def test_loads_without_qml_warnings(self, qml_harness):
        window, _backend, _settings = qml_harness
        assert window.title() == "YouTube Bootlegger"
        assert prop(window, "msgOverlay", "visible") is False

    def test_ffmpeg_missing_shows_warning_modal_on_startup(
        self, qapp, app_settings, monkeypatch
    ):
        monkeypatch.setattr(backend_module, "is_ffmpeg_available", lambda cmd: False)
        backend = AppBackend(settings=app_settings)
        with open_window(backend) as (window, warnings):
            assert backend.ffmpegMissing is True
            assert prop(window, "msgOverlay", "visible") is True
            assert prop(window, "msgTitle") == "FFmpeg Not Found"
            assert "FFmpeg is not installed" in prop(window, "msgBody")

            click_item(window, "msgCloseButton")
            assert prop(window, "msgOverlay", "visible") is False
            assert warnings == []


class TestVideoInfo:
    def test_valid_url_fetches_and_updates_qml_preview(self, qml_harness, fake_video):
        window, backend, settings = qml_harness
        load_video(window, backend)

        assert fake_video == [(VALID_URL, settings)]
        assert prop(window, "videoTitleText") == "Live at the Venue"
        assert prop(window, "videoChannelText") == "Band Channel"
        assert prop(window, "videoDurationText") == "1:00:00"
        assert prop(window, "albumPlaceholderText") == "Live at the Venue"

    def test_typed_url_fetches_once_after_debounce(self, qml_harness, fake_video):
        window, backend, _settings = qml_harness
        type_text(window, "urlField", VALID_URL)
        wait_until(lambda: backend.videoLoaded)

        assert [url for url, _ in fake_video] == [VALID_URL]

    def test_invalid_url_does_not_fetch(self, qml_harness, fake_video):
        window, backend, _settings = qml_harness
        set_text(window, "urlField", "https://example.com/not-youtube")
        wait_for_workers(backend)

        assert fake_video == []
        assert backend.videoLoaded is False
        assert prop(window, "videoTitleText") == ""

    def test_fetch_error_is_displayed_in_qml(self, qml_harness, monkeypatch):
        window, backend, _settings = qml_harness

        def failing_fetch(url, settings=None, comment_limit=0):
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
        window, backend, _settings = qml_harness
        fill_form(window, backend)
        assert prop(window, "albumPlaceholderText") == "Live at the Venue"

        backend.URL_DEBOUNCE_MS = 10_000
        set_text(window, "urlField", OTHER_URL)

        assert backend.videoLoaded is False
        assert prop(window, "videoTitleText") == ""
        assert prop(window, "albumPlaceholderText") == AppBackend.DEFAULT_ALBUM_PLACEHOLDER

        click_item(window, "startButton")
        assert fake_pipeline.instances == []
        assert "wait" in prop(window, "urlErrorText").lower()

    def test_returning_to_same_url_refetches(self, qml_harness, fake_video):
        window, backend, settings = qml_harness
        load_video(window, backend)
        assert len(fake_video) == 1

        set_text(window, "urlField", "not a url")
        assert backend.videoLoaded is False

        load_video(window, backend)
        assert fake_video == [(VALID_URL, settings), (VALID_URL, settings)]


class TestOutOfOrderVideoResults:
    """Slow responses for an earlier URL must never override the current one."""

    def test_late_result_for_previous_url_is_ignored(self, qml_harness, gated_fetch):
        window, backend, _settings = qml_harness
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: len(gated_fetch.calls) == 1)
        set_text(window, "urlField", OTHER_URL)
        wait_until(lambda: len(gated_fetch.calls) == 2)

        gated_fetch.calls[1].succeed("Current Video")
        wait_until(lambda: backend.videoLoaded)
        gated_fetch.calls[0].succeed("Stale Video")
        wait_for_workers(backend)

        assert prop(window, "videoTitleText") == "Current Video"
        assert prop(window, "albumPlaceholderText") == "Current Video"

    def test_late_error_from_earlier_fetch_of_same_url_is_ignored(
        self, qml_harness, gated_fetch
    ):
        window, backend, _settings = qml_harness
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: len(gated_fetch.calls) == 1)
        set_text(window, "urlField", "not a url")
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: len(gated_fetch.calls) == 2)

        gated_fetch.calls[0].fail("Transient network error")
        wait_until(lambda: backend._thread_pool.activeThreadCount() == 1)
        QApplication.processEvents()
        gated_fetch.calls[1].succeed("Fresh Video")
        wait_until(lambda: backend.videoLoaded)

        assert prop(window, "videoTitleText") == "Fresh Video"
        assert prop(window, "urlErrorText") == ""

    def test_late_error_for_previous_url_is_ignored(self, qml_harness, gated_fetch):
        window, backend, _settings = qml_harness
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: len(gated_fetch.calls) == 1)
        set_text(window, "urlField", OTHER_URL)
        wait_until(lambda: len(gated_fetch.calls) == 2)

        gated_fetch.calls[1].succeed("Current Video")
        wait_until(lambda: backend.videoLoaded)
        gated_fetch.calls[0].fail("Old URL failed")
        wait_for_workers(backend)

        assert backend.videoLoaded is True
        assert prop(window, "urlErrorText") == ""


class TestMetadataFields:
    def test_typed_artist_and_album_keep_spaces(self, qml_harness):
        window, backend, _settings = qml_harness
        type_text(window, "artistField", "Pink Floyd")
        type_text(window, "albumField", "Live at Pompeii")

        assert prop(window, "artistField") == "Pink Floyd"
        assert prop(window, "albumField") == "Live at Pompeii"
        assert backend.artistName == "Pink Floyd"
        assert backend.albumName == "Live at Pompeii"

    def test_surrounding_whitespace_is_trimmed_in_the_job(
        self, qml_harness, fake_pipeline, tmp_path
    ):
        window, backend, _settings = qml_harness
        fill_form(window, backend, artist="  Pink Floyd  ", output_dir=tmp_path)
        type_text(window, "albumField", " Live at Pompeii ")

        click_item(window, "startButton")
        wait_until(lambda: not backend.busy and len(fake_pipeline.instances) == 1)

        job = fake_pipeline.instances[0].job
        assert job.artist == "Pink Floyd"
        assert job.album == "Live at Pompeii"


class TestPreview:
    def test_tracklist_preview_populates_listview_model(self, qml_harness):
        window, backend, _settings = qml_harness
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
        window, backend, _settings = qml_harness
        set_text(window, "tracklistArea", "Opening - 0:00\nbad line without time")

        assert prop(window, "previewStatusText") == "1 error(s)"
        assert backend.previewValid is False

        model = backend.trackPreviewModel
        idx1 = model.index(1, 0)
        assert model.data(idx1, model.IsValidRole) is False
        assert model.data(idx1, model.ErrorRole) != ""

    def test_typed_template_updates_preview(self, qml_harness):
        window, backend, _settings = qml_harness
        set_text(window, "tracklistArea", "0:00 Opening\n4:32 Encore")
        type_text(window, "templateField", "%mm%:%ss% %songname%")

        assert prop(window, "templateField") == "%mm%:%ss% %songname%"
        assert backend.currentTemplate == "%mm%:%ss% %songname%"
        assert prop(window, "previewStatusText") == "2 tracks"

    def test_invalid_template_shows_error_in_qml(self, qml_harness):
        window, _backend, _settings = qml_harness
        type_text(window, "templateField", "%songname%")

        assert prop(window, "templateErrorText", "visible") is True
        assert prop(window, "templateErrorText") != ""


class TestPipeline:
    def test_fake_pipeline_matches_real_constructor(self):
        real = inspect.signature(DownloadSplitPipeline.__init__).parameters
        fake = inspect.signature(FakePipeline.__init__).parameters
        assert list(fake) == list(real)
        for method in ("execute", "cancel"):
            assert callable(getattr(DownloadSplitPipeline, method))

    def test_start_without_url_shows_error(self, qml_harness, fake_pipeline):
        window, _backend, _settings = qml_harness
        click_item(window, "startButton")

        assert "Please enter a YouTube URL" in prop(window, "urlErrorText")
        assert prop(window, "urlErrorText", "visible") is True
        assert fake_pipeline.instances == []

    def test_start_without_artist_or_album_shows_metadata_error(
        self, qml_harness, fake_pipeline
    ):
        window, backend, _settings = qml_harness
        fill_form(window, backend, artist="")
        click_item(window, "startButton")

        assert "artist name or album" in prop(window, "metadataErrorText")
        assert prop(window, "metadataErrorText", "visible") is True
        assert fake_pipeline.instances == []

    def test_start_with_empty_output_dir_shows_dir_error(
        self, qml_harness, fake_pipeline
    ):
        window, backend, _settings = qml_harness
        fill_form(window, backend, output_dir="")
        click_item(window, "startButton")

        assert "Please select an output directory" in prop(window, "dirErrorText")
        assert prop(window, "dirErrorText", "visible") is True
        assert fake_pipeline.instances == []

    def test_successful_pipeline_run_updates_progress_and_shows_completion_modal(
        self, qml_harness, fake_pipeline, tmp_path
    ):
        window, backend, settings = qml_harness
        fill_form(window, backend, output_dir=tmp_path)

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
        window, backend, _settings = qml_harness
        fill_form(window, backend, output_dir=tmp_path)

        click_item(window, "startButton")
        wait_until(lambda: prop(window, "progressStageText") == "Error")

        assert backend.busy is False
        assert prop(window, "msgOverlay", "visible") is True
        assert prop(window, "msgTitle") == "Error"
        assert "network down" in prop(window, "msgBody")

    def test_cancel_running_job(self, qml_harness, fake_pipeline, tmp_path):
        fake_pipeline.gate = threading.Event()
        window, backend, _settings = qml_harness
        fill_form(window, backend, output_dir=tmp_path)

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

    def test_second_start_while_running_is_ignored(
        self, qml_harness, fake_pipeline, tmp_path
    ):
        fake_pipeline.gate = threading.Event()
        window, backend, _settings = qml_harness
        fill_form(window, backend, output_dir=tmp_path)

        click_item(window, "startButton")
        wait_until(lambda: backend.busy)
        click_item(window, "startButton")
        backend.startPipeline()

        fake_pipeline.gate.set()
        wait_until(lambda: not backend.busy)
        assert len(fake_pipeline.instances) == 1


class TestAiAssist:
    def test_ai_button_disabled_until_video_and_tracklist_ready(self, qml_harness):
        window, backend, _settings = qml_harness
        assert prop(window, "aiButtonRect", "enabled") is False

        set_text(window, "tracklistArea", "Intro - 0:00")
        assert prop(window, "aiButtonRect", "enabled") is False

        load_video(window, backend)
        assert prop(window, "aiButtonRect", "enabled") is True

    def test_api_provider_overwrites_typed_template_artist_and_album(
        self, qml_harness, monkeypatch
    ):
        window, backend, _settings = qml_harness
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

        use_ai_http(monkeypatch, fake_post)

        load_video(window, backend)
        # The user types into the fields first; AI Assist must still replace them.
        type_text(window, "templateField", "%songname% - %mm%:%ss%")
        type_text(window, "artistField", "Manual Draft")
        type_text(window, "albumField", "Manual Album")
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
        window, backend, _settings = qml_harness
        backend.setLlmProvider(LlmProvider.OPENAI.value)
        backend.setOpenaiApiKey("sk-bad-key")

        def failing_post(url, headers, body):
            raise LlmError("LLM request failed: HTTP 401: invalid api key")

        use_ai_http(monkeypatch, failing_post)

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
        window, backend, _settings = qml_harness
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
        window, _backend, _settings = qml_harness
        help_panel = find_item(window, "helpPanel")
        assert help_panel.property("open") is False

        find_item(window, "helpMenuAction").trigger(None)
        QApplication.processEvents()

        assert help_panel.property("open") is True
        assert help_panel.property("visible") is True
        assert "YouTube Bootlegger" in prop(window, "helpTitleText")

        click_item(window, "helpCloseButton")
        assert help_panel.property("open") is False
        assert help_panel.property("visible") is False

    def test_settings_panel_edits_persist_across_restart(
        self, qml_harness, settings_store
    ):
        window, backend, settings = qml_harness
        settings_panel = open_settings(window)
        assert settings_panel.property("open") is True

        click_item(window, "externalYtdlpToggle")
        assert backend.useExternalYtdlp is True
        assert prop(window, "ytdlpPathSection", "enabled") is True

        click_item(window, "provider_anthropic")
        assert backend.llmProvider == "anthropic"
        assert prop(window, "anthropicSection", "visible") is True
        assert prop(window, "openaiSection", "visible") is False

        type_text(window, "ytdlpPathField", "/opt/yt-dlp")
        type_text(window, "ffmpegPathField", "/opt/ffmpeg")
        type_text(window, "anthropicKeyField", "sk-ant-123")
        type_text(window, "anthropicModelField", "claude-custom")

        click_item(window, "settingsDoneButton")

        assert settings_panel.property("open") is False
        assert settings.use_external_ytdlp is True
        assert settings.ytdlp_path == "/opt/yt-dlp"
        assert settings.ffmpeg_path == "/opt/ffmpeg"
        assert settings.llm_provider == LlmProvider.ANTHROPIC
        assert settings.anthropic_api_key == "sk-ant-123"
        assert settings.anthropic_model == "claude-custom"
        assert backend.llmConfigured is True

        # A fresh app reading the same stored settings shows the saved values.
        reloaded = AppBackend(settings=AppSettings(settings_store))
        with open_window(reloaded) as (window2, warnings):
            open_settings(window2)
            assert prop(window2, "ytdlpPathField") == "/opt/yt-dlp"
            assert prop(window2, "ffmpegPathField") == "/opt/ffmpeg"
            assert prop(window2, "anthropicSection", "visible") is True
            assert prop(window2, "anthropicKeyField") == "sk-ant-123"
            assert prop(window2, "anthropicModelField") == "claude-custom"
            assert warnings == []

    def test_settings_field_saves_on_enter_without_done(self, qml_harness):
        window, _backend, settings = qml_harness
        open_settings(window)

        type_text(window, "ffmpegPathField", "/usr/local/bin/ffmpeg")
        press_key(window, Qt.Key.Key_Return)

        assert settings.ffmpeg_path == "/usr/local/bin/ffmpeg"
