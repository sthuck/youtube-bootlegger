"""Unit tests for video info fetching helpers, including external yt-dlp mode."""

import pytest

from src.youtube_bootlegger.core.exceptions import ValidationError
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.video_info import (
    _build_video_info,
    _fetch_video_info_external,
)


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


def make_settings(ytdlp_path=""):
    settings = AppSettings(FakeSettingsBackend())
    settings.use_external_ytdlp = True
    settings.ytdlp_path = ytdlp_path
    return settings


class TestBuildVideoInfo:
    """Tests for _build_video_info, shared by the library and CLI code paths."""

    def test_builds_from_full_info_dict(self):
        info = {
            "id": "abc123",
            "title": "My Concert",
            "channel": "My Channel",
            "duration": 125,
            "thumbnails": [{"url": "https://example.com/hqdefault.jpg", "width": 480}],
            "view_count": 1500,
            "upload_date": "20240115",
        }

        video_info = _build_video_info(info)

        assert video_info.video_id == "abc123"
        assert video_info.title == "My Concert"
        assert video_info.channel == "My Channel"
        assert video_info.duration == 125
        assert video_info.duration_string == "2:05"
        assert video_info.thumbnail_url == "https://example.com/hqdefault.jpg"
        assert video_info.view_count == 1500
        assert video_info.upload_date == "20240115"

    def test_falls_back_to_uploader_when_no_channel(self):
        info = {"title": "Some Video", "uploader": "Some Uploader"}
        video_info = _build_video_info(info)
        assert video_info.channel == "Some Uploader"

    def test_defaults_title_when_missing(self):
        video_info = _build_video_info({})
        assert video_info.title == "Unknown Title"


class TestFetchVideoInfoExternal:
    """Tests for _fetch_video_info_external using a fake yt-dlp executable."""

    def test_missing_executable_raises_validation_error(self):
        settings = make_settings(ytdlp_path="/nonexistent/yt-dlp")

        with pytest.raises(ValidationError) as exc_info:
            _fetch_video_info_external("https://youtu.be/abc", settings)

        assert "/nonexistent/yt-dlp" in str(exc_info.value)

    def test_parses_json_output_from_fake_executable(self, tmp_path):
        fake_ytdlp = tmp_path / "fake-yt-dlp.py"
        fake_ytdlp.write_text(
            "#!/usr/bin/env python3\n"
            "import json\n"
            "print(json.dumps({"
            "'id': 'xyz', 'title': 'Fake Video', 'channel': 'Fake Channel', "
            "'duration': 61, 'thumbnails': [], 'view_count': 42, "
            "'upload_date': '20230101'}))\n"
        )
        fake_ytdlp.chmod(0o755)

        settings = make_settings(ytdlp_path=str(fake_ytdlp))

        video_info = _fetch_video_info_external("https://youtu.be/xyz", settings)

        assert video_info.video_id == "xyz"
        assert video_info.title == "Fake Video"
        assert video_info.duration_string == "1:01"
        assert video_info.view_count == 42

    def test_nonzero_exit_raises_validation_error(self, tmp_path):
        fake_ytdlp = tmp_path / "fake-yt-dlp-fail.py"
        fake_ytdlp.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "print('ERROR: Video unavailable', file=sys.stderr)\n"
            "sys.exit(1)\n"
        )
        fake_ytdlp.chmod(0o755)

        settings = make_settings(ytdlp_path=str(fake_ytdlp))

        with pytest.raises(ValidationError) as exc_info:
            _fetch_video_info_external("https://youtu.be/xyz", settings)

        assert "unavailable" in str(exc_info.value).lower()
