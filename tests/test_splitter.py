"""Unit tests for AudioSplitter's use of the configured ffmpeg executable."""

import pytest

from src.youtube_bootlegger.core.exceptions import FFmpegNotFoundError
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.splitter import AudioSplitter


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


def make_settings(ffmpeg_path=""):
    settings = AppSettings(FakeSettingsBackend())
    settings.ffmpeg_path = ffmpeg_path
    return settings


class TestFfmpegCommandResolution:
    """Tests that AudioSplitter picks up the configured ffmpeg path."""

    def test_defaults_to_ffmpeg_on_path(self):
        splitter = AudioSplitter(settings=make_settings())
        assert splitter._ffmpeg_command == "ffmpeg"

    def test_uses_custom_ffmpeg_path(self):
        splitter = AudioSplitter(settings=make_settings(ffmpeg_path="/opt/custom/ffmpeg"))
        assert splitter._ffmpeg_command == "/opt/custom/ffmpeg"

    def test_check_ffmpeg_raises_with_missing_custom_path(self):
        splitter = AudioSplitter(settings=make_settings(ffmpeg_path="/nonexistent/ffmpeg"))

        with pytest.raises(FFmpegNotFoundError) as exc_info:
            splitter._check_ffmpeg()

        assert "/nonexistent/ffmpeg" in str(exc_info.value)

    def test_run_ffmpeg_command_uses_configured_executable(self, tmp_path, monkeypatch):
        from src.youtube_bootlegger.models import Track

        splitter = AudioSplitter(settings=make_settings(ffmpeg_path="/opt/custom/ffmpeg"))
        captured_cmd = {}

        class FakeResult:
            returncode = 0
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured_cmd["cmd"] = cmd
            return FakeResult()

        monkeypatch.setattr("src.youtube_bootlegger.core.splitter.subprocess.run", fake_run)

        track = Track(name="Song", start_seconds=0, end_seconds=None)
        splitter._run_ffmpeg(tmp_path / "in.mp3", tmp_path / "out.mp3", track)

        assert captured_cmd["cmd"][0] == "/opt/custom/ffmpeg"
