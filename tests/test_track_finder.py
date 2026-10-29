"""Tests for the AI track-list finder's LLM layer; no network calls."""

import json
from dataclasses import replace

import pytest

from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.core.video_info import VideoChapter, VideoComment, VideoInfo
from src.youtube_bootlegger.llm import track_finder as tf
from src.youtube_bootlegger.llm.http import LlmError
from src.youtube_bootlegger.llm.track_finder import (
    FindOutcome,
    FoundTrack,
    TracklistDiscovery,
    TracklistFindError,
    TrackSource,
    build_track_sources,
    find_tracklist,
    validate_discovery,
)
from tests.test_llm_tracklist import FakeSettingsBackend


def make_video(**fields) -> VideoInfo:
    defaults = dict(
        video_id="vid", title="Band Live", channel="Chan", duration=3600,
        duration_string="1:00:00", thumbnail_url="",
    )
    return VideoInfo(**{**defaults, **fields})


def api_settings(**fields) -> AppSettings:
    settings = AppSettings(FakeSettingsBackend())
    settings.llm_provider = LlmProvider.OPENAI
    settings.openai_api_key = "sk-test"
    for key, value in fields.items():
        setattr(settings, key, value)
    return settings


def discovery(source_id="", entries=(), untimed="", artist="", album="") -> TracklistDiscovery:
    return TracklistDiscovery(
        source_id=source_id,
        entries=[
            {"title": title, "start_seconds": start, "source_line": line}
            for title, start, line in entries
        ],
        untimed_source_id=untimed,
        artist_name=artist,
        album_name=album,
    )


COMMENT = TrackSource("comment:1", "comment #1", "Setlist:\n0:00 1. Opener\n4:05 2. Second\n1:02:03 Encore")
SOURCES = (TrackSource("description", "the description", "Thanks for watching"), COMMENT)
ENTRIES = (
    ("Opener", 0, "0:00 1. Opener"),
    ("Second", 245, "4:05 2. Second"),
    ("Encore", 3723, "1:02:03 Encore"),
)


class TestBuildTrackSources:
    def test_orders_description_chapters_then_numbered_comments(self):
        info = make_video(
            description="  Live at the venue  ",
            chapters=(VideoChapter("Intro", 0, 30), VideoChapter("Song", 30.7)),
            comments=(VideoComment("x", "first"), VideoComment("y", "second")),
        )
        sources = build_track_sources(info)
        assert [(s.source_id, s.label) for s in sources] == [
            ("description", "the description"),
            ("chapters", "the chapters"),
            ("comment:1", "comment #1"),
            ("comment:2", "comment #2"),
        ]
        assert sources[0].text == "Live at the venue"
        # Fractional starts are floored.
        assert sources[1].text == "0:00 Intro\n0:30 Song"

    def test_chapters_past_an_hour_use_hours(self):
        info = make_video(chapters=(VideoChapter("Late", 3725), VideoChapter("Two\nlines", 4000)))
        assert build_track_sources(info)[0].text == "1:02:05 Late\n1:06:40 Two lines"

    def test_empty_video_has_no_sources(self):
        assert build_track_sources(make_video(description="  ")) == ()

    def test_blank_comments_are_skipped_but_keep_their_number(self):
        info = make_video(comments=(VideoComment("a", " "), VideoComment("b", "list")))
        assert [s.source_id for s in build_track_sources(info)] == ["comment:2"]

    def test_long_source_keeps_leading_whole_lines(self, monkeypatch):
        monkeypatch.setattr(tf, "MAX_SOURCE_CHARS", 12)
        info = make_video(description="aaaa\nbbbb\ncccc")
        assert build_track_sources(info)[0].text == "aaaa\nbbbb"

    def test_single_overlong_line_is_cut(self, monkeypatch):
        monkeypatch.setattr(tf, "MAX_SOURCE_CHARS", 5)
        assert build_track_sources(make_video(description="abcdefgh"))[0].text == "abcde"

    def test_total_budget_drops_later_sources(self, monkeypatch):
        monkeypatch.setattr(tf, "MAX_TOTAL_SOURCE_CHARS", 10)
        info = make_video(
            description="12345",
            comments=(VideoComment("a", "1234"), VideoComment("b", "12"), VideoComment("c", "1")),
        )
        assert [s.source_id for s in build_track_sources(info)] == ["description", "comment:1"]


class TestValidateDiscovery:
    def test_found(self):
        result = validate_discovery(
            discovery("comment:1", ENTRIES, artist=" Band ", album=" Live "), SOURCES, 4000,
        )
        assert result.outcome == FindOutcome.FOUND
        assert result.source == COMMENT
        assert result.tracks == (
            FoundTrack("Opener", 0), FoundTrack("Second", 245), FoundTrack("Encore", 3723),
        )
        assert (result.artist_name, result.album_name) == ("Band", "Live")

    def test_list_may_start_after_zero(self):
        result = validate_discovery(discovery("comment:1", ENTRIES[1:]), SOURCES, 4000)
        assert result.tracks[0].start_seconds == 245

    def test_source_line_matches_after_whitespace_normalising(self):
        entries = (("Opener", 0, "  0:00   1. Opener "),)
        assert validate_discovery(discovery("comment:1", entries), SOURCES, 0).tracks

    def test_unknown_duration_skips_the_bound(self):
        assert validate_discovery(discovery("comment:1", ENTRIES), SOURCES, 0).tracks

    def test_not_found(self):
        result = validate_discovery(discovery(artist="Band"), SOURCES, 4000)
        assert result.outcome == FindOutcome.NOT_FOUND
        assert result.source is None and result.tracks == ()

    def test_untimed(self):
        result = validate_discovery(discovery(untimed="description"), SOURCES, 4000)
        assert result.outcome == FindOutcome.UNTIMED
        assert result.source == SOURCES[0]

    def test_unknown_untimed_source_is_not_found(self):
        result = validate_discovery(discovery(untimed="comment:9"), SOURCES, 4000)
        assert result.outcome == FindOutcome.NOT_FOUND

    @pytest.mark.parametrize("response,match", [
        (discovery("comment:9", ENTRIES), "unknown source"),
        (discovery("", ENTRIES), "unknown source"),
        (discovery("comment:1", ()), "no tracks from comment #1"),
        (discovery("comment:1", (("Opener", 0, "0:00 Made up"),)), "isn't in comment #1"),
        (discovery("description", ENTRIES[:1]), "isn't in the description"),
        (discovery("comment:1", (("Second", 240, "4:05 2. Second"),)), "doesn't match"),
        (discovery("comment:1", (("Opener", -1, "0:00 1. Opener"),)), "doesn't match"),
        (discovery("comment:1", (("  ", 0, "0:00 1. Opener"),)), "without a title"),
        (discovery("comment:1", (ENTRIES[1], ENTRIES[0])), "don't increase"),
        (discovery("comment:1", (ENTRIES[0], ENTRIES[0])), "don't increase"),
        (discovery("comment:1", ENTRIES), "after the video ends"),
    ])
    def test_rejections(self, response, match):
        with pytest.raises(TracklistFindError, match=match):
            validate_discovery(response, SOURCES, 3723)

    @pytest.mark.parametrize("line,seconds", [
        ("[0:00] A", {0}),
        ("12:30 - B", {750}),
        ("123:45 C", {7425}),
        ("1:02:03 D", {3723}),
        ("0:00 then 4:05 E", {0, 245}),
        ("2024:12:30 not a time", set()),
        ("1:75 bad seconds", set()),
        ("No time", set()),
    ])
    def test_line_timestamps(self, line, seconds):
        assert tf._line_timestamps(line) == seconds


def openai_reply(payload: dict):
    def post(_url, _headers, _body):
        return {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return post


class TestFindTracklist:
    INFO = make_video(duration=4000, comments=(VideoComment("x", COMMENT.text),))

    def test_happy_path_sends_sources_and_validates(self):
        sent = {}

        def post(url, headers, body):
            sent.update(body)
            return openai_reply(discovery("comment:1", ENTRIES, artist="Band").model_dump())(
                url, headers, body)

        result = find_tracklist(api_settings(), self.INFO, http_post=post)

        assert result.outcome == FindOutcome.FOUND
        assert [t.title for t in result.tracks] == ["Opener", "Second", "Encore"]
        prompt = sent["messages"][1]["content"]
        assert '<source id="comment:1">' in prompt
        assert sent["response_format"]["json_schema"]["name"] == tf.SCHEMA_NAME

    def test_no_sources_makes_no_call(self):
        def post(*_args):
            raise AssertionError("AI was called")

        result = find_tracklist(api_settings(), make_video(), http_post=post)
        assert result.outcome == FindOutcome.NOT_FOUND

    def test_lite_is_an_error(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.llm_provider = LlmProvider.CHATGPT_LITE
        with pytest.raises(TracklistFindError, match="needs an API model"):
            find_tracklist(settings, self.INFO, http_post=openai_reply({}))

    def test_missing_credentials_is_an_error(self):
        with pytest.raises(TracklistFindError, match="not configured"):
            find_tracklist(api_settings(openai_api_key=""), self.INFO)

    def test_provider_error(self):
        def post(*_args):
            raise LlmError("LLM request failed: HTTP 500")

        with pytest.raises(TracklistFindError, match="HTTP 500"):
            find_tracklist(api_settings(), self.INFO, http_post=post)

    def test_bad_json(self):
        def post(*_args):
            return {"choices": [{"message": {"content": "not json"}}]}

        with pytest.raises(TracklistFindError, match="invalid JSON"):
            find_tracklist(api_settings(), self.INFO, http_post=post)

    def test_invalid_response_is_an_error(self):
        bad = discovery("comment:1", (("Opener", 0, "0:00 invented"),)).model_dump()
        with pytest.raises(TracklistFindError, match="isn't in comment #1"):
            find_tracklist(api_settings(), self.INFO, http_post=openai_reply(bad))

    def test_uses_video_duration_bound(self):
        short = replace(self.INFO, duration=100)
        payload = discovery("comment:1", ENTRIES).model_dump()
        with pytest.raises(TracklistFindError, match="after the video ends"):
            find_tracklist(api_settings(), short, http_post=openai_reply(payload))
