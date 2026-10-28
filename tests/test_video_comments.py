"""Tests for fetching a video's leading comments; no network calls."""

from unittest.mock import Mock

import pytest

from src.youtube_bootlegger.core import video_comments as comments
from src.youtube_bootlegger.core.exceptions import ValidationError
from src.youtube_bootlegger.core.video_comments import VideoComment
from tests.test_downloader import make_settings

URL = "https://www.youtube.com/watch?v=fixture"
# Like counts intentionally differ from YouTube's order, which must be kept.
COMMENTS = [
    {"id": "a", "text": "0:00 One\n1:05 Two", "parent": "root", "like_count": 1},
    {"id": "reply", "text": "A reply", "parent": "a"},
    {"id": "blank", "text": "   ", "parent": "root"},
    {"id": "b", "text": "Another list", "parent": "root", "like_count": 100},
    {"id": "c", "text": "Third", "parent": "root"},
]


def test_fetches_top_level_comments_in_given_order(monkeypatch):
    fetch = Mock(return_value={"comments": COMMENTS})
    monkeypatch.setattr(comments, "fetch_info_dict", fetch)
    settings = make_settings()

    result = comments.fetch_video_comments(URL, settings, limit=2)

    assert result == (VideoComment("a", "0:00 One\n1:05 Two"), VideoComment("b", "Another list"))
    fetch.assert_called_once_with(URL, settings, comment_limit=2)


def test_default_settings_and_limit(monkeypatch):
    fetch = Mock(return_value={})
    monkeypatch.setattr(comments, "fetch_info_dict", fetch)
    monkeypatch.setattr(comments, "get_settings", make_settings)
    assert comments.fetch_video_comments(URL) == ()
    assert fetch.call_args.kwargs == {"comment_limit": comments.DEFAULT_COMMENT_LIMIT}


def test_zero_limit_makes_no_request(monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(comments, "fetch_info_dict", fetch)
    assert comments.fetch_video_comments(URL, make_settings(), limit=0) == ()
    fetch.assert_not_called()


@pytest.mark.parametrize("limit", [-1, 2.5, "20", True, None])
def test_invalid_limit_rejected_before_fetch(monkeypatch, limit):
    fetch = Mock()
    monkeypatch.setattr(comments, "fetch_info_dict", fetch)
    with pytest.raises(ValidationError, match="nonnegative integer"):
        comments.fetch_video_comments(URL, make_settings(), limit=limit)
    fetch.assert_not_called()


@pytest.mark.parametrize("raw", [None, [], [None, {}, {"text": 5}]])
def test_absent_or_unusable_comments(raw):
    assert comments.parse_comments(raw, 20) == ()


def test_comment_without_id_keeps_text():
    assert comments.parse_comments([{"text": "Set list"}], 20) == (VideoComment("", "Set list"),)
