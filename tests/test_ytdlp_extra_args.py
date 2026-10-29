"""Extra yt-dlp options from Settings, and when yt-dlp config files are read."""

import io
import subprocess
from unittest.mock import MagicMock

import pytest
import yt_dlp

from src.youtube_bootlegger.app_logic import fetch_config, should_refetch_video_info
from src.youtube_bootlegger.core import ytdlp_metadata
from src.youtube_bootlegger.core.downloader import AudioDownloader
from src.youtube_bootlegger.core.exceptions import ValidationError
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.ytdlp_extra_args import parse_extra_args
from tests.qml_support import DictBackend
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools

URL = "https://youtu.be/abc"


@pytest.fixture
def installed(tmp_path, monkeypatch):
    """Every tool downloaded; yt-dlp runs as an external program."""
    fake_path(monkeypatch)
    tools_dir = tmp_path / "tools"
    install_fake_tools(tools_dir, use_fake_tools(monkeypatch))
    settings = AppSettings(DictBackend(), tools_dir=tools_dir)
    settings.use_external_ytdlp = True
    return settings


def fake_youtube_dl(info) -> MagicMock:
    """A YoutubeDL double; yt-dlp's option parser still needs its validate_outtmpl."""
    ydl = MagicMock()
    ydl.validate_outtmpl = yt_dlp.YoutubeDL.validate_outtmpl
    ydl.return_value.__enter__.return_value.extract_info.return_value = info
    return ydl


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


def test_options_become_python_api_options_too():
    args, options = parse_extra_args("--proxy socks5://127.0.0.1:9050  --limit-rate 2M")
    assert args == ["--proxy", "socks5://127.0.0.1:9050", "--limit-rate", "2M"]
    assert options == {"proxy": "socks5://127.0.0.1:9050", "ratelimit": 2 * 1024 * 1024}


def test_windows_paths_keep_their_backslashes():
    args, _options = parse_extra_args(r'--cookies C:\Users\Me\cookies.txt --cache-dir "D:\My cache"')
    assert args == ["--cookies", r"C:\Users\Me\cookies.txt", "--cache-dir", r"D:\My cache"]


def test_empty_text_adds_nothing():
    assert parse_extra_args("   ") == ([], {})


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("--bogus", "Extra yt-dlp options: no such option: --bogus."),
        ("--limit-rate", "Extra yt-dlp options: --limit-rate option requires 1 argument."),
        ('--proxy "socks5://x', "Extra yt-dlp options: a quote is not closed."),
        (f"--proxy socks5://x:1 {URL}", f"Extra yt-dlp options: only options, no video URLs ('{URL}')."),
        ("--proxy socks5://x:1 -o out.mp3", "Extra yt-dlp options: '-o' can't be used: the app sets this itself."),
        ("--exec 'rm x'", "Extra yt-dlp options: '--exec' can't be used: the app sets this itself."),
        ("-x", "Extra yt-dlp options: '-x' can't be used: the app sets this itself."),
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


def test_help_and_version_print_nothing(capsys):
    for text in ("--help", "--version", "-hv"):
        with pytest.raises(ValidationError):
            parse_extra_args(text)
    assert capsys.readouterr() == ("", "")


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

    installed.use_external_ytdlp = False
    ydl = fake_youtube_dl({"id": "abc"})
    monkeypatch.setattr(ytdlp_metadata.yt_dlp, "YoutubeDL", ydl)
    ytdlp_metadata.fetch_info_dict(URL, installed, comment_limit=5)
    assert ydl.call_args.args[0]["extractor_args"] == {"youtube": {
        "player_client": ["web", "tv"],
        "comment_sort": ["top"],
        "max_comments": ["5", "5", "0", "0"],
    }}


def test_library_mode_gets_the_extras_but_keeps_its_own_format(installed, tmp_path, monkeypatch):
    installed.use_external_ytdlp = False
    installed.ytdlp_extra_args = "--proxy socks5://127.0.0.1:9050 -S abr"
    (tmp_path / "song.mp3").touch()
    ydl = fake_youtube_dl({"id": "abc"})
    ydl.return_value.__enter__.return_value.prepare_filename.return_value = str(tmp_path / "song.webm")
    monkeypatch.setattr("src.youtube_bootlegger.core.downloader.yt_dlp.YoutubeDL", ydl)
    AudioDownloader(output_dir=tmp_path, settings=installed).download(URL)
    options = ydl.call_args.args[0]
    assert options["proxy"] == "socks5://127.0.0.1:9050"
    assert options["format_sort"] == ["abr"]
    assert options["format"] == "bestaudio/best"


def test_a_stored_value_yt_dlp_now_rejects_stops_with_its_reason(installed, tmp_path, monkeypatch):
    installed._backend.setValue("ytdlp/extra_args", "--no-such-option")  # e.g. edited by hand
    with pytest.raises(ValidationError, match="no such option: --no-such-option"):
        run_external_download(installed, tmp_path, monkeypatch)
