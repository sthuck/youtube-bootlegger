"""Tests for UI-agnostic application logic shared by all front-ends."""

from pathlib import Path

from src.youtube_bootlegger.app_logic import (
    FormError,
    FormField,
    JobForm,
    build_job,
    check_ai_assist_ready,
    format_progress_stage,
    summarize_preview,
    summarize_video,
)
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.core.template_parser import preview_parse
from src.youtube_bootlegger.core.video_info import VideoInfo
from src.youtube_bootlegger.models import DownloadJob


class DictBackend:
    def __init__(self):
        self.data = {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def sync(self):
        pass


VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def make_video(title="Live at Venue", **overrides) -> VideoInfo:
    fields = {
        "video_id": "dQw4w9WgXcQ",
        "title": title,
        "channel": "Some Channel",
        "duration": 3600,
        "duration_string": "1:00:00",
        "thumbnail_url": "https://img.example/thumb.jpg",
        "view_count": 12_345,
        "upload_date": "20240131",
    }
    fields.update(overrides)
    return VideoInfo(**fields)


def make_form(**overrides) -> JobForm:
    fields = {
        "url": VALID_URL,
        "template": "%songname% - %mm%:%ss%",
        "tracklist_text": "Intro - 0:00\nSong Two - 4:30",
        "artist": "The Band",
        "album": "",
        "output_dir": "/tmp/music",
    }
    fields.update(overrides)
    return JobForm(**fields)


class TestBuildJob:
    def test_builds_job_from_valid_form(self):
        result = build_job(make_form(), make_video())
        assert isinstance(result, DownloadJob)
        assert result.url == VALID_URL
        assert result.output_dir == Path("/tmp/music")
        assert [t.name for t in result.tracks] == ["Intro", "Song Two"]
        assert result.artist == "The Band"
        assert result.thumbnail_url == "https://img.example/thumb.jpg"

    def test_album_defaults_to_video_title(self):
        result = build_job(make_form(album=""), make_video(title="Big Show"))
        assert isinstance(result, DownloadJob)
        assert result.album == "Big Show"

    def test_artist_none_when_blank_but_album_given(self):
        result = build_job(make_form(artist="  ", album="Album"), make_video())
        assert isinstance(result, DownloadJob)
        assert result.artist is None
        assert result.album == "Album"

    def test_empty_template_falls_back_to_default(self):
        result = build_job(make_form(template=""), make_video())
        assert isinstance(result, DownloadJob)

    def test_missing_url(self):
        assert build_job(make_form(url="  "), make_video()) == FormError(
            FormField.URL, "Please enter a YouTube URL"
        )

    def test_invalid_url(self):
        result = build_job(make_form(url="https://example.com"), make_video())
        assert isinstance(result, FormError)
        assert result.field == FormField.URL
        assert "valid" in result.message

    def test_video_info_not_loaded(self):
        result = build_job(make_form(), None)
        assert isinstance(result, FormError)
        assert result.field == FormField.URL
        assert "wait" in result.message

    def test_invalid_template(self):
        result = build_job(make_form(template="%songname%"), make_video())
        assert isinstance(result, FormError)
        assert result.field == FormField.TEMPLATE
        assert result.message.startswith("Invalid template")

    def test_empty_tracklist(self):
        result = build_job(make_form(tracklist_text="   "), make_video())
        assert isinstance(result, FormError)
        assert result.field == FormField.TRACKLIST

    def test_unparseable_tracklist(self):
        result = build_job(make_form(tracklist_text="no timestamp here"), make_video())
        assert isinstance(result, FormError)
        assert result.field == FormField.TRACKLIST

    def test_missing_artist_and_album(self):
        result = build_job(make_form(artist="", album=""), make_video())
        assert result == FormError(
            FormField.METADATA, "Please enter an artist name or album name"
        )

    def test_missing_output_dir(self):
        result = build_job(make_form(output_dir=" "), make_video())
        assert isinstance(result, FormError)
        assert result.field == FormField.OUTPUT_DIR


class TestSummarizePreview:
    def test_empty_tracklist_is_valid_without_status(self):
        summary = summarize_preview(preview_parse("", "%songname% - %mm%:%ss%"))
        assert summary.status == ""
        assert summary.is_valid is True

    def test_valid_tracklist_reports_count(self):
        preview = preview_parse("A - 0:00\nB - 1:00", "%songname% - %mm%:%ss%")
        summary = summarize_preview(preview)
        assert summary.status == "2 tracks"
        assert summary.is_valid is True

    def test_errors_reported(self):
        preview = preview_parse("A - 0:00\nbad line", "%songname% - %mm%:%ss%")
        summary = summarize_preview(preview)
        assert summary.status == "1 error(s)"
        assert summary.is_valid is False


class TestFormatProgressStage:
    def test_known_stage(self):
        assert format_progress_stage("download", 42.7) == "Downloading: 42%"

    def test_unknown_stage_title_cased(self):
        assert format_progress_stage("custom", 10) == "Custom: 10%"


class TestSummarizeVideo:
    def test_formats_fields(self):
        summary = summarize_video(make_video())
        assert summary.title == "Live at Venue"
        assert summary.channel == "Some Channel"
        assert summary.duration == "Duration: 1:00:00"
        assert summary.views == "12.3K views"
        assert summary.date == "Uploaded: 2024-01-31"

    def test_truncates_long_title(self):
        summary = summarize_video(make_video(title="x" * 100))
        assert len(summary.title) == 80
        assert summary.title.endswith("...")

    def test_missing_date_is_blank(self):
        assert summarize_video(make_video(upload_date=None)).date == ""


class TestCheckAiAssistReady:
    def settings(self, provider=LlmProvider.CHATGPT_LITE, **values):
        s = AppSettings(DictBackend())
        s.llm_provider = provider
        for key, value in values.items():
            setattr(s, key, value)
        return s

    def test_ready(self):
        assert check_ai_assist_ready(make_video(), "A - 0:00", self.settings()) is None

    def test_requires_video(self):
        message = check_ai_assist_ready(None, "A - 0:00", self.settings())
        assert message and "video info" in message

    def test_requires_tracklist(self):
        message = check_ai_assist_ready(make_video(), "  ", self.settings())
        assert message and "empty" in message.lower()

    def test_requires_configured_provider(self):
        message = check_ai_assist_ready(
            make_video(), "A - 0:00", self.settings(LlmProvider.OPENAI)
        )
        assert message and "not configured" in message
