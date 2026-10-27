"""Track-source fetching tests; no network or AI calls."""

import json
import subprocess
from unittest.mock import Mock

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor

from src.youtube_bootlegger.core import video_sources as sources
from src.youtube_bootlegger.core.exceptions import ValidationError
from tests.test_downloader import make_settings

URL = "https://www.youtube.com/watch?v=fixture"
PAYLOAD = {
    "id": "fixture", "title": "Live 演奏", "description": "0:00 One\n1:05 Two",
    "chapters": [
        {"title": "One", "start_time": 0, "end_time": 65},
        {"title": "Two", "start_time": 65.5, "end_time": 150},
    ],
    # Like counts intentionally differ from YouTube order.
    "comments": [
        {"id": "a", "text": "0:00 One\n1:05 Two", "parent": "root", "like_count": 1},
        {"id": "reply", "text": "A reply", "parent": "a"},
        {"id": "blank", "text": "   ", "parent": "root"},
        {"id": "b", "text": "Another list", "parent": "root", "like_count": 100},
        {"id": "c", "text": "Third", "parent": "root"},
    ],
}


@pytest.mark.parametrize("external", [False, True])
def test_both_backends_produce_same_sources(monkeypatch, external):
    if external:
        run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(PAYLOAD), ""))
        monkeypatch.setattr(sources.subprocess, "run", run)
    else:
        ydl = Mock()
        ydl.extract_info.return_value = PAYLOAD.copy()
        manager = Mock()
        manager.__enter__ = Mock(return_value=ydl)
        manager.__exit__ = Mock(return_value=False)
        monkeypatch.setattr(sources.yt_dlp, "YoutubeDL", Mock(return_value=manager))

    result = sources.fetch_video_sources(URL, make_settings(use_external=external), comment_limit=2)

    assert result.video_id == "fixture"
    assert result.title == "Live 演奏"
    assert result.description == PAYLOAD["description"]
    assert result.chapters == (
        sources.VideoChapter("One", 0, 65), sources.VideoChapter("Two", 65.5, 150),
    )
    assert result.comments == (
        sources.VideoComment("a", "0:00 One\n1:05 Two"),
        sources.VideoComment("b", "Another list"),
    )
    if external:
        args = run.call_args.args[0]
        # Check our flags through yt-dlp's real parser, not just string matching.
        options = yt_dlp.parse_options(args[1:]).ydl_opts
        assert options["skip_download"] and options["noplaylist"] and options["getcomments"]
        assert options["extractor_args"]["youtube"] == {
            "comment_sort": ["top"], "max_comments": ["2", "2", "0", "0"],
        }
        assert run.call_args.kwargs["timeout"] == 120
    else:
        ydl.extract_info.assert_called_once_with(URL, download=False)
        ydl.post_extract.assert_called_once()


class FixtureIE(InfoExtractor):
    _VALID_URL = r"fixture:(?P<id>\w+)"

    def _real_extract(self, url):
        return {
            **PAYLOAD, "comments": None, "url": "https://example.com/audio.mp3",
            "__post_extractor": self.extract_comments(),
        }

    def _get_comments(self):
        yield {"id": "deferred", "text": "Set list", "parent": "root"}


@pytest.mark.parametrize("limit", [0, 2])
def test_real_library_executes_deferred_comments_only_when_requested(monkeypatch, limit):
    original = yt_dlp.YoutubeDL
    options_seen = []

    def downloader(options):
        options_seen.append(options)
        ydl = original(options, auto_init=False)
        ydl.add_info_extractor(FixtureIE())
        return ydl

    monkeypatch.setattr(sources.yt_dlp, "YoutubeDL", downloader)
    result = sources.fetch_video_sources("fixture:test", make_settings(), comment_limit=limit)
    assert result.comments == ((sources.VideoComment("deferred", "Set list"),) if limit else ())
    assert result.chapters[0].title == "One"
    assert options_seen[0]["getcomments"] == bool(limit)
    assert options_seen[0]["extractor_args"]["youtube"] == {
        "comment_sort": ["top"], "max_comments": [str(limit), str(limit), "0", "0"],
    }


def test_external_zero_skips_comments_and_honors_executable(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(PAYLOAD), ""))
    monkeypatch.setattr(sources.subprocess, "run", run)
    result = sources.fetch_video_sources(
        URL, make_settings(use_external=True, ytdlp_path="/custom path/yt-dlp"), comment_limit=0,
    )
    args = run.call_args.args[0]
    assert args[0] == "/custom path/yt-dlp"
    assert "--ignore-config" in args
    assert "--write-comments" not in args
    assert "--extractor-args" not in args
    assert args[-2:] == ["--", URL]
    assert result.comments == ()
    assert result.description


@pytest.mark.parametrize("limit", [-1, 2.5, "20", True, None])
def test_invalid_limit_rejected_before_fetch(monkeypatch, limit):
    fetch = Mock()
    monkeypatch.setattr(sources, "_fetch_sources_library", fetch)
    with pytest.raises(ValidationError, match="nonnegative integer"):
        sources.fetch_video_sources(URL, make_settings(), comment_limit=limit)
    fetch.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"description": None, "comments": None, "chapters": None}])
def test_absent_sources(monkeypatch, payload):
    monkeypatch.setattr(sources, "_fetch_sources_library", lambda *args: payload)
    assert sources.fetch_video_sources(URL, make_settings()) == sources.VideoSources("", "")


@pytest.mark.parametrize("payload", [None, [], {"_type": "playlist"}, {"_type": "multi_video"}])
def test_invalid_or_playlist_response(monkeypatch, payload):
    monkeypatch.setattr(sources, "_fetch_sources_library", lambda *args: payload)
    with pytest.raises(ValidationError, match="single video"):
        sources.fetch_video_sources(URL, make_settings())


def test_skips_unusable_chapters_without_changing_valid_names():
    result = sources._build_video_sources({"chapters": [
        None, {}, {"title": "", "start_time": 0},
        {"title": "Bad", "start_time": float("nan")},
        {"title": "Bad", "start_time": -1},
        {"title": "Bad", "start_time": True},
        {"title": "Bad", "start_time": 10, "end_time": 5},
        {"title": " 演奏 ", "start_time": 3600.5},
    ]}, 20)
    assert result.chapters == (sources.VideoChapter(" 演奏 ", 3600.5),)


@pytest.mark.parametrize("output", ["garbage", "", "null", "[]", '{"_type":"playlist"}'])
def test_external_bad_output(monkeypatch, output):
    monkeypatch.setattr(sources.subprocess, "run", Mock(return_value=
                        subprocess.CompletedProcess([], 0, output, "")))
    with pytest.raises(ValidationError):
        sources.fetch_video_sources(URL, make_settings(use_external=True))


@pytest.mark.parametrize("error,match", [
    (FileNotFoundError(), "not found"),
    (subprocess.TimeoutExpired("yt-dlp", 120), "Timed out"),
    (PermissionError("denied"), "Could not run"),
])
def test_external_process_errors(monkeypatch, error, match):
    monkeypatch.setattr(sources.subprocess, "run", Mock(side_effect=error))
    with pytest.raises(ValidationError, match=match):
        sources.fetch_video_sources(URL, make_settings(use_external=True))


def test_external_failure_includes_diagnostic(monkeypatch):
    monkeypatch.setattr(sources.subprocess, "run", Mock(return_value=
                        subprocess.CompletedProcess([], 1, "", "YouTube unavailable")))
    with pytest.raises(ValidationError, match="YouTube unavailable"):
        sources.fetch_video_sources(URL, make_settings(use_external=True))


def test_library_failure_is_validation_error(monkeypatch):
    monkeypatch.setattr(sources.yt_dlp, "YoutubeDL", Mock(side_effect=
                        yt_dlp.utils.DownloadError("private video")))
    with pytest.raises(ValidationError, match="private video"):
        sources.fetch_video_sources(URL, make_settings())


def test_default_settings_and_comment_limit(monkeypatch):
    monkeypatch.setattr(sources, "get_settings", make_settings)
    fetch = Mock(return_value={})
    monkeypatch.setattr(sources, "_fetch_sources_library", fetch)
    sources.fetch_video_sources(URL)
    fetch.assert_called_once_with(URL, 20)
