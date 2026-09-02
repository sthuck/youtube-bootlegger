"""Unit tests for the shared application controller."""

import pytest

from src.youtube_bootlegger.controller import AppController, stage_label

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
TRACKLIST = "Opening Number - 0:00\nSecond Song - 4:32\nThird Song - 8:15"


@pytest.fixture
def controller(qapp, settings):
    """Return a controller backed by in-memory settings."""
    return AppController(settings=settings)


@pytest.fixture
def loaded(controller, video_info):
    """Return a controller with a URL entered and video info resolved."""
    controller.set_url(VALID_URL)
    controller._url_debounce.stop()  # never hit the network in tests
    controller._on_video_info_loaded(video_info)
    return controller


def collect(signal):
    """Record every payload emitted by a single-argument signal."""
    seen = []
    signal.connect(lambda value: seen.append(value))
    return seen


class TestInputSetters:
    """Setters are idempotent and notify only on real changes."""

    def test_set_artist_strips_and_notifies_once(self, controller):
        seen = collect(controller.artistChanged)
        controller.set_artist("  The Band  ")
        controller.set_artist("The Band")
        assert controller.artist == "The Band"
        assert seen == ["The Band"]

    def test_set_template_notifies_and_revalidates(self, controller):
        templates = collect(controller.templateChanged)
        errors = collect(controller.templateErrorChanged)
        controller.set_template("%songname% @ %mm%:%ss%")
        assert templates == ["%songname% @ %mm%:%ss%"]
        assert errors == [""]

    def test_invalid_template_reports_an_error(self, controller):
        errors = collect(controller.templateErrorChanged)
        controller.set_template("no placeholders here")
        assert errors and errors[-1] != ""

    def test_template_falls_back_to_the_default_when_blank(self, controller):
        controller.set_template("")
        assert controller.template == "%songname% - %mm%:%ss%"

    def test_set_url_clears_video_when_emptied(self, controller, video_info):
        controller.set_url(VALID_URL)
        controller._url_debounce.stop()
        controller._on_video_info_loaded(video_info)
        cleared = []
        controller.videoCleared.connect(lambda: cleared.append(True))
        controller.set_url("")
        assert cleared == [True]
        assert controller.video_info is None

    def test_invalid_url_does_not_schedule_a_fetch(self, controller):
        controller.set_url("https://example.com/not-youtube")
        assert not controller._url_debounce.isActive()

    def test_valid_url_schedules_a_debounced_fetch(self, controller):
        controller.set_url(VALID_URL)
        assert controller._url_debounce.isActive()
        controller._url_debounce.stop()


class TestPreview:
    """Tracklist edits push a fresh preview to the UI."""

    def test_emits_preview_on_tracklist_change(self, controller):
        previews = collect(controller.previewChanged)
        controller.set_tracklist_text(TRACKLIST)
        assert len(previews) == 1
        assert previews[0].total_lines == 3
        assert previews[0].is_valid

    def test_reports_parse_errors_in_the_preview(self, controller):
        previews = collect(controller.previewChanged)
        controller.set_tracklist_text("this line has no timestamp")
        assert previews[-1].error_count == 1
        assert not previews[-1].is_valid

    def test_current_preview_matches_state(self, controller):
        controller.set_tracklist_text(TRACKLIST)
        assert controller.current_preview().total_lines == 3


class TestBuildJobValidation:
    """Every validation failure reports through a signal, never silently."""

    def test_requires_a_url(self, controller):
        errors = collect(controller.urlErrorChanged)
        assert controller.build_job() is None
        assert errors[-1] == "Please enter a YouTube URL"

    def test_rejects_a_non_youtube_url(self, controller):
        controller.set_url("https://example.com/watch?v=x")
        errors = collect(controller.urlErrorChanged)
        assert controller.build_job() is None
        assert errors[-1] == "Please enter a valid YouTube URL"

    def test_waits_for_video_info(self, controller):
        controller.set_url(VALID_URL)
        controller._url_debounce.stop()
        errors = collect(controller.urlErrorChanged)
        assert controller.build_job() is None
        assert errors[-1] == "Please wait for video info to load"

    def test_rejects_an_invalid_template(self, loaded):
        loaded.set_tracklist_text(TRACKLIST)
        loaded.set_artist("The Band")
        loaded.set_template("no placeholders")
        errors = collect(loaded.templateErrorChanged)
        assert loaded.build_job() is None
        assert errors[-1].startswith("Invalid template:")

    def test_requires_a_tracklist(self, loaded):
        errors = collect(loaded.tracklistErrorChanged)
        assert loaded.build_job() is None
        assert errors[-1] == "Please enter at least one track"

    def test_reports_unparseable_tracklist_lines(self, loaded):
        loaded.set_tracklist_text("total nonsense")
        errors = collect(loaded.tracklistErrorChanged)
        assert loaded.build_job() is None
        assert errors[-1] != ""

    def test_requires_artist_or_album(self, loaded):
        loaded.set_tracklist_text(TRACKLIST)
        errors = collect(loaded.metadataErrorChanged)
        assert loaded.build_job() is None
        assert errors[-1] == "Please enter an artist name or album name"

    def test_requires_an_output_directory(self, loaded):
        loaded.set_tracklist_text(TRACKLIST)
        loaded.set_artist("The Band")
        loaded.set_output_dir("   ")
        errors = collect(loaded.dirErrorChanged)
        assert loaded.build_job() is None
        assert errors[-1] == "Please select an output directory"

    def test_rejects_a_file_as_output_directory(self, loaded, tmp_path):
        target = tmp_path / "not-a-dir.txt"
        target.write_text("x")
        loaded.set_tracklist_text(TRACKLIST)
        loaded.set_artist("The Band")
        loaded.set_output_dir(str(target))
        errors = collect(loaded.dirErrorChanged)
        assert loaded.build_job() is None
        assert errors[-1] == "Selected path is not a directory"

    def test_start_pipeline_returns_false_when_invalid(self, controller):
        assert controller.start_pipeline() is False
        assert controller.busy is False


class TestBuildJobSuccess:
    """A fully specified form produces a runnable job."""

    @pytest.fixture
    def ready(self, loaded, tmp_path):
        loaded.set_tracklist_text(TRACKLIST)
        loaded.set_artist("The Band")
        loaded.set_output_dir(str(tmp_path))
        return loaded

    def test_builds_a_job_with_sorted_tracks(self, ready):
        job = ready.build_job()
        assert job is not None
        assert [t.name for t in job.tracks] == [
            "Opening Number",
            "Second Song",
            "Third Song",
        ]

    def test_defaults_album_to_the_video_title(self, ready, video_info):
        assert ready.build_job().album == video_info.title

    def test_uses_an_explicit_album_when_given(self, ready):
        ready.set_album("Roxy 79")
        assert ready.build_job().album == "Roxy 79"

    def test_carries_thumbnail_for_cover_art(self, ready, video_info):
        assert ready.build_job().thumbnail_url == video_info.thumbnail_url

    def test_clears_stale_errors_before_validating(self, ready):
        errors = collect(ready.urlErrorChanged)
        ready.build_job()
        assert errors[-1] == ""


class TestSettings:
    """Settings writes persist and refresh dependent state."""

    def test_update_setting_writes_and_notifies(self, controller):
        seen = []
        controller.settingChanged.connect(
            lambda name, value: seen.append((name, value))
        )
        controller.update_setting("openai_api_key", "  sk-test  ")
        assert controller.read_setting("openai_api_key") == "sk-test"
        assert seen == [("openai_api_key", "sk-test")]

    def test_update_setting_coerces_legacy_provider(self, controller):
        controller.update_setting("llm_provider", "none")
        assert controller.read_setting("llm_provider") == "chatgpt_lite"

    def test_read_all_settings_covers_every_field(self, controller):
        values = controller.read_all_settings()
        assert "openai_api_key" in values
        assert "llm_provider" in values

    def test_credentials_flip_llm_configured(self, controller):
        controller.update_setting("llm_provider", "openai")
        seen = collect(controller.llmConfiguredChanged)
        assert controller.llm_configured is False
        controller.update_setting("openai_api_key", "sk-test")
        assert controller.llm_configured is True
        assert seen == [True]

    def test_ffmpeg_path_change_rechecks_availability(self, controller):
        seen = collect(controller.ffmpegAvailableChanged)
        controller.update_setting("ffmpeg_path", "/nonexistent/ffmpeg")
        assert controller.ffmpeg_available is False
        assert seen == [False]

    def test_unknown_setting_is_rejected(self, controller):
        with pytest.raises(KeyError):
            controller.update_setting("not_a_setting", "x")


class TestAiAvailability:
    """AI assist unlocks only when tracklist, video and provider are ready."""

    def test_unavailable_without_a_tracklist(self, loaded):
        assert loaded.ai_available is False

    def test_available_once_tracklist_and_video_are_present(self, loaded):
        seen = collect(loaded.aiAvailableChanged)
        loaded.set_tracklist_text(TRACKLIST)
        assert loaded.ai_available is True
        assert seen == [True]

    def test_unavailable_without_video_info(self, controller):
        controller.set_tracklist_text(TRACKLIST)
        assert controller.ai_available is False

    def test_unavailable_when_provider_lacks_credentials(self, loaded):
        loaded.update_setting("llm_provider", "openai")
        loaded.set_tracklist_text(TRACKLIST)
        assert loaded.ai_available is False

    def test_blocked_while_analyzing(self, loaded):
        loaded.set_tracklist_text(TRACKLIST)
        loaded._set_ai_analyzing(True)
        assert loaded.ai_available is False

    def test_reports_when_video_info_is_missing(self, controller):
        controller.set_tracklist_text(TRACKLIST)
        messages = []
        controller.aiMessage.connect(
            lambda message, is_error: messages.append((message, is_error))
        )
        controller.analyze_tracklist_with_ai()
        assert messages == [
            ("Please wait for video info to load before using AI.", True)
        ]


class TestPipelineSignals:
    """Pipeline callbacks drive busy state, progress and logs."""

    def test_finish_clears_busy_and_reports_files(self, controller):
        controller._set_busy(True)
        finished = collect(controller.pipelineFinished)
        controller._on_pipeline_finished(["/tmp/01.mp3", "/tmp/02.mp3"])
        assert controller.busy is False
        assert finished == [["/tmp/01.mp3", "/tmp/02.mp3"]]

    def test_error_clears_busy_and_reports_message(self, controller):
        controller._set_busy(True)
        failed = collect(controller.pipelineFailed)
        controller._on_pipeline_error("boom")
        assert controller.busy is False
        assert failed == ["boom"]

    def test_progress_is_forwarded_with_a_log_line(self, controller):
        progress = []
        logs = []
        controller.progressChanged.connect(
            lambda stage, pct, msg: progress.append((stage, pct, msg))
        )
        controller.logMessage.connect(
            lambda message, level: logs.append((message, level))
        )
        controller._on_pipeline_progress("download", 42.0, "Downloading...")
        assert progress == [("download", 42.0, "Downloading...")]
        assert logs == [("Downloading...", "info")]

    def test_cancel_without_a_worker_is_a_no_op(self, controller):
        controller.cancel_pipeline()  # must not raise


class TestStageLabel:
    """Stage ids render as human-readable labels."""

    @pytest.mark.parametrize(
        "stage,expected",
        [
            ("download", "Downloading"),
            ("split", "Splitting"),
            ("tagging", "Tagging"),
            ("complete", "Complete"),
            ("something_else", "Something_Else"),
        ],
    )
    def test_labels(self, stage, expected):
        assert stage_label(stage) == expected
