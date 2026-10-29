"""TUI runtime-tool downloads: the banner, Start gating and the Settings section.

Driven headlessly with Pilot. Only the outside world is faked: the pinned
manifest and HTTP (tests.tools_support), PATH, the video lookup and the
download/split pipeline. The real installer writes to a temporary folder.
"""

import time
import urllib.error
from pathlib import Path

import pytest
from textual.widgets import Button, Input, ProgressBar, Static, TextArea

from src.youtube_bootlegger.app_logic import TOOLS_SECTION_TITLE
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.video_info import VideoInfo
from src.youtube_bootlegger.tui import BootleggerApp
from src.youtube_bootlegger.tui import app as app_module
from src.youtube_bootlegger.tui.screens import SettingsScreen
from src.youtube_bootlegger.tui.widgets import StatusLog
from tests.qml_support import DictBackend
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SIZE = (140, 45)
ALL_TOOLS = ("yt-dlp", "ffmpeg", "deno")


class FakePipeline:
    """Stands in for DownloadSplitPipeline; records that a job started."""

    instances: list["FakePipeline"] = []

    def __init__(self, progress_callback=None, log_callback=None, settings=None):
        FakePipeline.instances.append(self)

    def execute(self, job):
        return [Path("/out/01 - Intro.mp3")]

    def cancel(self):
        pass


@pytest.fixture
def server(monkeypatch):
    return use_fake_tools(monkeypatch)


@pytest.fixture
def backend():
    return DictBackend()


@pytest.fixture
def tools_dir(tmp_path):
    return tmp_path / "tools"


@pytest.fixture
def settings(backend, tools_dir):
    return AppSettings(backend, tools_dir=tools_dir)


@pytest.fixture
def fake_video(monkeypatch):
    def fetch(url, settings=None, comment_limit=0):
        return VideoInfo(
            video_id="dQw4w9WgXcQ", title="Live", channel="Band", duration=600,
            duration_string="10:00", thumbnail_url="", view_count=1, upload_date="20240131",
        )

    monkeypatch.setattr(app_module, "fetch_video_info", fetch)
    monkeypatch.setattr(app_module, "URL_DEBOUNCE_SECONDS", 0.01)


@pytest.fixture
def fake_pipeline(monkeypatch):
    FakePipeline.instances = []
    monkeypatch.setattr(app_module, "DownloadSplitPipeline", FakePipeline)
    return FakePipeline


@pytest.fixture(autouse=True)
def open_gate(server):
    yield
    server.release()  # Never leave a download thread blocked after a test.


def make_app(settings, server) -> BootleggerApp:
    return BootleggerApp(settings, show_thumbnail=False, tools_http_get=server.http_get)


async def wait_for(pilot, condition, attempts=250):
    for _ in range(attempts):
        if condition():
            return
        await pilot.pause(0.02)
    raise AssertionError("condition not met")


def text_of(widget_or_screen, selector) -> str:
    return str(widget_or_screen.query_one(selector, Static).render())


def banner_shown(app) -> bool:
    return app.query_one("#tools-banner").display


def banner_text(app) -> str:
    return text_of(app, "#tools-banner-text")


def banner_button(app) -> Button:
    return app.query_one("#tools-banner-action", Button)


def button_label(app) -> str:
    button = banner_button(app)
    return str(button.label) if button.display else ""


def log_text(app) -> str:
    return "\n".join(line.text for line in app.query_one(StatusLog).lines)


def installed(settings, tool_ids=ALL_TOOLS) -> bool:
    store = settings.tool_store
    return all(store.is_installed(tool_id) for tool_id in tool_ids)


async def fill_form(app, pilot):
    app.query_one("#url", Input).value = VALID_URL
    await wait_for(pilot, lambda: app._video_info is not None)
    app.query_one("#tracklist", TextArea).text = "Intro - 0:00\nSong - 4:30"
    app.query_one("#artist", Input).value = "The Band"
    app.query_one("#output-dir", Input).value = "/tmp/out"
    await pilot.pause()


async def click_banner(pilot, app):
    # A button ignores clicks during its brief pressed animation, as for a user.
    await wait_for(pilot, lambda: not banner_button(app).has_class("-active"))
    await pilot.click("#tools-banner-action")


async def click(pilot, screen, selector):
    screen.query_one(selector).scroll_visible(animate=False)
    await pilot.pause()
    await pilot.click(selector)


class TestFirstLaunch:
    async def test_downloads_by_itself_shows_progress_then_hides(
        self, settings, server, monkeypatch, fake_video, fake_pipeline
    ):
        fake_path(monkeypatch)
        server.hold()
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await wait_for(pilot, lambda: server.requests)
            assert banner_shown(app)
            assert banner_text(app) == "Preparing tool download…"
            assert button_label(app) == "Cancel"
            bar = app.query_one("#tools-banner-progress", ProgressBar)
            assert bar.display and bar.total is None  # Indeterminate until bytes arrive.

            server.release()
            await wait_for(pilot, lambda: not banner_shown(app))
            assert installed(settings)
            assert [url.split("/")[-1] for url in server.requests] == [
                "yt-dlp-1.0.zip", "ffmpeg-1.0.zip", "deno-1.0.zip",
            ]

            await fill_form(app, pilot)
            await pilot.press("f5")
            await wait_for(pilot, lambda: fake_pipeline.instances and not app.busy)

    async def test_restart_finds_the_download(self, backend, tools_dir, server, monkeypatch):
        fake_path(monkeypatch)
        first = make_app(AppSettings(backend, tools_dir=tools_dir), server)
        async with first.run_test(size=SIZE) as pilot:
            await wait_for(pilot, lambda: server.requests and not banner_shown(first))
        assert installed(AppSettings(backend, tools_dir=tools_dir))
        server.requests.clear()

        again = make_app(AppSettings(backend, tools_dir=tools_dir), server)
        async with again.run_test(size=SIZE) as pilot:
            await pilot.pause(0.1)
            assert server.requests == []
            assert not banner_shown(again)

    async def test_only_ytdlp_downloaded_when_others_are_on_path(
        self, settings, server, monkeypatch
    ):
        fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await wait_for(pilot, lambda: installed(settings, ("yt-dlp",)))
            await wait_for(pilot, lambda: not banner_shown(app))
            assert [url.split("/")[-1] for url in server.requests] == ["yt-dlp-1.0.zip"]
            assert not installed(settings, ("ffmpeg",))


class TestBannerActions:
    async def test_cancel_then_download(self, settings, server, monkeypatch):
        fake_path(monkeypatch)
        server.hold()
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await wait_for(pilot, lambda: button_label(app) == "Cancel")
            await click_banner(pilot, app)
            server.release()
            await wait_for(pilot, lambda: button_label(app) == "Download")
            assert banner_text(app).startswith("Download cancelled. ")
            assert not installed(settings, ("yt-dlp",))

            await click_banner(pilot, app)
            await wait_for(pilot, lambda: not banner_shown(app))
            assert installed(settings)

    async def test_network_failure_then_retry(self, settings, server, monkeypatch):
        fake_path(monkeypatch)
        server.error = urllib.error.URLError("offline")
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await wait_for(pilot, lambda: button_label(app) == "Retry")
            assert "offline" in banner_text(app)
            assert banner_text(app).startswith("Tool download failed: ")
            assert app.query_one("#tools-banner").has_class("-error")

            server.error = None
            await click_banner(pilot, app)
            await wait_for(pilot, lambda: not banner_shown(app))
            assert installed(settings)
            assert not app.query_one("#tools-banner").has_class("-error")


class TestStartGating:
    async def test_start_while_ffmpeg_downloads_is_blocked(
        self, settings, server, monkeypatch, fake_video, fake_pipeline
    ):
        fake_path(monkeypatch)
        server.hold()
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.press("f5")
            await pilot.pause()
            assert "Wait for FFmpeg to finish downloading." in log_text(app)
            assert fake_pipeline.instances == []
            assert not app.busy

    async def test_start_without_ffmpeg_or_downloads_is_blocked(
        self, backend, server, monkeypatch, fake_video, fake_pipeline
    ):
        fake_path(monkeypatch)
        app = make_app(AppSettings(backend), server)  # No tools folder: nothing to download.
        async with app.run_test(size=SIZE) as pilot:
            await fill_form(app, pilot)
            await pilot.press("f5")
            await pilot.pause()
            assert "FFmpeg not found. Install it, or set its path in Settings." in log_text(app)
            assert fake_pipeline.instances == []
            assert banner_shown(app)
            assert "can't be downloaded" in banner_text(app)
            assert server.requests == []


class TestSettingsSection:
    async def test_shows_statuses_and_folder(self, settings, server, monkeypatch, tools_dir):
        fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
        install_fake_tools(tools_dir, server, ("yt-dlp",))
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.press("f2")
            screen = app.screen
            assert isinstance(screen, SettingsScreen)
            body = "\n".join(str(s.render()) for s in screen.query(".section-title"))
            assert TOOLS_SECTION_TITLE.upper() in body
            statuses = text_of(screen, "#tools-statuses")
            assert f"yt-dlp: Downloaded: {tools_dir}" in statuses
            assert "FFmpeg: From PATH: /usr/bin/ffmpeg" in statuses
            assert "Deno: From PATH: /usr/bin/deno" in statuses
            assert str(tools_dir) in text_of(screen, "#tools-folder")
            assert text_of(screen, "#ffmpeg-warning") == ""
            assert screen.query_one("#setting-ffmpeg-path", Input).placeholder.startswith(
                "Leave empty to use FFmpeg from PATH"
            )

    async def test_verify_redownloads_tampered_tool(
        self, settings, server, monkeypatch, tools_dir
    ):
        fake_path(monkeypatch)
        install_fake_tools(tools_dir, server)
        ytdlp = settings.tool_store.executable("yt-dlp")
        original = ytdlp.read_bytes()
        ytdlp.write_bytes(b"tampered")
        server.hold()
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause(0.1)
            assert server.requests == []  # Tampering isn't noticed without Verify.
            await pilot.press("f2")
            screen = app.screen
            await click(pilot, screen, "#tools-verify")
            await wait_for(pilot, lambda: server.requests)
            assert screen.query_one("#tools-verify", Button).disabled
            assert screen.query_one("#tools-download-missing", Button).disabled
            assert banner_shown(app) and button_label(app) == "Cancel"

            server.release()
            await wait_for(pilot, lambda: not screen.query_one("#tools-verify", Button).disabled)
            assert [url.split("/")[-1] for url in server.requests] == ["yt-dlp-1.0.zip"]
            assert settings.tool_store.executable("yt-dlp").read_bytes() == original
            assert "yt-dlp: Downloaded:" in text_of(screen, "#tools-statuses")

    async def test_download_missing_after_cancel(self, settings, server, monkeypatch):
        fake_path(monkeypatch)
        server.hold()
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await wait_for(pilot, lambda: button_label(app) == "Cancel")
            await click_banner(pilot, app)
            server.release()
            await wait_for(pilot, lambda: button_label(app) == "Download")
            await pilot.press("f2")
            screen = app.screen
            assert "yt-dlp: Not downloaded yet" in text_of(screen, "#tools-statuses")
            await click(pilot, screen, "#tools-download-missing")
            await wait_for(pilot, lambda: installed(settings))
            await wait_for(
                pilot, lambda: "FFmpeg: Downloaded:" in text_of(screen, "#tools-statuses")
            )
            assert isinstance(app.screen, SettingsScreen)  # The button doesn't close Settings.

    async def test_saving_settings_starts_auto_download(
        self, backend, tools_dir, server, monkeypatch
    ):
        settings = AppSettings(backend, tools_dir=tools_dir)
        settings.ffmpeg_path = "/opt/custom/ffmpeg"
        settings.ytdlp_path = "/opt/custom/yt-dlp"
        fake_path(monkeypatch, {"deno"})
        app = make_app(settings, server)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause(0.1)
            assert server.requests == []  # Custom paths: nothing to download.
            await pilot.press("f2")
            app.screen.query_one("#setting-ffmpeg-path", Input).value = ""
            await pilot.pause()
            assert "Not downloaded yet" in text_of(app.screen, "#ffmpeg-warning")
            await pilot.press("ctrl+s")
            await wait_for(pilot, lambda: installed(settings, ("ffmpeg",)))
            assert [url.split("/")[-1] for url in server.requests] == ["ffmpeg-1.0.zip"]


async def test_saving_settings_mid_download_keeps_the_downloaded_ytdlp_default(
    backend, tools_dir, server, monkeypatch
):
    """Saving Settings before yt-dlp arrives must not store "external off" for good."""
    settings = AppSettings(backend, tools_dir=tools_dir)
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
    server.hold()
    app = make_app(settings, server)
    async with app.run_test(size=SIZE) as pilot:
        await wait_for(pilot, lambda: server.requests)
        await pilot.press("f2")
        await wait_for(pilot, lambda: isinstance(app.screen, SettingsScreen))
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: not isinstance(app.screen, SettingsScreen))
        server.release()
        await wait_for(pilot, lambda: installed(settings, ("yt-dlp",)))
        await wait_for(pilot, lambda: not banner_shown(app))
    assert AppSettings(backend, tools_dir=tools_dir).use_external_ytdlp is True


async def test_quit_cancels_running_download(settings, server, monkeypatch, tools_dir):
    fake_path(monkeypatch)
    server.hold()
    app = make_app(settings, server)
    async with app.run_test(size=SIZE) as pilot:
        await wait_for(pilot, lambda: server.requests)
        await pilot.press("ctrl+q")
    server.release()
    # The download thread removes its staging folder once it stops.
    for _ in range(250):
        if not list(tools_dir.glob(".staging-*")):
            break
        time.sleep(0.02)
    else:
        raise AssertionError("download kept running after quit")
    assert not installed(settings, ("yt-dlp",))
    assert len(server.requests) == 1
