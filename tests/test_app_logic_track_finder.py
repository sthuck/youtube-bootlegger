"""Tests for the UI-agnostic track-finder glue and the find worker."""

import pytest

from src.youtube_bootlegger.app_logic import track_finder as logic
from src.youtube_bootlegger.app_logic.track_finder import (
    FIND_TEMPLATE,
    NEEDS_API_MODEL_MESSAGE,
    AiButtonMode,
    CancelReason,
    FormValues,
    LogLine,
    TrackFinderSession,
    ai_button_label,
    ai_button_mode,
    check_find_ready,
    has_api_model,
    preview_comment_limit,
    render_tracklist,
    should_auto_find,
    video_sources_log_line,
)
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.core.template_parser import (
    DEFAULT_TEMPLATE,
    parse_tracklist_with_template,
)
from src.youtube_bootlegger.core.video_info import (
    DEFAULT_COMMENT_LIMIT,
    VideoChapter,
    VideoComment,
)
from src.youtube_bootlegger.llm.track_finder import (
    FindOutcome,
    FoundTrack,
    TracklistFindError,
    TracklistFindResult,
    TrackSource,
)
from src.youtube_bootlegger.workers import tracklist_find_worker as worker_module
from src.youtube_bootlegger.workers.tracklist_find_worker import TracklistFindWorker
from tests.test_llm_tracklist import FakeSettingsBackend
from tests.test_track_finder import api_settings, make_video

COMMENT = TrackSource("comment:3", "comment #3", "0:00 Opener\n4:05 Second")
FOUND = TracklistFindResult(
    FindOutcome.FOUND, COMMENT, (FoundTrack("Opener", 0), FoundTrack("Second", 245)),
    artist_name="Band", album_name="Live 2024",
)
EMPTY_FORM = FormValues(tracklist="", template="%songname% %mm%:%ss%", artist="", album="")


def lite_settings() -> AppSettings:
    settings = AppSettings(FakeSettingsBackend())
    settings.llm_provider = LlmProvider.CHATGPT_LITE
    return settings


class TestButtonAndReadiness:
    @pytest.mark.parametrize("text,mode", [("", AiButtonMode.FIND), (" \n", AiButtonMode.FIND),
                                           ("A - 0:00", AiButtonMode.DETECT_FORMAT)])
    def test_mode_follows_box(self, text, mode):
        assert ai_button_mode(text) == mode

    def test_labels(self):
        assert ai_button_label(AiButtonMode.FIND) == "Find with AI"
        assert ai_button_label(AiButtonMode.DETECT_FORMAT) == "Detect format"

    def test_has_api_model(self):
        assert has_api_model(api_settings())
        assert not has_api_model(api_settings(openai_api_key=""))
        assert not has_api_model(lite_settings())

    def test_preview_comment_limit(self):
        assert preview_comment_limit(api_settings()) == DEFAULT_COMMENT_LIMIT
        assert preview_comment_limit(lite_settings()) == 0

    def test_should_auto_find(self):
        video = make_video(duration=600)
        assert should_auto_find(api_settings(), video, "")
        assert not should_auto_find(api_settings(auto_find_tracklist=False), video, "")
        assert not should_auto_find(lite_settings(), video, "")
        assert not should_auto_find(api_settings(), video, "A - 0:00")
        assert not should_auto_find(api_settings(), make_video(duration=0), "")

    def test_check_find_ready(self):
        assert check_find_ready(None, api_settings()) == logic.VIDEO_NOT_LOADED_MESSAGE
        assert check_find_ready(make_video(), lite_settings()) == NEEDS_API_MODEL_MESSAGE
        assert check_find_ready(make_video(), api_settings()) is None


class TestRenderTracklist:
    def test_renders_default_format(self):
        assert render_tracklist(FOUND.tracks) == "Opener - 0:00\nSecond - 4:05"

    def test_total_minutes_past_an_hour(self):
        assert render_tracklist((FoundTrack("Late", 3725),)) == "Late - 62:05"

    def test_round_trips_through_the_default_template(self):
        tracks = (FoundTrack("Intro - Reprise", 0), FoundTrack("Ünïcode 曲", 245),
                  FoundTrack("Long", 3725))
        parsed = parse_tracklist_with_template(render_tracklist(tracks), DEFAULT_TEMPLATE)
        assert [(t.name, t.start_seconds) for t in parsed] == [
            ("Intro - Reprise", 0), ("Ünïcode 曲", 245), ("Long", 3725),
        ]
        assert FIND_TEMPLATE == DEFAULT_TEMPLATE


class TestVideoSourcesLogLine:
    def test_counts(self):
        info = make_video(
            description="x",
            chapters=(VideoChapter("a", 0), VideoChapter("b", 5)),
            comments=(VideoComment("c", "t"),),
        )
        assert video_sources_log_line(info) == LogLine(
            "Video info: description, 2 chapters, 1 comment")

    def test_empty(self):
        assert video_sources_log_line(make_video()).text == (
            "Video info: no description, 0 chapters, 0 comments")


def filled_session() -> tuple[TrackFinderSession, FormValues]:
    session = TrackFinderSession()
    token = session.begin("vid")
    application = session.complete(token, "vid", FOUND, EMPTY_FORM)
    return session, application.values


class TestSessionSearching:
    def test_begin_complete_lifecycle(self):
        session = TrackFinderSession()
        assert not session.searching
        token = session.begin("vid")
        assert session.searching and session.is_current(token)
        assert session.complete(token, "vid", FOUND, EMPTY_FORM) is not None
        assert not session.searching and not session.is_current(token)

    def test_begin_supersedes_running_search(self):
        session = TrackFinderSession()
        old = session.begin("vid")
        new = session.begin("vid")
        assert session.complete(old, "vid", FOUND, EMPTY_FORM) is None
        assert session.searching
        assert session.complete(new, "vid", FOUND, EMPTY_FORM) is not None

    def test_stale_token_changes_nothing(self):
        session = TrackFinderSession()
        token = session.begin("vid")
        session.cancel(CancelReason.STOPPED)
        assert session.complete(token, "vid", FOUND, EMPTY_FORM) is None
        assert session.fail(token, "boom") is None
        assert session.cached("vid") is None
        assert not session.ai_filled

    def test_cache_keeps_any_outcome_but_not_failures(self):
        session = TrackFinderSession()
        session.complete(session.begin("a"), "a", TracklistFindResult(FindOutcome.NOT_FOUND),
                         EMPTY_FORM)
        session.fail(session.begin("b"), "boom")
        assert session.cached("a").outcome == FindOutcome.NOT_FOUND
        assert session.cached("b") is None

    def test_fail_line(self):
        session = TrackFinderSession()
        line = session.fail(session.begin("vid"), "HTTP 500")
        assert line == LogLine("AI: couldn't find a track list: HTTP 500", "error")
        assert not session.searching

    @pytest.mark.parametrize("reason,text", [
        (CancelReason.STOPPED, "AI: search stopped"),
        (CancelReason.EDITED, "AI: search stopped because you edited the track list"),
        (CancelReason.VIDEO_CHANGED, "AI: search stopped because the video changed"),
    ])
    def test_cancel_lines(self, reason, text):
        session = TrackFinderSession()
        session.begin("vid")
        assert session.cancel(reason) == LogLine(text, "warn")
        assert session.cancel(reason) is None


class TestSessionComplete:
    def test_found_fills_form_and_logs(self):
        session = TrackFinderSession()
        application = session.complete(session.begin("vid"), "vid", FOUND, EMPTY_FORM)
        assert application.values == FormValues(
            "Opener - 0:00\nSecond - 4:05", FIND_TEMPLATE, "Band", "Live 2024")
        assert application.banner == session.banner == (
            "✨ Filled by AI from comment #3: 2 tracks. Check it before downloading.")
        assert application.log == (
            LogLine("AI: found 2 timestamped tracks in comment #3"),
            LogLine(f'AI: format set to "{FIND_TEMPLATE}"'),
        )
        assert session.ai_filled

    def test_banner_singular(self):
        one = TracklistFindResult(FindOutcome.FOUND, COMMENT, (FoundTrack("Opener", 0),))
        session = TrackFinderSession()
        application = session.complete(session.begin("vid"), "vid", one, EMPTY_FORM)
        assert "comment #3: 1 track." in session.banner
        assert application.log[0].text == "AI: found 1 timestamped track in comment #3"

    def test_keeps_users_artist_and_album(self):
        session = TrackFinderSession()
        current = FormValues("", "t", "My Artist", "My Album")
        values = session.complete(session.begin("vid"), "vid", FOUND, current).values
        assert (values.artist, values.album) == ("My Artist", "My Album")

    def test_box_filled_meanwhile_is_left_alone(self):
        session = TrackFinderSession()
        current = FormValues("Mine - 0:00", "t", "", "")
        application = session.complete(session.begin("vid"), "vid", FOUND, current)
        assert application.values is None and application.banner == ""
        assert application.log == (LogLine(
            "AI: found a track list, but you'd already filled one in; left it unchanged",
            "warn"),)
        assert not session.ai_filled

    def test_untimed(self):
        untimed = TracklistFindResult(
            FindOutcome.UNTIMED, TrackSource("description", "the description", "A\nB"))
        session = TrackFinderSession()
        application = session.complete(session.begin("vid"), "vid", untimed, EMPTY_FORM)
        assert application.values is None and application.banner == ""
        assert application.log == (LogLine(
            "AI: found song names without timestamps in the description; "
            "add timestamps to use it", "warn"),)

    def test_not_found(self):
        session = TrackFinderSession()
        application = session.complete(
            session.begin("vid"), "vid", TracklistFindResult(FindOutcome.NOT_FOUND), EMPTY_FORM)
        assert application.values is None
        assert application.log == (
            LogLine("AI: no track list found in the description, chapters or comments"),)


class TestSessionAfterFill:
    def test_writing_the_fill_is_not_an_edit(self):
        session, values = filled_session()
        assert session.on_tracklist_edited(values.tracklist) is None
        assert session.on_tracklist_edited(values.tracklist + "\n") is None
        assert session.ai_filled and session.banner

    def test_user_edit_ends_the_fill(self):
        session, values = filled_session()
        session.on_tracklist_edited(values.tracklist + "\nThird - 9:00")
        assert not session.ai_filled and session.banner == ""
        assert session.undo() is None

    def test_template_marker(self):
        session, _ = filled_session()
        assert session.template_set_by_ai(FIND_TEMPLATE)
        assert not session.template_set_by_ai("[%mm%:%ss%] %songname%")
        session.undo()
        assert not session.template_set_by_ai(FIND_TEMPLATE)

    def test_dismiss_banner_keeps_undo(self):
        session, _ = filled_session()
        session.dismiss_banner()
        assert session.banner == "" and session.ai_filled
        assert session.undo() == EMPTY_FORM

    def test_undo_restores_pre_fill_values(self):
        session, _ = filled_session()
        assert session.undo() == EMPTY_FORM
        assert not session.ai_filled and session.banner == ""
        assert session.undo() is None

    def test_video_change_restores_unedited_fill(self):
        session, _ = filled_session()
        assert session.on_video_changed() == (EMPTY_FORM, None)
        assert not session.ai_filled

    def test_video_change_keeps_edited_fill(self):
        session, values = filled_session()
        session.on_tracklist_edited("Edited - 0:00")
        assert session.on_video_changed() == (None, None)


class TestSessionEditsWhileSearching:
    def test_typing_cancels(self):
        session = TrackFinderSession()
        token = session.begin("vid")
        line = session.on_tracklist_edited("O")
        assert line == LogLine("AI: search stopped because you edited the track list", "warn")
        assert session.complete(token, "vid", FOUND, EMPTY_FORM) is None

    def test_blank_text_does_not_cancel(self):
        session = TrackFinderSession()
        session.begin("vid")
        assert session.on_tracklist_edited("  ") is None
        assert session.searching

    def test_video_change_cancels(self):
        session = TrackFinderSession()
        session.begin("vid")
        assert session.on_video_changed() == (
            None, LogLine("AI: search stopped because the video changed", "warn"))
        assert not session.searching


class TestApiHint:
    def test_shown_without_api_model(self):
        session = TrackFinderSession()
        assert session.show_api_hint(lite_settings(), make_video(), "")
        assert not session.show_api_hint(api_settings(), make_video(), "")
        assert not session.show_api_hint(lite_settings(), None, "")
        assert not session.show_api_hint(lite_settings(), make_video(), "A - 0:00")

    def test_dismissal_lasts_the_session(self):
        session = TrackFinderSession()
        session.dismiss_api_hint()
        assert not session.show_api_hint(lite_settings(), make_video(), "")


class TestTracklistFindWorker:
    def run_worker(self, monkeypatch, outcome):
        def fake_find(settings, info, *, http_post):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(worker_module, "find_tracklist", fake_find)
        worker = TracklistFindWorker(api_settings(), make_video(), 7)
        emitted = []
        worker.signals.finished.connect(lambda *args: emitted.append(("finished", *args)))
        worker.signals.error.connect(lambda *args: emitted.append(("error", *args)))
        worker.run()
        return emitted

    def test_emits_result_with_token(self, monkeypatch):
        assert self.run_worker(monkeypatch, FOUND) == [("finished", 7, FOUND)]

    def test_emits_find_error(self, monkeypatch):
        emitted = self.run_worker(monkeypatch, TracklistFindError("bad response"))
        assert emitted == [("error", 7, "bad response")]

    def test_emits_unexpected_error(self, monkeypatch):
        emitted = self.run_worker(monkeypatch, RuntimeError("boom"))
        assert emitted == [("error", 7, "Unexpected error: boom")]
