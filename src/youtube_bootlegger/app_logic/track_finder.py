"""UI-agnostic glue for the AI track-list finder, shared by all three front-ends.

Front-ends own their widgets and threads; everything they decide or display
about finding comes from here: the AI button's mode, when to run
automatically, the hint, the exact log/banner strings, and the per-session
state (cache, request tokens, AI-filled snapshot for Undo).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..core.settings import AppSettings
from ..core.template_parser import DEFAULT_TEMPLATE
from ..core.video_info import VideoInfo
from ..llm.track_finder import FoundTrack, TracklistFindResult

# The finder always writes the track list in this format.
FIND_TEMPLATE = DEFAULT_TEMPLATE

FIND_BUTTON_LABEL = "Find with AI"
DETECT_FORMAT_BUTTON_LABEL = "Detect format"

SEARCHING_TEXT = "Looking for a track list in the description, chapters and comments…"
STOP_BUTTON_LABEL = "Stop"
UNDO_BUTTON_LABEL = "Undo"
TEMPLATE_SET_BY_AI_TEXT = "set by AI"
API_HINT_TEXT = (
    "Want the track list filled in automatically? This needs an API model "
    "(OpenAI, Anthropic, …). ChatGPT Lite can't do it."
)
OPEN_SETTINGS_LABEL = "Open Settings"
# Manual "Find with AI" click without an API model (shown as a message).
NEEDS_API_MODEL_MESSAGE = (
    "Finding a track list needs an API model (OpenAI, Anthropic, …), "
    "not ChatGPT Lite. Choose one in Settings."
)

AUTO_FIND_SETTING_LABEL = "Find track lists automatically"
AUTO_FIND_SETTING_NOTE = (
    "When a video loads with an empty track list, sends its description, "
    "chapters and comments to the selected AI provider. Needs an API model, "
    "not ChatGPT Lite."
)


class AiButtonMode(StrEnum):
    """What the single AI button does, decided by the track list box."""

    FIND = "find"  # Empty box: find a track list in the video.
    DETECT_FORMAT = "detect_format"  # Filled box: today's template inference.


class CancelReason(StrEnum):
    """Why a running search was cancelled (its result is then discarded)."""

    STOPPED = "stopped"  # The Stop button.
    EDITED = "edited"  # The user typed in the track list box.
    VIDEO_CHANGED = "video_changed"  # The URL changed or the video was cleared.


@dataclass(frozen=True)
class LogLine:
    """A log entry; level is one of "info", "warn", "error" (as the log panels use)."""

    text: str
    level: str = "info"


@dataclass(frozen=True)
class FormValues:
    """The form fields the finder may change."""

    tracklist: str
    template: str
    artist: str
    album: str


@dataclass(frozen=True)
class FindApplication:
    """What a front-end does when a search finishes.

    Attributes:
        values: Form values to write, or None to leave the form untouched
            (UNTIMED, NOT_FOUND). Writing them must not count as a user edit
            (see TrackFinderSession.on_tracklist_edited).
        banner: Banner text to show above the box, or "" for no banner.
        log: Lines to append to the log, in order.
    """

    values: FormValues | None
    banner: str
    log: tuple[LogLine, ...]


def ai_button_mode(tracklist_text: str) -> AiButtonMode:
    """FIND when the box is blank (whitespace only), else DETECT_FORMAT."""
    raise NotImplementedError


def ai_button_label(mode: AiButtonMode) -> str:
    """FIND_BUTTON_LABEL or DETECT_FORMAT_BUTTON_LABEL."""
    raise NotImplementedError


def has_api_model(settings: AppSettings) -> bool:
    """True when an API provider is configured (is_llm_configured and not ChatGPT Lite)."""
    raise NotImplementedError


def preview_comment_limit(settings: AppSettings) -> int:
    """comment_limit for the preview's fetch_video_info call.

    DEFAULT_COMMENT_LIMIT when has_api_model(settings), else 0, so users
    without an API model don't pay for comments. (Read at fetch time; a video
    loaded before an API model was configured has no comments, and finding
    then uses the description and chapters only.)
    """
    raise NotImplementedError


def should_auto_find(
    settings: AppSettings,
    info: VideoInfo,
    tracklist_text: str,
) -> bool:
    """Whether to start a search on its own right after ``info`` loads.

    True only if settings.auto_find_tracklist, has_api_model(settings), the
    box is blank, and info.duration > 0 (skips live streams and premieres).
    """
    raise NotImplementedError


def check_find_ready(info: VideoInfo | None, settings: AppSettings) -> str | None:
    """Reason a manual "Find with AI" click can't run, or None if it can.

    "Please wait for video info to load before using AI." without a video;
    NEEDS_API_MODEL_MESSAGE without an API model. (DETECT_FORMAT clicks keep
    using check_ai_assist_ready, unchanged.)
    """
    raise NotImplementedError


def render_tracklist(tracks: tuple[FoundTrack, ...]) -> str:
    """Render tracks as track-list text matching FIND_TEMPLATE.

    One ``Title - M:SS`` line per track, newline-separated, no trailing
    newline. Minutes are total minutes, so hour-long sets stay parseable
    without %hh%: 3725 s → ``62:05``.
    """
    raise NotImplementedError


def video_sources_log_line(info: VideoInfo) -> LogLine:
    """Logged when a video loads, e.g. "Video info: description, 13 chapters, 20 comments".

    Parts: "description" or "no description"; "N chapter(s)"; "N comment(s)"
    (singular for 1, e.g. "1 chapter").
    """
    raise NotImplementedError


class TrackFinderSession:
    """Per-window finder state. Create one per front-end window; not thread-safe.

    Front-ends call it from their UI thread only. Background work gets a
    token from begin() and hands its result back with the same token; stale
    tokens are ignored, which covers Stop, typing, and URL changes.
    """

    def __init__(self) -> None:
        raise NotImplementedError

    # ── Searching ───────────────────────────────────────────────────

    @property
    def searching(self) -> bool:
        """True between begin() and complete()/fail()/cancel()."""
        raise NotImplementedError

    def begin(self, video_id: str) -> int:
        """Start a search for ``video_id``; returns its token.

        Supersedes (silently discards) any search already running. Callers
        then check cached(video_id): if present, call complete() right away
        with it instead of starting background work.
        """
        raise NotImplementedError

    def cached(self, video_id: str) -> TracklistFindResult | None:
        """The result of an earlier search for this video in this session, if any.

        Only complete() results are cached (any outcome); failures aren't.
        """
        raise NotImplementedError

    def is_current(self, token: int) -> bool:
        """Whether ``token`` belongs to the running search."""
        raise NotImplementedError

    def complete(
        self,
        token: int,
        video_id: str,
        result: TracklistFindResult,
        current: FormValues,
    ) -> FindApplication | None:
        """Finish a search. Returns None (and changes nothing) for a stale token.

        Caches ``result`` for ``video_id``. For FOUND: values set tracklist
        to render_tracklist(...), template to FIND_TEMPLATE, and artist/album
        to the result's only where ``current`` has them blank; remembers
        ``current`` for Undo and the written tracklist as AI-filled; banner
        "✨ Filled by AI from <label>: N tracks. Check it before downloading."
        ("1 track" singular). Log lines, in order:

        - FOUND: "AI: found N timestamped tracks in <label>", then
          'AI: format set to "<FIND_TEMPLATE>"'
        - UNTIMED: "AI: found song names without timestamps in <label>; add
          timestamps to use it" (warn), values None, no banner
        - NOT_FOUND: "AI: no track list found in the description, chapters
          or comments", values None, no banner

        If the box was filled meanwhile (current.tracklist not blank), FOUND
        is not applied: values None, no banner, log "AI: found a track list,
        but you'd already filled one in; left it unchanged" (warn).
        """
        raise NotImplementedError

    def fail(self, token: int, message: str) -> LogLine | None:
        """Finish a search with an error. None for a stale token.

        Returns "AI: couldn't find a track list: <message>" (error). Front-ends
        log it; a manual click also shows ``message`` as a message box/toast,
        an automatic run only logs.
        """
        raise NotImplementedError

    def cancel(self, reason: CancelReason) -> LogLine | None:
        """Cancel the running search; None if nothing was running.

        STOPPED → "AI: search stopped"; EDITED → "AI: search stopped because
        you edited the track list"; VIDEO_CHANGED → "AI: search stopped
        because the video changed". All "warn".
        """
        raise NotImplementedError

    # ── After filling ───────────────────────────────────────────────

    @property
    def ai_filled(self) -> bool:
        """True while the box still holds exactly what the finder wrote."""
        raise NotImplementedError

    @property
    def banner(self) -> str:
        """Banner text to show now, or "" (hidden)."""
        raise NotImplementedError

    def template_set_by_ai(self, template: str) -> bool:
        """Show TEMPLATE_SET_BY_AI_TEXT by the format field: ai_filled and
        ``template`` still equals FIND_TEMPLATE."""
        raise NotImplementedError

    def on_tracklist_edited(self, text: str) -> LogLine | None:
        """Call on every track list text change (user typing or programmatic).

        While searching, a nonblank ``text`` cancels with EDITED and returns
        that log line. Text equal to the AI-filled text is not an edit (so
        writing FindApplication.values is safe). Any other change ends
        ai_filled and hides the banner. Returns None unless it cancelled.
        """
        raise NotImplementedError

    def dismiss_banner(self) -> None:
        """Hide the banner (the ✕). ai_filled and Undo are unaffected."""
        raise NotImplementedError

    def undo(self) -> FormValues | None:
        """Values from before the fill, or None if nothing can be undone.

        Available while ai_filled. Ends ai_filled and hides the banner.
        """
        raise NotImplementedError

    def on_video_changed(self) -> tuple[FormValues | None, LogLine | None]:
        """Call when the URL changes or the video is cleared.

        Cancels a running search (VIDEO_CHANGED log line, else None). If the
        box is still ai_filled, returns the pre-fill values to restore (the
        list belonged to the old video), like undo(); otherwise None.
        """
        raise NotImplementedError

    # ── Hint ────────────────────────────────────────────────────────

    def show_api_hint(
        self,
        settings: AppSettings,
        info: VideoInfo | None,
        tracklist_text: str,
    ) -> bool:
        """Show API_HINT_TEXT: a video is loaded, the box is blank, there's no
        API model, and the hint wasn't dismissed in this session."""
        raise NotImplementedError

    def dismiss_api_hint(self) -> None:
        """Hide the hint for the rest of the session."""
        raise NotImplementedError
