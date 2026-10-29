"""Runtime tool lookup, the first-run downloader and companion paths for yt-dlp."""

import io
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.youtube_bootlegger.core import tool_manifest, tools, ytdlp_metadata
from src.youtube_bootlegger.core.cancellation import CancelToken
from src.youtube_bootlegger.core.downloader import AudioDownloader
from src.youtube_bootlegger.core.exceptions import OperationCancelledError, ToolInstallError
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.splitter import AudioSplitter
from src.youtube_bootlegger.core.tool_installer import install_tools
from src.youtube_bootlegger.core.tool_manifest import ToolAsset, ToolSpec
from src.youtube_bootlegger.core.tools import ToolSource, ToolStore, default_tools_dir, exe_name
from tests.qml_support import DictBackend
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools


@pytest.fixture
def server(monkeypatch):
    return use_fake_tools(monkeypatch)


@pytest.fixture
def tools_dir(tmp_path):
    return tmp_path / "Data With Spaces" / "tools"


def settings_with(tools_dir) -> AppSettings:
    return AppSettings(DictBackend(), tools_dir=tools_dir)


# --- where downloads go -------------------------------------------------------


def test_linux_and_macos_use_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_tools_dir() == tmp_path / "youtube-bootlegger" / "tools"


def test_relative_xdg_data_home_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("XDG_DATA_HOME", "relative/dir")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_tools_dir() == tmp_path / ".local" / "share" / "youtube-bootlegger" / "tools"


def test_windows_uses_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_tools_dir() == tmp_path / "YouTubeBootlegger" / "tools"


def test_in_memory_settings_never_touch_the_real_folder():
    settings = AppSettings(DictBackend())
    assert settings.tools_dir is None
    assert all(not s.downloadable for s in settings.tool_statuses())


# --- the installer ----------------------------------------------------------------


def test_installs_only_whats_missing_and_reuses_past_downloads(server, tools_dir):
    store = ToolStore(tools_dir, server.specs)
    install_tools(["ffmpeg"], store, http_get=server.http_get)
    assert store.executable("ffmpeg").read_bytes() == b"fake ffmpeg 1.0"
    assert store.executable("ffprobe").parent == store.executable("ffmpeg").parent

    server.requests.clear()
    install_tools(["yt-dlp", "ffmpeg", "deno"], ToolStore(tools_dir, server.specs), http_get=server.http_get)
    assert [Path(u).name for u in server.requests] == ["yt-dlp-1.0.zip", "deno-1.0.zip"]

    server.requests.clear()
    install_tools(["yt-dlp", "ffmpeg", "deno"], ToolStore(tools_dir, server.specs), http_get=server.http_get)
    assert server.requests == []


def test_new_pin_downloads_again_and_removes_the_old_version(server, tools_dir):
    install_fake_tools(tools_dir, server, ["deno"])
    old = ToolStore(tools_dir, server.specs).executable("deno").parent
    server.set_version("2.0")
    store = ToolStore(tools_dir, server.specs)
    assert not store.is_installed("deno")
    install_tools(["deno"], store, http_get=server.http_get)
    assert store.executable("deno").read_bytes() == b"fake deno 2.0"
    assert not old.exists()


def test_checksum_mismatch_installs_nothing(server, tools_dir):
    url = server.specs["deno"].assets[0].url
    server.payloads[url] = server.payloads[url][:-1] + b"X"
    store = ToolStore(tools_dir, server.specs)
    with pytest.raises(ToolInstallError, match="corrupted"):
        install_tools(["deno"], store, http_get=server.http_get)
    assert not store.is_installed("deno")
    assert not list(tools_dir.glob(".staging-*"))


def test_network_error_is_reported(server, tools_dir):
    import urllib.error
    server.error = urllib.error.URLError("no route to host")
    with pytest.raises(ToolInstallError, match="Could not download Deno: no route to host"):
        install_tools(["deno"], ToolStore(tools_dir, server.specs), http_get=server.http_get)


def test_oversized_download_is_stopped(server, tools_dir):
    url = server.specs["deno"].assets[0].url
    server.payloads[url] += b"\0" * 10
    with pytest.raises(ToolInstallError, match="larger than expected"):
        install_tools(["deno"], ToolStore(tools_dir, server.specs), http_get=server.http_get)


def test_cancel_leaves_nothing_behind(server, tools_dir):
    cancel = CancelToken()
    store = ToolStore(tools_dir, server.specs)
    with pytest.raises(OperationCancelledError):
        install_tools(
            ["ffmpeg"], store, http_get=server.http_get, cancel=cancel,
            on_progress=lambda p: cancel.cancel(),
        )
    assert not store.is_installed("ffmpeg")
    assert not list(tools_dir.glob(".staging-*"))
    assert not (tools_dir / "ffmpeg").exists() or not any((tools_dir / "ffmpeg").iterdir())


def test_progress_covers_every_byte(server, tools_dir):
    seen = []
    install_tools(
        ["ffmpeg", "deno"], ToolStore(tools_dir, server.specs),
        http_get=server.http_get, on_progress=seen.append,
    )
    total = server.specs["ffmpeg"].download_size + server.specs["deno"].download_size
    assert {p.total_bytes for p in seen} == {total}
    assert seen[-1].done_bytes == total
    assert [p.label for p in seen] == ["FFmpeg", "Deno"]


def test_progress_is_reported_per_percent_not_per_chunk(server, tools_dir, monkeypatch):
    url = server.specs["deno"].assets[0].url
    monkeypatch.setattr("src.youtube_bootlegger.core.tool_installer.CHUNK_SIZE", 1)
    seen = []
    install_tools(
        ["deno"], ToolStore(tools_dir, server.specs),
        http_get=server.http_get, on_progress=seen.append,
    )
    assert len(server.payloads[url]) > 101  # more chunks than percent steps
    assert len(seen) <= 101
    assert seen[-1].done_bytes == seen[-1].total_bytes


def test_crashed_install_is_not_used_and_is_cleaned_up(server, tools_dir):
    store = ToolStore(tools_dir, server.specs)
    final = store.install_dir(server.specs["deno"])
    final.mkdir(parents=True)
    (final / exe_name("deno")).write_bytes(b"half")  # no installed.json marker
    (tools_dir / ".staging-deno-abc").mkdir()
    assert not store.is_installed("deno")
    install_tools(["deno"], store, http_get=server.http_get)
    assert store.executable("deno").read_bytes() == b"fake deno 1.0"
    assert not (tools_dir / ".staging-deno-abc").exists()


def test_verify_replaces_a_tampered_tool(server, tools_dir):
    install_fake_tools(tools_dir, server, ["ffmpeg"])
    store = ToolStore(tools_dir, server.specs)
    store.executable("ffprobe").write_bytes(b"tampered")
    install_tools(["ffmpeg"], store, http_get=server.http_get)
    assert server.requests == []  # without verify, it isn't re-checked

    install_tools(["ffmpeg"], store, verify=True, http_get=server.http_get)
    assert store.executable("ffprobe").read_bytes() == b"fake ffprobe 1.0"
    assert len(server.requests) == 1


def _zip(tmp_path, entries) -> Path:
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return archive


def _spec_for(archive: Path, files=("deno",)) -> tuple[ToolSpec, dict]:
    import hashlib
    data = archive.read_bytes()
    url = "https://example.invalid/x.zip"
    asset = ToolAsset(url, hashlib.sha256(data).hexdigest(), len(data), "zip", files)
    return ToolSpec("deno", "Deno", "1", ("deno",), (asset,)), {url: data}


def _serve(payloads):
    from contextlib import contextmanager

    @contextmanager
    def http_get(url):
        yield io.BytesIO(payloads[url])
    return http_get


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable names")
def test_archive_paths_cannot_escape_the_tools_folder(tmp_path, tools_dir):
    spec, payloads = _spec_for(_zip(tmp_path, [("../../deno", b"ok"), ("../../evil", b"no")]))
    store = ToolStore(tools_dir, {"deno": spec})
    install_tools(["deno"], store, http_get=_serve(payloads))
    assert store.executable("deno").read_bytes() == b"ok"
    assert not (tmp_path / "evil").exists()
    assert not (tools_dir.parent / "evil").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable names")
def test_ambiguous_archives_are_rejected(tmp_path, tools_dir):
    spec, payloads = _spec_for(_zip(tmp_path, [("a/deno", b"1"), ("b/deno", b"2")]))
    with pytest.raises(ToolInstallError, match="Expected one deno"):
        install_tools(["deno"], ToolStore(tools_dir, {"deno": spec}), http_get=_serve(payloads))


def test_no_tools_folder_is_an_error(server):
    with pytest.raises(ToolInstallError):
        install_tools(["deno"], ToolStore(None, server.specs), http_get=server.http_get)


# --- the manifest -----------------------------------------------------------------


@pytest.mark.parametrize("platform_key", tool_manifest.platform_keys())
def test_manifest_pins_every_tool(platform_key):
    specs = tool_manifest.tool_specs(platform_key)
    assert set(specs) == {"yt-dlp", "ffmpeg", "deno"}
    suffix = ".exe" if platform_key.startswith("windows") else ""
    for spec in specs.values():
        provided = {name for asset in spec.assets for name in asset.files}
        assert provided == {f"{name}{suffix}" for name in spec.executables}
        for asset in spec.assets:
            assert asset.url.startswith("https://")
            assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
            assert asset.size > 0 and asset.archive in ("raw", "zip")


def test_unsupported_platform_has_no_downloads():
    assert tool_manifest.tool_specs("plan9-mips") == {}


# --- lookup order -----------------------------------------------------------------


def _status(settings, tool_id):
    return next(s for s in settings.tool_statuses() if s.tool_id == tool_id)


def test_nothing_installed_and_nothing_on_path(server, tools_dir, monkeypatch):
    fake_path(monkeypatch)
    settings = settings_with(tools_dir)
    assert [s.needs_download for s in settings.tool_statuses()] == [True, True, True]
    assert settings.resolved_ffmpeg_command() == "ffmpeg"
    assert settings.resolved_ytdlp_command() == "yt-dlp"
    assert not settings.use_external_ytdlp


def test_ffmpeg_and_deno_on_path_save_the_download_but_ytdlp_does_not(server, tools_dir, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno", "yt-dlp"})
    settings = settings_with(tools_dir)
    assert _status(settings, "ffmpeg").source == ToolSource.SYSTEM
    assert not _status(settings, "ffmpeg").needs_download
    assert not _status(settings, "deno").needs_download
    ytdlp = _status(settings, "yt-dlp")
    assert ytdlp.source == ToolSource.SYSTEM and ytdlp.needs_download


def test_ffmpeg_without_ffprobe_on_path_is_missing(server, tools_dir, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg"})
    assert _status(settings_with(tools_dir), "ffmpeg").source == ToolSource.MISSING


@pytest.mark.parametrize("version,counts", [("deno 1.46.3 (stable)", False), ("deno 2.1.0", True)])
def test_deno_on_path_must_be_version_2(server, tools_dir, monkeypatch, version, counts):
    monkeypatch.setattr(shutil, "which", lambda cmd, *a, **k: "/opt/deno" if cmd == "deno" else None)
    monkeypatch.setattr(
        tools.subprocess, "run",
        MagicMock(return_value=subprocess.CompletedProcess([], 0, version + "\n", "")),
    )
    tools._deno_is_supported.cache_clear()
    try:
        assert _status(settings_with(tools_dir), "deno").needs_download is not counts
    finally:
        tools._deno_is_supported.cache_clear()


def test_downloaded_tools_win_over_path_and_custom_paths_win_over_both(server, tools_dir, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno", "yt-dlp"})
    install_fake_tools(tools_dir, server)
    settings = settings_with(tools_dir)
    store = settings.tool_store
    assert all(s.source == ToolSource.DOWNLOADED for s in settings.tool_statuses())
    assert settings.use_external_ytdlp  # downloaded yt-dlp becomes the default
    assert settings.resolved_ytdlp_command() == str(store.executable("yt-dlp"))
    assert AudioSplitter(settings=settings)._ffmpeg_command == str(store.executable("ffmpeg"))

    settings.ytdlp_path = "/custom/yt-dlp"
    settings.ffmpeg_path = "/custom/ffmpeg"
    assert settings.resolved_ytdlp_command() == "/custom/yt-dlp"
    assert settings.resolved_ffmpeg_command() == "/custom/ffmpeg"
    assert _status(settings, "ffmpeg").source == ToolSource.CUSTOM


def test_explicit_library_preference_is_kept(server, tools_dir):
    install_fake_tools(tools_dir, server)
    settings = settings_with(tools_dir)
    settings.use_external_ytdlp = False
    assert not settings.use_external_ytdlp


# --- companion paths passed to yt-dlp --------------------------------------------


@pytest.fixture
def installed(server, tools_dir, monkeypatch):
    fake_path(monkeypatch)
    install_fake_tools(tools_dir, server)
    return settings_with(tools_dir)


def test_custom_ytdlp_is_not_given_js_runtimes(installed):
    """An older user-chosen yt-dlp would reject --js-runtimes and fail every run."""
    installed.ytdlp_path = "/old/yt-dlp"
    args = installed.ytdlp_tool_cli_args()
    assert "--js-runtimes" not in args
    assert "--ffmpeg-location" in args


def test_metadata_library_gets_companion_paths(installed, monkeypatch):
    installed.use_external_ytdlp = False
    ydl = MagicMock()
    ydl.return_value.__enter__.return_value.extract_info.return_value = {"id": "abc"}
    monkeypatch.setattr(ytdlp_metadata.yt_dlp, "YoutubeDL", ydl)
    assert ytdlp_metadata.fetch_info_dict("https://youtu.be/abc", installed)["id"] == "abc"
    options = ydl.call_args.args[0]
    store = installed.tool_store
    assert options["ffmpeg_location"] == str(store.executable("ffmpeg"))
    assert options["js_runtimes"] == {"deno": {"path": str(store.executable("deno"))}}


def test_metadata_cli_gets_companion_paths(installed, monkeypatch):
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, '{"id":"abc"}', ""))
    monkeypatch.setattr(ytdlp_metadata.subprocess, "run", run)
    ytdlp_metadata.fetch_info_dict("https://youtu.be/abc", installed, comment_limit=2)
    args = run.call_args.args[0]
    store = installed.tool_store
    assert args[0] == str(store.executable("yt-dlp"))
    assert args[args.index("--js-runtimes") + 1] == f"deno:{store.executable('deno')}"
    assert args[args.index("--ffmpeg-location") + 1] == str(store.executable("ffmpeg"))
    assert "--ignore-config" in args


def test_download_cli_gets_companion_paths(installed, tmp_path, monkeypatch):
    (tmp_path / "song.mp3").touch()
    process = MagicMock(stdout=io.StringIO(""))
    process.wait.return_value = 0
    popen = MagicMock(return_value=process)
    monkeypatch.setattr("src.youtube_bootlegger.core.cancellation.subprocess.Popen", popen)
    AudioDownloader(output_dir=tmp_path, settings=installed).download("https://youtu.be/abc")
    args = popen.call_args.args[0]
    store = installed.tool_store
    assert args[0] == str(store.executable("yt-dlp"))
    assert args[args.index("--js-runtimes") + 1] == f"deno:{store.executable('deno')}"


# --- the real downloads (network) ---------------------------------------------


@pytest.mark.e2e
@pytest.mark.skipif(
    not __import__("os").environ.get("RUNTIME_TOOLS_E2E"),
    reason="Set RUNTIME_TOOLS_E2E=1 to download the real pinned tools",
)
@pytest.mark.skipif(tool_manifest.current_platform() is None, reason="No downloads for this platform")
def test_real_tools_download_and_run(tmp_path, monkeypatch):
    tools_dir = tmp_path / "Data With Spaces" / "tools"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    settings = settings_with(tools_dir)
    install_tools(["yt-dlp", "ffmpeg", "deno"], settings.tool_store)
    assert all(s.source == ToolSource.DOWNLOADED for s in settings.tool_statuses())
    store = settings.tool_store

    audio = tmp_path / "tone.mp3"
    subprocess.run([
        settings.resolved_ffmpeg_command(), "-nostdin", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=0.1", "-c:a", "libmp3lame", str(audio),
    ], check=True, capture_output=True, timeout=60)
    probe = subprocess.run([
        str(store.executable("ffprobe")), "-v", "error", "-show_format", "-of", "json", str(audio),
    ], check=True, capture_output=True, text=True, timeout=60)
    assert float(json.loads(probe.stdout)["format"]["duration"]) > 0

    extraction = subprocess.run([
        settings.resolved_ytdlp_command(), "--ignore-config", *settings.ytdlp_tool_cli_args(),
        "--verbose", "--enable-file-urls", "--skip-download", "--simulate", audio.as_uri(),
    ], check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
    # yt-dlp really detects the companions, not just accepts the flags.
    assert "JS runtimes: deno-" in extraction.stderr
    assert "exe versions: ffmpeg " in extraction.stderr
    assert "ffprobe " in extraction.stderr
    deno = subprocess.run([
        str(store.executable("deno")), "eval", "console.log(1 + 1)",
    ], check=True, capture_output=True, text=True, timeout=60)
    assert deno.stdout.strip() == "2"

    for tool_id in ("yt-dlp", "ffmpeg", "deno"):
        assert store.verify(tool_id)
