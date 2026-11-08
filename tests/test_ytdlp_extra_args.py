"""Extra yt-dlp options from Settings, and when yt-dlp config files are read."""

import io
import subprocess
from unittest.mock import MagicMock

import pytest

from src.youtube_bootlegger.app_logic import fetch_config, should_refetch_video_info
from src.youtube_bootlegger.core import ytdlp_metadata
from src.youtube_bootlegger.core.downloader import AudioDownloader
from src.youtube_bootlegger.core.exceptions import DownloadError, ValidationError
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.ytdlp_extra_args import parse_extra_args, youtube_extractor_args
from tests.qml_support import DictBackend
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools

URL = "https://youtu.be/abc"


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """Every tool downloaded."""
    fake_path(monkeypatch)
    tools_dir = tmp_path / "tools"
    install_fake_tools(tools_dir, use_fake_tools(monkeypatch))
    settings = AppSettings(DictBackend(), tools_dir=tools_dir)
    return settings


def run_external_download(settings, tmp_path, monkeypatch) -> list[str]:
    (tmp_path / "song.mp3").touch()
    process = MagicMock(stdout=io.StringIO(""))
    process.wait.return_value = 0
    popen = MagicMock(return_value=process)
    monkeypatch.setattr("src.youtube_bootlegger.core.cancellation.subprocess.Popen", popen)
    AudioDownloader(output_dir=tmp_path, settings=settings).download(URL)
    return popen.call_args.args[0]


def run_external_metadata(settings, monkeypatch, comment_limit=0) -> list[str]:
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, '{"id":"abc"}', ""))
    monkeypatch.setattr(ytdlp_metadata.subprocess, "run", run)
    ytdlp_metadata.fetch_info_dict(URL, settings, comment_limit=comment_limit)
    return run.call_args.args[0]


# --- checking what the user typed ----------------------------------------------


def test_options_become_command_line_arguments():
    args = parse_extra_args("--proxy socks5://127.0.0.1:9050  --limit-rate 2M")
    assert args == ["--proxy", "socks5://127.0.0.1:9050", "--limit-rate", "2M"]


def test_windows_paths_keep_their_backslashes():
    args = parse_extra_args(r'--cookies C:\Users\Me\cookies.txt --cache-dir "D:\My cache"')
    assert args == ["--cookies", r"C:\Users\Me\cookies.txt", "--cache-dir", r"D:\My cache"]


def test_empty_text_adds_nothing():
    assert parse_extra_args("   ") == []


@pytest.mark.parametrize("video", [
    "youtu.be/dQw4w9WgXcQ", "www.youtube.com/watch?v=dQw4w9WgXcQ",
    "youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ",
])
def test_extra_video_arguments_are_rejected(video):
    for text in (video, f"--limit-rate 2M {video}", f"--no-playlist {video}", f"-v {video}"):
        with pytest.raises(ValidationError, match="only options, no video URLs"):
            parse_extra_args(text)


def test_video_id_shaped_option_values_are_kept():
    assert parse_extra_args("--username dQw4w9WgXcQ") == ["--username", "dQw4w9WgXcQ"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('--proxy "socks5://x', "Extra yt-dlp options: a quote is not closed."),
        (f"--proxy socks5://x:1 {URL}", f"Extra yt-dlp options: only options, no video URLs ('{URL}')."),
        (URL, f"Extra yt-dlp options: only options, no video URLs ('{URL}')."),
        (f"--no-playlist {URL}", f"Extra yt-dlp options: only options, no video URLs ('{URL}')."),
        ("--proxy socks5://x:1 -o out.mp3", "Extra yt-dlp options: '-o' can't be used: the app sets this itself."),
        ("--exec 'rm x'", "Extra yt-dlp options: '--exec' can't be used: the app sets this itself."),
        ("-x", "Extra yt-dlp options: '-x' can't be used: the app sets this itself."),
        ("-ofile.mp3", "Extra yt-dlp options: '-o' can't be used: the app sets this itself."),
        ("--print=title", "Extra yt-dlp options: '--print' can't be used: the app sets this itself."),
        ("--print title", "Extra yt-dlp options: '--print' can't be used: the app sets this itself."),
        ("--download-archive seen.txt", "Extra yt-dlp options: '--download-archive' can't be used: the app sets this itself."),
        ("--ffmpeg-location /opt/ffmpeg", "Extra yt-dlp options: '--ffmpeg-location' can't be used: set the ffmpeg path instead."),
        ("--cookies-from-browser firefox", "Extra yt-dlp options: '--cookies-from-browser' can't be used: use the Browser cookies setting instead."),
        ("--update", "Extra yt-dlp options: '--update' can't be used here."),
        ("--config-locations=/etc/x", "Extra yt-dlp options: '--config-locations=/etc/x' can't be used here."),
    ],
)
def test_rejected_options_name_the_culprit(text, message):
    with pytest.raises(ValidationError) as error:
        parse_extra_args(text)
    assert str(error.value) == message


@pytest.mark.parametrize("text", ["--help", "--version", "-hv", "-U"])
def test_help_version_and_update_are_refused(text):
    with pytest.raises(ValidationError, match="can't be used here"):
        parse_extra_args(text)


def test_proxy_urls_are_option_values_not_videos():
    assert parse_extra_args("--proxy http://127.0.0.1:8080") == ["--proxy", "http://127.0.0.1:8080"]


def test_youtube_extractor_args_are_read_as_ytdlp_reads_them():
    args = parse_extra_args(
        "--extractor-args youtube:player-client=web,tv;lang=en "
        "--extractor-args=generic:impersonate --extractor-args YouTube:po_token=a\\,b"
    )
    assert youtube_extractor_args(args) == {"po_token": ["a,b"]}  # the last set wins
    assert youtube_extractor_args(args[:2]) == {"player_client": ["web", "tv"], "lang": ["en"]}


def test_rejected_text_is_not_stored():
    settings = AppSettings(DictBackend())
    settings.ytdlp_extra_args = "  --limit-rate 1M "
    with pytest.raises(ValidationError):
        settings.ytdlp_extra_args = "-o out.mp3"
    assert settings.ytdlp_extra_args == "--limit-rate 1M"


def test_changing_them_retries_a_failed_video_lookup():
    settings = AppSettings(DictBackend())
    before = fetch_config(settings)
    settings.ytdlp_extra_args = "--proxy socks5://127.0.0.1:9050"
    assert should_refetch_video_info(before, fetch_config(settings), None, URL)


# --- what yt-dlp gets ----------------------------------------------------------


def test_downloaded_ytdlp_ignores_config_files_and_gets_the_extras(installed, tmp_path, monkeypatch):
    installed.ytdlp_extra_args = "--proxy socks5://127.0.0.1:9050"
    for args in (
        run_external_download(installed, tmp_path, monkeypatch),
        run_external_metadata(installed, monkeypatch),
    ):
        assert args[0] == str(installed.tool_store.executable("yt-dlp"))
        assert args[1:4] == ["--ignore-config", "--proxy", "socks5://127.0.0.1:9050"]


def test_own_ytdlp_reads_its_config_files(installed, tmp_path, monkeypatch):
    installed.ytdlp_path = "/opt/yt-dlp"
    installed.ytdlp_extra_args = "--limit-rate 2M"
    for args in (
        run_external_download(installed, tmp_path, monkeypatch),
        run_external_metadata(installed, monkeypatch),
    ):
        assert args[:3] == ["/opt/yt-dlp", "--limit-rate", "2M"]
        assert "--ignore-config" not in args


def test_comment_lookup_keeps_the_users_youtube_extractor_args(installed, monkeypatch):
    installed.ytdlp_extra_args = "--extractor-args youtube:player_client=web,tv"
    args = run_external_metadata(installed, monkeypatch, comment_limit=5)
    assert args[args.index("--extractor-args", 4) + 1] == (
        "youtube:player_client=web,tv;comment_sort=top;max_comments=5,5,0,0"
    )


YTDLP_USAGE_ERROR = (
    "Usage: yt-dlp [OPTIONS] URL [URL...]\n\n"
    "yt-dlp: error: no such option: --no-such-option\n"
)


def test_an_option_ytdlp_rejects_is_reported_by_name_when_downloading(installed, tmp_path, monkeypatch):
    installed.ytdlp_extra_args = "--no-such-option"  # only yt-dlp knows its options
    process = MagicMock(stdout=io.StringIO(YTDLP_USAGE_ERROR))
    process.wait.return_value = 2
    monkeypatch.setattr(
        "src.youtube_bootlegger.core.cancellation.subprocess.Popen", MagicMock(return_value=process)
    )
    with pytest.raises(DownloadError) as error:
        AudioDownloader(output_dir=tmp_path, settings=installed).download(URL)
    assert str(error.value) == "Extra yt-dlp options: no such option: --no-such-option."


def test_an_option_ytdlp_rejects_is_reported_by_name_when_fetching(installed, monkeypatch):
    installed.ytdlp_extra_args = "--no-such-option"
    run = MagicMock(return_value=subprocess.CompletedProcess([], 2, "", YTDLP_USAGE_ERROR))
    monkeypatch.setattr(ytdlp_metadata.subprocess, "run", run)
    with pytest.raises(ValidationError) as error:
        ytdlp_metadata.fetch_info_dict(URL, installed)
    assert str(error.value) == "Extra yt-dlp options: no such option: --no-such-option."
