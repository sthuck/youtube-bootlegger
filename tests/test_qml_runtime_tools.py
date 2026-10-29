"""QML UI: the first-run runtime-tools downloader (banner, Start gating, Settings section).

Only the outside world is faked: the pinned manifest and HTTP (FakeToolServer)
and which executables are on PATH. The real installer writes into tmp_path.
"""

import urllib.error
from contextlib import contextmanager

import pytest
from PySide6.QtCore import Qt

from src.youtube_bootlegger.app_logic import FFMPEG_PATH_PLACEHOLDER, YTDLP_PATH_PLACEHOLDER
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.tools import ToolStore
from src.youtube_bootlegger.qml_backend import AppBackend
from src.youtube_bootlegger.workers import tools_download_runner as tools_runner_module
from tests.qml_support import (
    DictBackend,
    click_item,
    find_item,
    open_settings,
    open_window,
    press_key,
    prop,
    type_text,
    wait_for_workers,
    wait_until,
)
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools

ALL_TOOLS = ("yt-dlp", "ffmpeg", "deno")


@pytest.fixture
def server(monkeypatch):
    server = use_fake_tools(monkeypatch)
    yield server
    server.release()


@pytest.fixture
def store():
    return DictBackend()


@pytest.fixture
def tools_dir(tmp_path):
    return tmp_path / "tools"


@contextmanager
def tools_window(store, tools_dir, server):
    backend = AppBackend(
        settings=AppSettings(store, tools_dir=tools_dir), tools_http_get=server.http_get
    )
    with open_window(backend) as (window, warnings):
        yield window, backend
        assert warnings == [], f"QML emitted warnings: {warnings}"


def installed(tools_dir, server, tool_ids=ALL_TOOLS) -> bool:
    tool_store = ToolStore(tools_dir, server.specs)
    return all(tool_store.is_installed(t) for t in tool_ids)


def banner_visible(window) -> bool:
    return prop(window, "toolsBanner", "visible")


def wait_banner_gone(window) -> None:
    try:
        wait_until(lambda: not banner_visible(window))
    except AssertionError:
        raise AssertionError(f"Banner still shown: {prop(window, 'toolsBannerText')!r}") from None


class TestFirstLaunch:
    def test_downloads_by_itself_shows_progress_then_unblocks_start(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch)
        server.hold()
        with tools_window(store, tools_dir, server) as (window, _backend):
            wait_until(lambda: server.requests)
            assert banner_visible(window) is True
            assert prop(window, "toolsBannerText") == "Preparing tool download…"
            assert prop(window, "toolsBannerProgress", "visible") is True
            assert prop(window, "toolsBannerButtonText") == "Cancel"
            assert prop(window, "startButton", "enabled") is False
            assert prop(window, "startBlockedText") == "Wait for FFmpeg to finish downloading."

            server.release()
            wait_banner_gone(window)

            assert installed(tools_dir, server)
            assert len(server.requests) == 3
            assert prop(window, "startButton", "enabled") is True
            assert prop(window, "startBlockedText", "visible") is False

    def test_restart_finds_the_download_and_requests_nothing(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch)
        with tools_window(store, tools_dir, server) as (window, _backend):
            wait_until(lambda: installed(tools_dir, server) and not banner_visible(window))
        server.requests.clear()

        with tools_window(store, tools_dir, server) as (window, backend):
            wait_for_workers(backend)
            assert server.requests == []
            assert banner_visible(window) is False
            assert prop(window, "startButton", "enabled") is True

    def test_only_ytdlp_is_requested_when_the_rest_is_on_path(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
        with tools_window(store, tools_dir, server) as (window, _backend):
            wait_until(lambda: server.requests)
            # FFmpeg from PATH works meanwhile, so Start isn't held up.
            assert prop(window, "startButton", "enabled") is True
            wait_banner_gone(window)

        assert server.requests == [server.specs["yt-dlp"].assets[0].url]
        assert installed(tools_dir, server, ["yt-dlp"])
        assert not installed(tools_dir, server, ["ffmpeg"])


def external_ytdlp_on(window) -> bool:
    return prop(window, "externalYtdlpKnob", "x") > 2


def test_ytdlp_toggle_turns_on_when_the_download_finishes(
    qapp, server, store, tools_dir, monkeypatch
):
    """The downloaded yt-dlp becomes the default; the toggle must show it, and
    one click must turn it off (it used to show off and need two clicks)."""
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
    server.hold()
    with tools_window(store, tools_dir, server) as (window, _backend):
        open_settings(window)
        wait_until(lambda: server.requests)
        assert not external_ytdlp_on(window)

        server.release()
        wait_banner_gone(window)
        wait_until(lambda: external_ytdlp_on(window))

        click_item(window, "externalYtdlpToggle")
        wait_until(lambda: not external_ytdlp_on(window))
    assert AppSettings(store, tools_dir=tools_dir).use_external_ytdlp is False


class TestBannerActions:
    def test_cancel_then_download_completes_the_install(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch)
        server.hold()
        with tools_window(store, tools_dir, server) as (window, _backend):
            wait_until(lambda: server.requests)
            click_item(window, "toolsBannerButton")
            server.release()

            wait_until(lambda: prop(window, "toolsBannerText").startswith("Download cancelled."))
            assert prop(window, "toolsBannerButtonText") == "Download"
            assert prop(window, "toolsBannerProgress", "visible") is False
            assert prop(window, "startBlockedText") == (
                "FFmpeg not downloaded yet. Use Download in the banner."
            )
            assert not installed(tools_dir, server)

            click_item(window, "toolsBannerButton")
            wait_banner_gone(window)
            assert installed(tools_dir, server)
            assert prop(window, "startButton", "enabled") is True

    def test_network_failure_shows_error_and_retry_succeeds(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch)
        server.error = urllib.error.URLError("offline")
        with tools_window(store, tools_dir, server) as (window, _backend):
            wait_until(lambda: prop(window, "toolsBannerButtonText") == "Retry")
            assert prop(window, "toolsBannerText") == (
                "Tool download failed: Could not download yt-dlp: offline"
            )
            assert prop(window, "toolsBannerText", "color").name() == "#ef4444"
            assert prop(window, "toolsBanner", "color").name() == "#2d1111"
            assert prop(window, "startButton", "enabled") is False

            server.error = None
            click_item(window, "toolsBannerButton")
            wait_banner_gone(window)
            assert installed(tools_dir, server)

    def test_closing_the_window_cancels_the_download(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch)
        server.hold()
        with tools_window(store, tools_dir, server) as (window, backend):
            wait_until(lambda: server.requests)
            window.close()
            server.release()
            wait_until(lambda: backend.tools.bannerText.startswith("Download cancelled."))
        assert not installed(tools_dir, server, ["yt-dlp"])


class TestStartGating:
    def test_start_is_blocked_with_the_reason_while_ffmpeg_downloads(
        self, qapp, server, store, tools_dir, monkeypatch, fake_pipeline
    ):
        fake_path(monkeypatch)
        server.hold()
        with tools_window(store, tools_dir, server) as (window, backend):
            wait_until(lambda: server.requests)
            reason = "Wait for FFmpeg to finish downloading."
            assert prop(window, "startButton", "enabled") is False
            assert prop(window, "startBlockedText") == reason
            assert prop(window, "startBlockedText", "visible") is True

            backend.startPipeline()  # The guard behind the disabled button.
            assert prop(window, "msgOverlay", "visible") is True
            assert prop(window, "msgBody") == reason
            assert fake_pipeline.instances == []
            click_item(window, "msgCloseButton")

            server.release()
            wait_until(lambda: prop(window, "startButton", "enabled"))
            assert prop(window, "startBlockedText", "visible") is False


class TestSettingsSection:
    def test_lists_statuses_and_uses_shared_placeholders(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        install_fake_tools(tools_dir, server, ("yt-dlp", "deno"))
        fake_path(monkeypatch, {"ffmpeg", "ffprobe"})
        with tools_window(store, tools_dir, server) as (window, backend):
            wait_for_workers(backend)
            open_settings(window)
            ytdlp = ToolStore(tools_dir, server.specs).executable("yt-dlp")

            assert prop(window, "toolsSectionTitle") == "Runtime tools"
            assert prop(window, "toolStatus_yt-dlp") == f"Downloaded: {ytdlp}"
            assert prop(window, "toolStatus_ffmpeg") == "From PATH: /usr/bin/ffmpeg"
            assert prop(window, "ytdlpPathPlaceholder") == YTDLP_PATH_PLACEHOLDER
            assert prop(window, "ffmpegPathPlaceholder") == FFMPEG_PATH_PLACEHOLDER
            assert server.requests == []

    def test_verify_redownloads_a_tampered_executable(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        install_fake_tools(tools_dir, server)
        fake_path(monkeypatch)
        ffmpeg = ToolStore(tools_dir, server.specs).executable("ffmpeg")
        original = ffmpeg.read_bytes()
        with tools_window(store, tools_dir, server) as (window, backend):
            wait_for_workers(backend)
            assert server.requests == []
            open_settings(window)
            ffmpeg.write_bytes(b"tampered")

            server.hold()
            click_item(window, "toolsVerifyButton")
            wait_until(lambda: server.requests)
            for name in ("toolsDownloadButton", "toolsVerifyButton", "toolsOpenFolderButton"):
                assert prop(window, name, "enabled") is False

            server.release()
            wait_until(lambda: prop(window, "toolsVerifyButton", "enabled"))
            assert ffmpeg.read_bytes() == original
            assert server.requests == [server.specs["ffmpeg"].assets[0].url]
            assert prop(window, "toolStatus_ffmpeg") == f"Downloaded: {ffmpeg}"

    def test_download_missing_after_cancel_refreshes_the_list(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        fake_path(monkeypatch)
        server.hold()
        with tools_window(store, tools_dir, server) as (window, _backend):
            wait_until(lambda: server.requests)
            click_item(window, "toolsBannerButton")
            server.release()
            wait_until(lambda: prop(window, "toolsBannerButtonText") == "Download")

            open_settings(window)
            assert prop(window, "toolStatus_ffmpeg") == "Not downloaded yet"
            click_item(window, "toolsDownloadButton")
            wait_banner_gone(window)
            ffmpeg = ToolStore(tools_dir, server.specs).executable("ffmpeg")
            assert prop(window, "toolStatus_ffmpeg") == f"Downloaded: {ffmpeg}"

    def test_clearing_a_custom_ffmpeg_path_downloads_ffmpeg(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        install_fake_tools(tools_dir, server, ("yt-dlp", "deno"))
        fake_path(monkeypatch)
        AppSettings(store).ffmpeg_path = "/opt/ffmpeg"
        with tools_window(store, tools_dir, server) as (window, backend):
            wait_for_workers(backend)
            assert server.requests == []
            assert prop(window, "startBlockedText") == (
                "FFmpeg not found at '/opt/ffmpeg'. Fix the path in Settings."
            )

            open_settings(window)
            type_text(window, "ffmpegPathField", "")
            press_key(window, Qt.Key.Key_Return)

            wait_until(lambda: installed(tools_dir, server, ["ffmpeg"]))
            wait_banner_gone(window)
            assert server.requests == [server.specs["ffmpeg"].assets[0].url]
            assert prop(window, "startButton", "enabled") is True

    def test_open_folder_opens_the_tools_dir(
        self, qapp, server, store, tools_dir, monkeypatch
    ):
        install_fake_tools(tools_dir, server)
        fake_path(monkeypatch)
        opened = []

        class FakeDesktop:
            @staticmethod
            def openUrl(url):
                opened.append(url.toLocalFile())
                return True

        monkeypatch.setattr(tools_runner_module, "QDesktopServices", FakeDesktop)
        with tools_window(store, tools_dir, server) as (window, _backend):
            open_settings(window)
            click_item(window, "toolsOpenFolderButton")
            assert opened == [str(tools_dir)]

    def test_open_folder_disabled_without_a_tools_folder(self, qml_harness):
        window, _backend, _settings = qml_harness
        open_settings(window)
        assert find_item(window, "toolsOpenFolderButton").property("enabled") is False
