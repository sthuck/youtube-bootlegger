"""Unit tests for video info helpers: metadata, track sources and thumbnails."""

from unittest.mock import Mock

import pytest

import src.youtube_bootlegger.core.video_info as vi
from src.youtube_bootlegger.core.exceptions import ValidationError
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.video_info import (
    VideoChapter,
    VideoComment,
    _build_video_info,
    parse_chapters,
    parse_comments,
    resolve_thumbnail,
    thumbnail_candidates,
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


class TestChaptersAndDescription:
    """Tests for the track-list sources kept from the yt-dlp info dict."""

    def test_keeps_description_and_valid_chapters(self):
        info = _build_video_info({
            "description": "0:00 One\n1:05 Two",
            "chapters": [
                {"title": "One", "start_time": 0, "end_time": 65},
                {"title": "Two", "start_time": 65.5, "end_time": 150},
            ],
        })
        assert info.description == "0:00 One\n1:05 Two"
        assert info.chapters == (VideoChapter("One", 0, 65), VideoChapter("Two", 65.5, 150))

    def test_missing_sources_are_empty(self):
        info = _build_video_info({"description": None, "chapters": None})
        assert info.description == ""
        assert info.chapters == ()

    def test_skips_unusable_chapters_without_changing_valid_names(self):
        chapters = parse_chapters([
            None, {}, {"title": "", "start_time": 0},
            {"title": "Bad", "start_time": float("nan")},
            {"title": "Bad", "start_time": -1},
            {"title": "Bad", "start_time": True},
            {"title": "Bad", "start_time": 10, "end_time": 5},
            {"title": " 演奏 ", "start_time": 3600.5},
        ])
        assert chapters == (VideoChapter(" 演奏 ", 3600.5),)


# Like counts intentionally differ from YouTube's order, which must be kept.
COMMENTS = [
    {"id": "a", "text": "0:00 One\n1:05 Two", "parent": "root", "like_count": 1},
    {"id": "reply", "text": "A reply", "parent": "a"},
    {"id": "blank", "text": "   ", "parent": "root"},
    {"id": "b", "text": "Another list", "parent": "root", "like_count": 100},
    {"id": "c", "text": "Third", "parent": "root"},
]


class TestComments:
    """Comments are fetched in the same request as the rest of the info."""

    @pytest.fixture
    def fetch(self, monkeypatch):
        fetch = Mock(return_value={"id": "", "comments": COMMENTS})
        monkeypatch.setattr(vi, "fetch_info_dict", fetch)
        monkeypatch.setattr(vi, "_url_exists", lambda url: False)
        return fetch

    def test_one_request_returns_top_level_comments_in_order(self, fetch):
        settings = AppSettings(FakeSettingsBackend())
        info = vi.fetch_video_info("https://youtu.be/x", settings, comment_limit=2)
        assert info.comments == (
            VideoComment("a", "0:00 One\n1:05 Two"), VideoComment("b", "Another list"),
        )
        fetch.assert_called_once_with("https://youtu.be/x", settings, comment_limit=2)

    def test_not_requested_by_default(self, fetch):
        info = vi.fetch_video_info("https://youtu.be/x", AppSettings(FakeSettingsBackend()))
        assert info.comments == ()
        assert fetch.call_args.kwargs == {"comment_limit": 0}

    @pytest.mark.parametrize("limit", [-1, 2.5, "20", True, None])
    def test_invalid_limit_rejected_before_fetch(self, fetch, limit):
        with pytest.raises(ValidationError, match="nonnegative integer"):
            vi.fetch_video_info("https://youtu.be/x", comment_limit=limit)
        fetch.assert_not_called()

    @pytest.mark.parametrize("raw", [None, [], [None, {}, {"text": 5}]])
    def test_absent_or_unusable_comments(self, raw):
        assert parse_comments(raw, 20) == ()

    def test_comment_without_id_keeps_text(self):
        assert parse_comments([{"text": "Set list"}], 20) == (VideoComment("", "Set list"),)


ZOO_ID = "jNQXAC9IVRw"


def yt_thumbnails(video_id):
    """Subset of what yt-dlp reports: guessed URLs (no width) plus sized ones."""
    base = f"https://i.ytimg.com/vi/{video_id}"
    webp = f"https://i.ytimg.com/vi_webp/{video_id}"
    return [
        {"url": f"{base}/default.jpg", "preference": -13},
        {"url": f"{base}/hqdefault.jpg?sqp=x", "preference": -7, "width": 480},
        {"url": f"{webp}/hqdefault.webp", "preference": -6},
        {"url": f"{base}/sddefault.jpg", "preference": -5},
        {"url": f"{base}/hq720.jpg", "preference": -3},
        {"url": f"{base}/maxresdefault.jpg", "preference": -1},
        {"url": f"{webp}/maxresdefault.webp", "preference": 0},
    ]


class TestThumbnailCandidates:
    def test_prefers_jpeg_largest_first(self):
        candidates = thumbnail_candidates(yt_thumbnails(ZOO_ID), ZOO_ID)
        assert candidates[0] == f"https://i.ytimg.com/vi/{ZOO_ID}/maxresdefault.jpg"
        assert candidates[1] == f"https://i.ytimg.com/vi/{ZOO_ID}/hq720.jpg"
        assert not any(".webp" in url for url in candidates)

    def test_always_ends_with_guaranteed_hqdefault(self):
        candidates = thumbnail_candidates(yt_thumbnails(ZOO_ID), ZOO_ID)
        assert candidates[-1] == f"https://i.ytimg.com/vi/{ZOO_ID}/hqdefault.jpg"
        assert len(candidates) == len(set(candidates))

    def test_no_thumbnails_still_gives_fallback(self):
        assert thumbnail_candidates([], "abc") == ["https://i.ytimg.com/vi/abc/hqdefault.jpg"]

    def test_no_thumbnails_and_no_id(self):
        assert thumbnail_candidates([], "") == []

    def test_webp_used_when_no_jpeg(self):
        thumbs = [{"url": "https://example.com/a.webp", "preference": 0}]
        assert thumbnail_candidates(thumbs, "")[0] == "https://example.com/a.webp"

    def test_build_video_info_uses_top_candidate_and_keeps_list(self):
        info = _build_video_info({"id": ZOO_ID, "thumbnails": yt_thumbnails(ZOO_ID)})
        assert info.thumbnail_url == f"https://i.ytimg.com/vi/{ZOO_ID}/maxresdefault.jpg"
        assert info.thumbnail_candidates[-1].endswith("/hqdefault.jpg")


class TestResolveThumbnail:
    def test_picks_first_reachable_candidate(self):
        info = _build_video_info({"id": ZOO_ID, "thumbnails": yt_thumbnails(ZOO_ID)})
        checked = []

        def exists(url):
            checked.append(url)
            return url.endswith("/hqdefault.jpg")  # Old SD video: only hqdefault exists.

        resolved = resolve_thumbnail(info, url_exists=exists)
        assert resolved.thumbnail_url == f"https://i.ytimg.com/vi/{ZOO_ID}/hqdefault.jpg"
        assert checked[0].endswith("/maxresdefault.jpg")

    def test_keeps_best_when_it_exists(self):
        info = _build_video_info({"id": "x", "thumbnails": yt_thumbnails("x")})
        resolved = resolve_thumbnail(info, url_exists=lambda url: True)
        assert resolved.thumbnail_url.endswith("/maxresdefault.jpg")

    def test_unchanged_when_nothing_reachable(self):
        info = _build_video_info({"id": "x", "thumbnails": yt_thumbnails("x")})
        assert resolve_thumbnail(info, url_exists=lambda url: False) == info

    def test_fetch_video_info_resolves_thumbnail(self, monkeypatch):
        settings = AppSettings(FakeSettingsBackend())
        monkeypatch.setattr(
            vi,
            "fetch_info_dict",
            lambda url, settings, comment_limit: {"id": ZOO_ID, "thumbnails": yt_thumbnails(ZOO_ID)},
        )
        monkeypatch.setattr(vi, "_url_exists", lambda url: url.endswith("/hqdefault.jpg"))
        info = vi.fetch_video_info("https://youtu.be/" + ZOO_ID, settings)
        assert info.thumbnail_url == f"https://i.ytimg.com/vi/{ZOO_ID}/hqdefault.jpg"
