"""Interaction tests for the Textual TUI, driven headlessly with Pilot."""

import threading
import time
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Static, TextArea

from src.youtube_bootlegger.core.exceptions import DownloadError, ValidationError
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.core.video_info import VideoInfo
from src.youtube_bootlegger.llm import TracklistExtraction
from src.youtube_bootlegger.tui import BootleggerApp
from src.youtube_bootlegger.tui import app as app_module
from src.youtube_bootlegger.tui.screens import (
    ConfirmScreen,
    DirectoryPickerScreen,
    HelpScreen,
    SettingsScreen,
)
from src.youtube_bootlegger.tui.screens.help import build_help_markdown
from src.youtube_bootlegger.tui.widgets import TrackPreviewTable

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SIZE = (140, 45)


class DictBackend:
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
    """Stands in for DownloadSplitPipeline; behaviour set per test."""

    instances: list["FakePipeline"] = []
    outcome: object = None  # list of paths, or an exception to raise
    gate: threading.Event | None = None

    def __init__(self, progress_callback=None, log_callback=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.cancelled = False
        self.job = None
        FakePipeline.instances.append(self)

    def execute(self, job):
        self.job = job
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


@pytest.fixture
def settings():
    return AppSettings(DictBackend())


@pytest.fixture
def fake_pipeline(monkeypatch):
    FakePipeline.instances = []
    FakePipeline.outcome = [Path("/out/01 - Intro.mp3"), Path("/out/02 - Song.mp3")]
    FakePipeline.gate = None
    monkeypatch.setattr(app_module, "DownloadSplitPipeline", FakePipeline)
    return FakePipeline


@pytest.fixture
def fake_video(monkeypatch):
    calls = []

    def fetch(url, settings=None):
        calls.append(url)
        return make_video()

    monkeypatch.setattr(app_module, "fetch_video_info", fetch)
    monkeypatch.setattr(app_module, "is_ffmpeg_available", lambda cmd: True)
    monkeypatch.setattr(app_module, "URL_DEBOUNCE_SECONDS", 0.01)
    return calls


def make_app(settings) -> BootleggerApp:
    return BootleggerApp(settings, show_thumbnail=False)


async def wait_for(pilot, condition, attempts=100):
    for _ in range(attempts):
        if condition():
            return
        await pilot.pause(0.02)
    raise AssertionError("condition not met")


def static_text(app, selector) -> str:
    return str(app.query_one(selector, Static).render())


async def load_video(app, pilot):
    app.query_one("#url", Input).value = VALID_URL
    await wait_for(pilot, lambda: app._video_info is not None)


async def fill_form(app, pilot, artist="The Band"):
    await load_video(app, pilot)
    app.query_one("#tracklist", TextArea).text = "Intro - 0:00\nSong - 4:30"
    app.query_one("#artist", Input).value = artist
    app.query_one("#output-dir", Input).value = "/tmp/out"
    await pilot.pause()


class TestVideoInfo:
    async def test_valid_url_fetches_and_shows_video(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await load_video(app, pilot)
            await pilot.pause()
            assert fake_video == [VALID_URL]
            assert "Live at the Venue" in static_text(app, "#video-title")
            assert "Band Channel" in static_text(app, "#video-channel")
            assert "Duration: 1:00:00" in static_text(app, "#video-details")
            assert app.query_one("#album", Input).placeholder == "Live at the Venue"

    async def test_invalid_url_does_not_fetch(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#url", Input).value = "https://example.com/video"
            await pilot.pause(0.1)
            assert fake_video == []
            assert app._video_info is None

    async def test_fetch_error_is_shown(self, settings, fake_video, monkeypatch):
        def failing_fetch(url, settings=None):
            raise ValidationError("Video unavailable")

        monkeypatch.setattr(app_module, "fetch_video_info", failing_fetch)
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#url", Input).value = VALID_URL
            await wait_for(pilot, lambda: "unavailable" in static_text(app, "#url-error"))
            assert app.query_one("#url-error").display is True
            assert "Video unavailable" in static_text(app, "#video-title")


class TestPreview:
    async def test_tracklist_preview_counts_tracks(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#tracklist", TextArea).text = "A - 0:00\nB - 1:00"
            await pilot.pause()
            assert app.query_one(TrackPreviewTable).row_count == 2
            assert static_text(app, "#preview-status") == "2 tracks"

    async def test_bad_line_marks_preview_invalid(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#tracklist", TextArea).text = "A - 0:00\nno time"
            await pilot.pause()
            status = app.query_one("#preview-status", Static)
            assert str(status.render()) == "1 error(s)"
            assert status.has_class("-invalid")

    async def test_invalid_template_shows_error(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#template", Input).value = "%songname%"
            await pilot.pause()
            assert app.query_one("#template-error").display is True


class TestPipeline:
    async def test_start_without_url_shows_error(self, settings, fake_video, fake_pipeline):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.press("f5")
            assert "Please enter a YouTube URL" in static_text(app, "#url-error")
            assert fake_pipeline.instances == []
            assert app.focused.id == "url"

    async def test_start_without_artist_or_album(self, settings, fake_video, fake_pipeline):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot, artist="")
            await pilot.press("f5")
            assert "artist name or album" in static_text(app, "#metadata-error")
            assert fake_pipeline.instances == []

    async def test_successful_run(self, settings, fake_video, fake_pipeline):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.click("#start")
            await wait_for(pilot, lambda: not app.busy and fake_pipeline.instances)
            await pilot.pause()
            job = fake_pipeline.instances[0].job
            assert job.url == VALID_URL
            assert job.artist == "The Band"
            assert job.album == "Live at the Venue"
            assert [t.name for t in job.tracks] == ["Intro", "Song"]
            assert static_text(app, "#progress-stage") == "Complete!"
            assert app.query_one("#start", Button).disabled is False

    async def test_pipeline_error_reported(self, settings, fake_video, fake_pipeline):
        fake_pipeline.outcome = DownloadError("network down")
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.press("f5")
            await wait_for(pilot, lambda: static_text(app, "#progress-stage") == "Error")
            assert app.busy is False

    async def test_cancel_running_job(self, settings, fake_video, fake_pipeline):
        fake_pipeline.gate = threading.Event()
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.press("f5")
            await wait_for(pilot, lambda: "Downloading" in static_text(app, "#progress-stage"))
            assert app.query_one("#cancel", Button).disabled is False
            await pilot.press("f8")
            assert fake_pipeline.instances[0].cancelled is True
            fake_pipeline.gate.set()
            await wait_for(pilot, lambda: not app.busy)
            assert static_text(app, "#progress-stage") == "Cancelled"

    async def test_quit_while_busy_asks_for_confirmation(
        self, settings, fake_video, fake_pipeline
    ):
        fake_pipeline.gate = threading.Event()
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.press("f5")
            await wait_for(pilot, lambda: app.busy)
            await pilot.press("ctrl+q")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)
            await pilot.click("#confirm-no")
            await pilot.pause()
            assert not isinstance(app.screen, ConfirmScreen)
            fake_pipeline.gate.set()
            await wait_for(pilot, lambda: not app.busy)


class TestQuitWhileRunning:
    async def test_confirmed_quit_cancels_and_exits_promptly(
        self, settings, fake_video, fake_pipeline
    ):
        # The real pipeline logs (via call_from_thread) while cleaning up after
        # cancel; quitting must not block the UI thread or the two deadlock.
        class LoggingCancelPipeline(FakePipeline):
            def cancel(self):
                super().cancel()
                FakePipeline.gate.set()

            def execute(self, job):
                result = super().execute(job)
                self.log_callback("Cancelled; removing partial output.")
                return result

        fake_pipeline.gate = threading.Event()
        app_module.DownloadSplitPipeline = LoggingCancelPipeline
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.press("f5")
            await wait_for(pilot, lambda: app.busy)
            await pilot.press("ctrl+q")
            await pilot.pause()
            start = time.monotonic()
            await pilot.click("#confirm-yes")
            await wait_for(pilot, lambda: not app.is_running, attempts=200)
            assert time.monotonic() - start < 2
            assert fake_pipeline.instances[0].cancelled is True


class TestAiAssist:
    async def test_requires_video_info(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#tracklist", TextArea).text = "A - 0:00"
            await pilot.press("f3")
            await pilot.pause()
            assert app.ai_running is False

    async def test_api_provider_fills_template_and_metadata(
        self, settings, fake_video, monkeypatch
    ):
        settings.llm_provider = LlmProvider.OPENAI
        settings.openai_api_key = "sk-test"
        monkeypatch.setattr(
            app_module,
            "extract_tracklist_metadata",
            lambda s, title, text: TracklistExtraction(
                template="%mm%:%ss% %songname%", artist_name="AI Band", album_name="AI Album"
            ),
        )
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await load_video(app, pilot)
            app.query_one("#tracklist", TextArea).text = "0:00 Intro"
            await pilot.press("f3")
            await wait_for(pilot, lambda: app.query_one("#artist", Input).value == "AI Band")
            assert app.query_one("#template", Input).value == "%mm%:%ss% %songname%"
            assert app.query_one("#album", Input).value == "AI Album"
            assert app.ai_running is False

    async def test_lite_without_browser_copies_prompt(self, settings, fake_video, monkeypatch):
        monkeypatch.setattr(app_module, "open_url_in_browser", lambda url: False)
        app = make_app(settings)
        copied = []
        monkeypatch.setattr(app, "copy_to_clipboard", copied.append)
        async with app.run_test(size=SIZE) as pilot:
            await load_video(app, pilot)
            app.query_one("#tracklist", TextArea).text = "Intro - 0:00"
            await pilot.press("f3")
            await pilot.pause()
            assert copied and copied[-1].startswith("YouTube Bootlegger")
            assert "Live at the Venue" in copied[-1]


class TestDialogs:
    async def test_help_opens_and_closes(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.press("f1")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            assert not isinstance(app.screen, HelpScreen)

    async def test_settings_save_persists(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.press("f2")
            screen = app.screen
            assert isinstance(screen, SettingsScreen)
            screen.query_one("#setting-ffmpeg-path", Input).value = "/opt/ffmpeg"
            screen.query_one("#setting-llm-provider").value = LlmProvider.ANTHROPIC
            await pilot.pause()
            assert screen.query_one("#provider-anthropic").display is True
            assert screen.query_one("#provider-openai").display is False
            screen.query_one("#setting-anthropic-api-key", Input).value = "key-123"
            await pilot.click("#settings-save")
            await pilot.pause()
            assert settings.ffmpeg_path == "/opt/ffmpeg"
            assert settings.llm_provider == LlmProvider.ANTHROPIC
            assert settings.anthropic_api_key == "key-123"

    async def test_settings_cancel_discards(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.press("f2")
            app.screen.query_one("#setting-ffmpeg-path", Input).value = "/nope"
            await pilot.press("escape")
            await pilot.pause()
            assert settings.ffmpeg_path == ""

    async def test_directory_picker_sets_output(self, settings, fake_video, tmp_path):
        (tmp_path / "music").mkdir()
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#output-dir", Input).value = str(tmp_path)
            await pilot.press("ctrl+o")
            screen = app.screen
            assert isinstance(screen, DirectoryPickerScreen)
            screen.query_one("#dir-path", Input).value = str(tmp_path / "music")
            await pilot.click("#dir-select")
            await pilot.pause()
            assert app.query_one("#output-dir", Input).value == str(tmp_path / "music")


class TestUntrustedText:
    """Track names, titles and errors must never be parsed as Rich markup."""

    async def test_bracketed_track_names_do_not_crash(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app.query_one("#tracklist", TextArea).text = "Song [/feat] - 3:00\n[bold] - 4:00"
            await pilot.pause(0.2)
            table = app.query_one(TrackPreviewTable)
            assert table.row_count == 2
            assert str(table.get_cell_at((0, 2))) == "Song [/feat]"

    async def test_bracketed_title_and_error_shown_verbatim(
        self, settings, fake_video, monkeypatch
    ):
        monkeypatch.setattr(
            app_module,
            "fetch_video_info",
            lambda url, settings=None: make_video(title="Live [Full Concert] [/x]"),
        )
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await load_video(app, pilot)
            await pilot.pause()
            assert static_text(app, "#video-title") == "Live [Full Concert] [/x]"

            def failing_fetch(url, settings=None):
                raise ValidationError("ERROR: [youtube] abc: [/oops]")

            monkeypatch.setattr(app_module, "fetch_video_info", failing_fetch)
            app.query_one("#url", Input).value = "https://youtu.be/other"
            await wait_for(pilot, lambda: "[youtube]" in static_text(app, "#url-error"))
            assert "[/oops]" in static_text(app, "#url-error")


class TestUrlEditing:
    async def test_editing_url_clears_previous_video_immediately(
        self, settings, fake_video, fake_pipeline, monkeypatch
    ):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            monkeypatch.setattr(app_module, "URL_DEBOUNCE_SECONDS", 10)
            app.query_one("#url", Input).value = "https://youtu.be/different"
            await pilot.press("f5")
            assert fake_pipeline.instances == []
            assert "wait" in static_text(app, "#url-error")

    async def test_returning_to_same_url_refetches(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            await load_video(app, pilot)
            app.query_one("#url", Input).value = "not a url"
            await pilot.pause()
            assert app._video_info is None
            app.query_one("#url", Input).value = VALID_URL
            await wait_for(pilot, lambda: app._video_info is not None)
            assert fake_video == [VALID_URL, VALID_URL]

    async def test_stale_video_result_is_ignored(self, settings, fake_video):
        app = make_app(settings)
        async with app.run_test(size=SIZE) as pilot:
            app._start_video_info_fetch("https://youtu.be/new")
            app._on_video_info_loaded(VALID_URL, make_video(title="Old"))
            assert app._video_info is None


def test_help_shortcuts_match_app_bindings():
    from src.youtube_bootlegger.tui.screens.help import keyboard_shortcuts

    shortcuts = dict(keyboard_shortcuts(BootleggerApp.BINDINGS))
    assert shortcuts["F5 / Ctrl+R"] == "Start"
    assert shortcuts["F8"] == "Cancel"
    assert shortcuts["F3"] == "AI assist"
    assert shortcuts["Ctrl+O"] == "Output dir"
    assert "Ctrl+K" not in shortcuts and "Ctrl+A" not in shortcuts


def test_help_markdown_includes_shared_content_and_shortcuts():
    markdown = build_help_markdown()
    assert "QUICK START" in markdown
    assert "`%songname%`" in markdown
    assert "KEYBOARD SHORTCUTS" in markdown
