"""Release executable discovery and companion-path integration."""

import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.bundle_tools import extract_asset, verify
from src.youtube_bootlegger.core import tools, ytdlp_metadata
from src.youtube_bootlegger.core.downloader import AudioDownloader
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.splitter import AudioSplitter


class MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


@pytest.fixture
def installation(tmp_path, monkeypatch):
    root = tmp_path / "Installed App With Spaces"
    root.mkdir()
    monkeypatch.setattr(sys, "argv", [str(root / "YouTubeBootlegger")])
    directory = root / "tools"
    directory.mkdir()
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno"):
        path = directory / (name + suffix)
        path.write_bytes(b"test executable")
        path.chmod(0o755)
    return directory


def test_discovery_is_independent_of_working_and_extraction_directories(installation, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tools, "__file__", str(tmp_path / "onefile-extracted" / "tools.py"))
    assert tools.bundled_tools_dir() == installation
    settings = AppSettings(MemorySettings())
    assert settings.use_external_ytdlp
    assert settings.resolved_ytdlp_command() == str(tools.bundled_tool("yt-dlp"))
    assert AudioSplitter(settings=settings)._ffmpeg_command == str(tools.bundled_tool("ffmpeg"))


def test_custom_paths_and_explicit_library_preference_are_preserved(installation):
    settings = AppSettings(MemorySettings())
    settings.use_external_ytdlp = False
    settings.ytdlp_path = "/custom/yt-dlp"
    settings.ffmpeg_path = "/custom/ffmpeg"
    assert not settings.use_external_ytdlp
    assert settings.resolved_ytdlp_command() == "/custom/yt-dlp"
    assert settings.resolved_ffmpeg_command() == "/custom/ffmpeg"
    assert settings.ytdlp_tool_options()["ffmpeg_location"] == "/custom/ffmpeg"


@pytest.mark.parametrize("platform,suffix", [("linux", ""), ("win32", ".exe"), ("darwin", "")])
def test_native_layouts(tmp_path, monkeypatch, platform, suffix):
    root = tmp_path / "Install"
    if platform == "darwin":
        executable = root / "Bootlegger.app" / "Contents" / "MacOS" / "main"
        directory = executable.parent.parent / "Resources" / "tools"
    else:
        executable = root / ("Bootlegger" + suffix)
        directory = root / "tools"
    directory.mkdir(parents=True)
    deno = directory / ("deno" + suffix)
    deno.touch(mode=0o755)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "argv", [str(executable)])
    assert tools.bundled_tool("deno") == deno


def test_missing_bundle_uses_path_and_library(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
    settings = AppSettings(MemorySettings())
    assert not settings.use_external_ytdlp
    assert settings.resolved_ffmpeg_command() == "ffmpeg"
    assert settings.resolved_ytdlp_command() == "yt-dlp"
    assert settings.ytdlp_tool_cli_args() == ["--encoding", "utf-8"]


def test_metadata_library_gets_companion_paths(installation, monkeypatch):
    settings = AppSettings(MemorySettings())
    settings.use_external_ytdlp = False
    ydl = MagicMock()
    ydl.return_value.__enter__.return_value.extract_info.return_value = {"id": "abc"}
    monkeypatch.setattr(ytdlp_metadata.yt_dlp, "YoutubeDL", ydl)
    assert ytdlp_metadata.fetch_info_dict("https://youtu.be/abc", settings)["id"] == "abc"
    options = ydl.call_args.args[0]
    assert options["ffmpeg_location"] == str(tools.bundled_tool("ffmpeg"))
    assert options["js_runtimes"] == {"deno": {"path": str(tools.bundled_tool("deno"))}}


def test_metadata_cli_gets_companion_paths(installation, monkeypatch):
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, '{"id":"abc"}', ""))
    monkeypatch.setattr(ytdlp_metadata.subprocess, "run", run)
    settings = AppSettings(MemorySettings())
    ytdlp_metadata.fetch_info_dict("https://youtu.be/abc", settings, comment_limit=2)
    args = run.call_args.args[0]
    assert args[0] == settings.resolved_ytdlp_command()
    assert args[args.index("--js-runtimes") + 1] == f"deno:{tools.bundled_tool('deno')}"
    assert args[args.index("--ffmpeg-location") + 1] == str(tools.bundled_tool("ffmpeg"))
    assert "--ignore-config" in args
    assert "--write-comments" in args


def test_download_cli_gets_companion_paths(installation, tmp_path, monkeypatch):
    (tmp_path / "song.mp3").touch()
    process = MagicMock(stdout=io.StringIO(""))
    process.wait.return_value = 0
    popen = MagicMock(return_value=process)
    monkeypatch.setattr("src.youtube_bootlegger.core.cancellation.subprocess.Popen", popen)
    settings = AppSettings(MemorySettings())
    AudioDownloader(output_dir=tmp_path, settings=settings).download("https://youtu.be/abc")
    args = popen.call_args.args[0]
    assert args[0] == settings.resolved_ytdlp_command()
    assert args[args.index("--js-runtimes") + 1] == f"deno:{tools.bundled_tool('deno')}"
    assert args[args.index("--ffmpeg-location") + 1] == str(tools.bundled_tool("ffmpeg"))


def test_archive_copy_cannot_escape_destination(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../../deno", b"expected contents")
        z.writestr("../../unexpected", b"unexpected contents")
    destination = tmp_path / "tools"
    destination.mkdir()
    extract_asset(archive, {"archive": "zip", "files": ["deno"]}, destination)
    assert (destination / "deno").read_bytes() == b"expected contents"
    assert not (tmp_path / "unexpected").exists()


def test_duplicate_archive_executables_are_rejected(tmp_path):
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("one/deno", b"a")
        z.writestr("two/deno", b"b")
    with pytest.raises(ValueError, match="one regular"):
        extract_asset(archive, {"archive": "zip", "files": ["deno"]}, tmp_path)


def test_checksum_mismatch_is_rejected(tmp_path):
    path = tmp_path / "binary"
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify(path, "0" * 64)


@pytest.mark.skipif(not os.environ.get("BUNDLED_TOOLS_DIR"), reason="Native release tools not downloaded")
def test_native_tools_without_path(tmp_path, monkeypatch):
    directory = Path(os.environ["BUNDLED_TOOLS_DIR"]).resolve()
    monkeypatch.setattr(sys, "argv", [str(directory.parent / "YouTubeBootlegger")])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    settings = AppSettings(MemorySettings())
    assert settings.use_external_ytdlp
    assert Path(settings.resolved_ytdlp_command()).parent == directory
    audio = tmp_path / "tone.mp3"
    subprocess.run([
        settings.resolved_ffmpeg_command(), "-nostdin", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=0.1", "-c:a", "libmp3lame", str(audio),
    ], check=True, capture_output=True, timeout=30)
    suffix = ".exe" if sys.platform == "win32" else ""
    probe = subprocess.run([
        str(directory / ("ffprobe" + suffix)), "-v", "error", "-show_format", "-of", "json", str(audio),
    ], check=True, capture_output=True, text=True, timeout=30)
    assert float(json.loads(probe.stdout)["format"]["duration"]) > 0
    subprocess.run([
        settings.resolved_ytdlp_command(), "--ignore-config", *settings.ytdlp_tool_cli_args(),
        "--list-extractors",
    ], check=True, capture_output=True, timeout=30)
    deno = subprocess.run([
        str(directory / ("deno" + suffix)), "eval", "console.log(1 + 1)",
    ], check=True, capture_output=True, text=True, timeout=30)
    assert deno.stdout.strip() == "2"
