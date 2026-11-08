"""Unit tests for AudioDownloader helper logic (no network/subprocess calls)."""

import tempfile
import time
from pathlib import Path

from src.youtube_bootlegger.core.downloader import AudioDownloader
from src.youtube_bootlegger.core.settings import AppSettings


class FakeSettingsBackend:
    """In-memory stand-in for QSettings, avoiding disk I/O in tests."""

    def __init__(self):
        self._data = {}

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, value):
        self._data[key] = value

    def sync(self):
        pass


def make_settings(ytdlp_path="", ffmpeg_path=""):
    settings = AppSettings(FakeSettingsBackend())
    settings.ytdlp_path = ytdlp_path
    settings.ffmpeg_path = ffmpeg_path
    return settings


class TestLatestOutputFile:
    """Tests for AudioDownloader._latest_output_file."""

    def test_returns_none_when_no_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AudioDownloader(output_dir=Path(tmpdir), settings=make_settings())
            assert downloader._latest_output_file() is None

    def test_returns_only_mp3_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / "song.mp3").write_bytes(b"data")
            (output_dir / "notes.txt").write_text("ignore me")

            downloader = AudioDownloader(output_dir=output_dir, settings=make_settings())
            result = downloader._latest_output_file()

            assert result == output_dir / "song.mp3"

    def test_returns_most_recently_modified_mp3(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            older = output_dir / "older.mp3"
            newer = output_dir / "newer.mp3"
            older.write_bytes(b"old")
            time.sleep(0.01)
            newer.write_bytes(b"new")

            downloader = AudioDownloader(output_dir=output_dir, settings=make_settings())
            result = downloader._latest_output_file()

            assert result == newer


class TestReportExternalProgress:
    """Tests for AudioDownloader._report_external_progress."""

    def test_parses_percent_from_download_line(self):
        received = []
        downloader = AudioDownloader(
            progress_callback=lambda percent, message: received.append((percent, message)),
            settings=make_settings(),
        )

        downloader._report_external_progress("[download]  45.2% of ~10.00MiB at 1.02MiB/s ETA 00:05")

        assert received == [(45.2, "Downloading...")]

    def test_ignores_non_progress_lines(self):
        received = []
        downloader = AudioDownloader(
            progress_callback=lambda percent, message: received.append((percent, message)),
            settings=make_settings(),
        )

        downloader._report_external_progress("[ExtractAudio] Destination: song.mp3")

        assert received == []

    def test_skips_small_percent_increments(self):
        received = []
        downloader = AudioDownloader(
            progress_callback=lambda percent, message: received.append((percent, message)),
            settings=make_settings(),
        )

        downloader._report_external_progress("[download]  10.0% of ~10.00MiB")
        downloader._report_external_progress("[download]  10.3% of ~10.00MiB")

        assert received == [(10.0, "Downloading...")]

    def test_noop_without_progress_callback(self):
        downloader = AudioDownloader(settings=make_settings())
        downloader._report_external_progress("[download]  50.0% of ~10.00MiB")  # should not raise


class TestDownloadExternalMissingExecutable:
    """Tests for the error path when the external yt-dlp binary is missing."""

    def test_raises_download_error_with_helpful_message(self):
        from src.youtube_bootlegger.core.exceptions import DownloadError

        with tempfile.TemporaryDirectory() as tmpdir:
            downloader = AudioDownloader(
                output_dir=Path(tmpdir),
                settings=make_settings(ytdlp_path="/nonexistent/yt-dlp"),
            )

            try:
                downloader._download_external("https://youtu.be/abc")
                assert False, "expected DownloadError"
            except DownloadError as e:
                assert "/nonexistent/yt-dlp" in str(e)


def test_external_executable_resolution_is_logged(tmp_path, monkeypatch):
    """Show which executable a bare command selects from the app's PATH."""
    from unittest.mock import Mock

    messages = []
    (tmp_path / "song.mp3").write_bytes(b"audio")
    process = Mock(stdout=iter(["WARNING: challenge solving failed\n"]))
    process.wait.return_value = 0
    popen = Mock(return_value=process)
    monkeypatch.setattr("src.youtube_bootlegger.core.downloader.subprocess.Popen", popen)
    monkeypatch.setattr(
        "src.youtube_bootlegger.core.downloader.shutil.which",
        lambda command: "/app/.venv/bin/yt-dlp",
    )
    downloader = AudioDownloader(
        output_dir=tmp_path,
        log_callback=messages.append,
        settings=make_settings(),
    )

    assert downloader.download("https://youtu.be/abc") == tmp_path / "song.mp3"
    assert "yt-dlp executable: /app/.venv/bin/yt-dlp" in messages
    assert "WARNING: challenge solving failed" in messages
    assert "--no-warnings" not in popen.call_args.args[0]


def test_success_without_audio_explains_missing_output(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import pytest
    from src.youtube_bootlegger.core.exceptions import DownloadError

    process = Mock(stdout=iter(["https://example.invalid/audio\n"]))
    process.wait.return_value = 0
    monkeypatch.setattr("src.youtube_bootlegger.core.downloader.subprocess.Popen", Mock(return_value=process))
    settings = make_settings()
    settings.ytdlp_extra_args = "--get-url"
    with pytest.raises(DownloadError, match="without creating an MP3 audio file.*Extra yt-dlp options.*download log"):
        AudioDownloader(output_dir=tmp_path, settings=settings).download("https://youtu.be/abc")


def test_external_passes_cookies_from_browser_and_handles_age_error(tmp_path, monkeypatch):
    from unittest.mock import Mock
    import pytest
    from src.youtube_bootlegger.core.exceptions import DownloadError
    from src.youtube_bootlegger.core.settings import CookieBrowser

    process = Mock(stdout=iter(["ERROR: Sign in to confirm your age\n"]))
    process.wait.return_value = 1
    popen = Mock(return_value=process)
    monkeypatch.setattr("src.youtube_bootlegger.core.downloader.subprocess.Popen", popen)

    settings = make_settings()
    settings.cookies_from_browser = CookieBrowser.CHROME
    downloader = AudioDownloader(output_dir=tmp_path, settings=settings)

    with pytest.raises(DownloadError) as exc_info:
        downloader.download("https://youtu.be/abc")

    cmd = popen.call_args.args[0]
    assert "--cookies-from-browser" in cmd
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "chrome"
    assert "Chrome" in str(exc_info.value)
