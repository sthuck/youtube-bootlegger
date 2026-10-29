"""RuntimeToolsSession: what every front-end shows and decides about tool downloads."""

import pytest

from src.youtube_bootlegger.app_logic.runtime_tools import (
    BannerAction,
    RuntimeToolsSession,
    ToolsPhase,
    status_text,
)
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.tool_installer import InstallProgress, install_tools
from tests.qml_support import DictBackend
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools


@pytest.fixture
def server(monkeypatch):
    return use_fake_tools(monkeypatch)


@pytest.fixture
def settings(tmp_path):
    return AppSettings(DictBackend(), tools_dir=tmp_path / "tools")


def run_download(session, settings, server, ids):
    install_tools(ids, settings.tool_store, http_get=server.http_get, on_progress=session.on_progress)
    session.on_finished()


def test_first_start_downloads_everything_missing_once(server, settings, monkeypatch):
    fake_path(monkeypatch)
    session = RuntimeToolsSession(settings)
    ids = session.auto_download_ids()
    assert ids == ["yt-dlp", "ffmpeg", "deno"]
    assert session.downloading
    assert session.auto_download_ids() == []  # no second download while one runs

    banner = session.banner()
    assert banner.action == BannerAction.CANCEL and banner.text == "Preparing tool download…"
    assert session.start_blocked_reason() == "Wait for FFmpeg to finish downloading."

    run_download(session, settings, server, ids)
    assert session.phase == ToolsPhase.IDLE
    assert not session.banner().visible
    assert session.start_blocked_reason() is None
    assert session.auto_download_ids() == []  # a restart finds the past download


def test_only_ytdlp_is_fetched_when_ffmpeg_and_deno_are_on_path(server, settings, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno", "yt-dlp"})
    session = RuntimeToolsSession(settings)
    assert session.auto_download_ids() == ["yt-dlp"]
    assert session.start_blocked_reason() is None  # PATH FFmpeg works meanwhile


def test_progress_text(server, settings, monkeypatch):
    fake_path(monkeypatch)
    session = RuntimeToolsSession(settings)
    session.start()
    session.on_progress(InstallProgress("FFmpeg", 45_000_000, 180_000_000))
    banner = session.banner()
    assert banner.text == "Downloading FFmpeg… 45 MB of 180 MB (25%)"
    assert banner.progress == pytest.approx(0.25)


def test_cancel_waits_for_the_user_to_download_again(server, settings, monkeypatch):
    fake_path(monkeypatch)
    session = RuntimeToolsSession(settings)
    session.auto_download_ids()
    session.on_cancelled()
    assert session.auto_download_ids() == []  # saving Settings doesn't restart it
    banner = session.banner()
    assert banner.action == BannerAction.DOWNLOAD and banner.action_label == "Download"
    assert banner.text.startswith("Download cancelled. yt-dlp, FFmpeg and Deno need a one-time download")
    assert session.start_blocked_reason() == "FFmpeg not downloaded yet. Use Download in the banner."
    assert session.start() == ["yt-dlp", "ffmpeg", "deno"]


def test_failure_offers_retry(server, settings, monkeypatch):
    fake_path(monkeypatch)
    session = RuntimeToolsSession(settings)
    session.auto_download_ids()
    session.on_failed("Could not download FFmpeg: timed out")
    banner = session.banner()
    assert banner.is_error and banner.action_label == "Retry"
    assert banner.text == "Tool download failed: Could not download FFmpeg: timed out"
    assert session.auto_download_ids() == []
    assert session.start() == ["yt-dlp", "ffmpeg", "deno"]


def test_settings_change_that_needs_a_tool_starts_a_download(server, settings, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
    install_fake_tools(settings.tools_dir, server, ["yt-dlp"])
    session = RuntimeToolsSession(settings)
    assert session.auto_download_ids() == []
    fake_path(monkeypatch, {"deno"})  # e.g. FFmpeg uninstalled from the system
    assert session.auto_download_ids() == ["ffmpeg"]


def test_verify_includes_downloaded_tools(server, settings, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
    install_fake_tools(settings.tools_dir, server, ["yt-dlp"])
    session = RuntimeToolsSession(settings)
    assert session.start() == []
    assert session.start(verify=True) == ["yt-dlp"]


def test_custom_ffmpeg_path_that_does_not_exist_blocks_start(server, settings, monkeypatch, tmp_path):
    fake_path(monkeypatch)
    install_fake_tools(settings.tools_dir, server)
    settings.ffmpeg_path = str(tmp_path / "nope" / "ffmpeg")
    session = RuntimeToolsSession(settings)
    assert session.start_blocked_reason() == (
        f"FFmpeg not found at '{tmp_path / 'nope' / 'ffmpeg'}'. Fix the path in Settings."
    )


def test_external_mode_needs_ytdlp(server, settings, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe"})
    settings.use_external_ytdlp = True
    session = RuntimeToolsSession(settings)
    session.start()
    assert session.start_blocked_reason() == "Wait for yt-dlp to finish downloading."


def test_no_download_for_this_platform(monkeypatch):
    fake_path(monkeypatch)
    session = RuntimeToolsSession(AppSettings(DictBackend()))  # nowhere to download to
    assert session.auto_download_ids() == []
    banner = session.banner()
    assert banner.is_error and banner.action == BannerAction.NONE
    assert banner.text.startswith("FFmpeg can't be downloaded on this platform.")
    assert session.start_blocked_reason() == "FFmpeg not found. Install it, or set its path in Settings."


def test_status_lines(server, settings, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "yt-dlp"})
    by_id = {s.tool_id: status_text(s) for s in settings.tool_statuses()}
    assert by_id == {
        "yt-dlp": "Using /usr/bin/yt-dlp until the download finishes",
        "ffmpeg": "From PATH: /usr/bin/ffmpeg",
        "deno": "Not downloaded yet",
    }
