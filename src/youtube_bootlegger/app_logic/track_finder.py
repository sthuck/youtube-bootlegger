"""UI-agnostic glue for the AI track-list finder, shared by all three front-ends.

Front-ends own their widgets and threads; everything they decide or display
about finding comes from here: the AI button's mode, when to run
automatically, the hint, the exact log/banner strings, and the per-session
state (cache, request tokens, AI-filled snapshot for Undo).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..core.settings import AppSettings, LlmProvider
from ..core.template_parser import DEFAULT_TEMPLATE
from ..core.video_info import DEFAULT_COMMENT_LIMIT, VideoInfo
from ..llm.config import is_llm_configured
from ..llm.track_finder import FindOutcome, FoundTrack, TracklistFindResult

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

VIDEO_NOT_LOADED_MESSAGE = "Please wait for video info to load before using AI."

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
    return AiButtonMode.DETECT_FORMAT if tracklist_text.strip() else AiButtonMode.FIND


def ai_button_label(mode: AiButtonMode) -> str:
    """FIND_BUTTON_LABEL or DETECT_FORMAT_BUTTON_LABEL."""
    return FIND_BUTTON_LABEL if mode == AiButtonMode.FIND else DETECT_FORMAT_BUTTON_LABEL


def has_api_model(settings: AppSettings) -> bool:
    """True when an API provider is configured (is_llm_configured and not ChatGPT Lite)."""
    return settings.llm_provider != LlmProvider.CHATGPT_LITE and is_llm_configured(settings)


def preview_comment_limit(settings: AppSettings) -> int:
    """comment_limit for the preview's fetch_video_info call.

    DEFAULT_COMMENT_LIMIT when has_api_model(settings), else 0, so users
    without an API model don't pay for comments. (Read at fetch time; a video
    loaded before an API model was configured has no comments, and finding
    then uses the description and chapters only.)
    """
    return DEFAULT_COMMENT_LIMIT if has_api_model(settings) else 0


def should_auto_find(
    settings: AppSettings,
    info: VideoInfo,
    tracklist_text: str,
) -> bool:
    """Whether to start a search on its own right after ``info`` loads.

    True only if settings.auto_find_tracklist, has_api_model(settings), the
    box is blank, and info.duration > 0 (skips live streams and premieres).
    """
    return (
        settings.auto_find_tracklist
        and has_api_model(settings)
        and not tracklist_text.strip()
        and info.duration > 0
    )


def check_find_ready(info: VideoInfo | None, settings: AppSettings) -> str | None:
    """Reason a manual "Find with AI" click can't run, or None if it can.

    "Please wait for video info to load before using AI." without a video;
    NEEDS_API_MODEL_MESSAGE without an API model. (DETECT_FORMAT clicks keep
    using check_ai_assist_ready, unchanged.)
    """
    if info is None:
        return VIDEO_NOT_LOADED_MESSAGE
    if not has_api_model(settings):
        return NEEDS_API_MODEL_MESSAGE
    return None


def render_tracklist(tracks: tuple[FoundTrack, ...]) -> str:
    """Render tracks as track-list text matching FIND_TEMPLATE.

    One ``Title - M:SS`` line per track, newline-separated, no trailing
    newline. Minutes are total minutes, so hour-long sets stay parseable
    without %hh%: 3725 s → ``62:05``.
    """
    return "\n".join(
        f"{track.title} - {track.start_seconds // 60}:{track.start_seconds % 60:02d}"
        for track in tracks
    )


def video_sources_log_line(info: VideoInfo, settings: AppSettings) -> LogLine:
    """Logged when a video loads, e.g. "Video info: description, 13 chapters, 20 comments".

    Parts: "description" or "no description"; "N chapter(s)"; "N comment(s)"
    (singular for 1, e.g. "1 chapter"). The comment count is left out when
    the preview didn't request comments, so "0 comments" is never misleading.
    """
    parts = [
        "description" if info.description.strip() else "no description",
        _count(len(info.chapters), "chapter"),
    ]
    if preview_comment_limit(settings):
        parts.append(_count(len(info.comments), "comment"))
    return LogLine("Video info: " + ", ".join(parts))


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


_CANCEL_LOG = {
    CancelReason.STOPPED: "AI: search stopped",
    CancelReason.EDITED: "AI: search stopped because you edited the track list",
    CancelReason.VIDEO_CHANGED: "AI: search stopped because the video changed",
}


class TrackFinderSession:
    """Per-window finder state. Create one per front-end window; not thread-safe.

    Front-ends call it from their UI thread only. Background work gets a
    token from begin() and hands its result back with the same token; stale
    tokens are ignored, which covers Stop, typing, and URL changes.
    """

    def __init__(self) -> None:
        self._last_token = 0
        self._token: int | None = None  # The running search's token.
        self._cache: dict[str, TracklistFindResult] = {}
        self._filled_text: str | None = None  # What the finder wrote, while unedited.
        self._before_fill: FormValues | None = None
        self._banner = ""
        self._hint_dismissed = False

    # ── Searching ───────────────────────────────────────────────────

    @property
    def searching(self) -> bool:
        """True between begin() and complete()/fail()/cancel()."""
        return self._token is not None

    def begin(self, video_id: str) -> int:
        """Start a search for ``video_id``; returns its token.

        Supersedes (silently discards) any search already running. Callers
        then check cached(video_id): if present, call complete() right away
        with it instead of starting background work.
        """
        self._last_token += 1
        self._token = self._last_token
        return self._token

    def cached(self, video_id: str) -> TracklistFindResult | None:
        """The result of an earlier search for this video in this session, if any.

        Only complete() results are cached (any outcome); failures aren't.
        """
        return self._cache.get(video_id)

    def is_current(self, token: int) -> bool:
        """Whether ``token`` belongs to the running search."""
        return self._token is not None and token == self._token

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

        - FOUND: "AI: found N timestamped tracks in <label>" ("1 timestamped
          track" singular), then
          'AI: format set to "<FIND_TEMPLATE>"'
        - UNTIMED: "AI: found song names without timestamps in <label>; add
          timestamps to use it" (warn), values None, no banner
        - NOT_FOUND: "AI: no track list found in the description, chapters
          or comments", values None, no banner

        If the box was filled meanwhile (current.tracklist not blank), FOUND
        is not applied: values None, no banner, log "AI: found a track list,
        but you'd already filled one in; left it unchanged" (warn).
        """
        if not self.is_current(token):
            return None
        self._token = None
        self._cache[video_id] = result

        if result.outcome == FindOutcome.UNTIMED:
            line = LogLine(
                f"AI: found song names without timestamps in {result.source.label}; "
                "add timestamps to use it",
                "warn",
            )
            return FindApplication(None, "", (line,))
        if result.outcome != FindOutcome.FOUND:
            line = LogLine("AI: no track list found in the description, chapters or comments")
            return FindApplication(None, "", (line,))
        if current.tracklist.strip():
            line = LogLine(
                "AI: found a track list, but you'd already filled one in; left it unchanged",
                "warn",
            )
            return FindApplication(None, "", (line,))

        values = FormValues(
            tracklist=render_tracklist(result.tracks),
            template=FIND_TEMPLATE,
            artist=current.artist if current.artist.strip() else result.artist_name,
            album=current.album if current.album.strip() else result.album_name,
        )
        self._before_fill = current
        self._filled_text = values.tracklist
        self._banner = (
            f"✨ Filled by AI from {result.source.label}: "
            f"{_count(len(result.tracks), 'track')}. Check it before downloading."
        )
        log = (
            LogLine(
                f"AI: found {_count(len(result.tracks), 'timestamped track')} "
                f"in {result.source.label}"
            ),
            LogLine(f'AI: format set to "{FIND_TEMPLATE}"'),
        )
        return FindApplication(values, self._banner, log)

    def fail(self, token: int, message: str) -> LogLine | None:
        """Finish a search with an error. None for a stale token.

        Returns "AI: couldn't find a track list: <message>" (error). Front-ends
        log it; a manual click also shows ``message`` as a message box/toast,
        an automatic run only logs.
        """
        if not self.is_current(token):
            return None
        self._token = None
        return LogLine(f"AI: couldn't find a track list: {message}", "error")

    def cancel(self, reason: CancelReason) -> LogLine | None:
        """Cancel the running search; None if nothing was running.

        STOPPED → "AI: search stopped"; EDITED → "AI: search stopped because
        you edited the track list"; VIDEO_CHANGED → "AI: search stopped
        because the video changed". All "warn".
        """
        if self._token is None:
            return None
        self._token = None
        return LogLine(_CANCEL_LOG[reason], "warn")

    # ── After filling ───────────────────────────────────────────────

    @property
    def ai_filled(self) -> bool:
        """True while the box still holds exactly what the finder wrote."""
        return self._filled_text is not None

    @property
    def banner(self) -> str:
        """Banner text to show now, or "" (hidden)."""
        return self._banner if self.ai_filled else ""

    def template_set_by_ai(self, template: str) -> bool:
        """Show TEMPLATE_SET_BY_AI_TEXT by the format field: ai_filled and
        ``template`` still equals FIND_TEMPLATE."""
        return self.ai_filled and template.strip() == FIND_TEMPLATE

    def on_tracklist_edited(self, text: str) -> LogLine | None:
        """Call on every track list text change (user typing or programmatic).

        While searching, a nonblank ``text`` cancels with EDITED and returns
        that log line. Text equal to the AI-filled text is not an edit (so
        writing FindApplication.values is safe). Any other change ends
        ai_filled and hides the banner. Returns None unless it cancelled.
        """
        line = None
        if self.searching and text.strip():
            line = self.cancel(CancelReason.EDITED)
        # Compared stripped: editors may add or drop a trailing newline.
        if self._filled_text is not None and text.strip() != self._filled_text.strip():
            self._end_fill()
        return line

    def dismiss_banner(self) -> None:
        """Hide the banner (the ✕). ai_filled and Undo are unaffected."""
        self._banner = ""

    def undo(self) -> FormValues | None:
        """Values from before the fill, or None if nothing can be undone.

        Available while ai_filled. Ends ai_filled and hides the banner.
        """
        if not self.ai_filled:
            return None
        values = self._before_fill
        self._end_fill()
        return values

    def on_video_changed(self) -> tuple[FormValues | None, LogLine | None]:
        """Call when the URL changes or the video is cleared.

        Cancels a running search (VIDEO_CHANGED log line, else None). If the
        box is still ai_filled, returns the pre-fill values to restore (the
        list belonged to the old video), like undo(); otherwise None.
        """
        line = self.cancel(CancelReason.VIDEO_CHANGED)
        return self.undo(), line

    def _end_fill(self) -> None:
        self._filled_text = None
        self._before_fill = None
        self._banner = ""

    # ── Hint ────────────────────────────────────────────────────────

    def show_api_hint(
        self,
        settings: AppSettings,
        info: VideoInfo | None,
        tracklist_text: str,
    ) -> bool:
        """Show API_HINT_TEXT: a video is loaded, the box is blank, there's no
        API model, and the hint wasn't dismissed in this session."""
        return (
            info is not None
            and not tracklist_text.strip()
            and not has_api_model(settings)
            and not self._hint_dismissed
        )

    def dismiss_api_hint(self) -> None:
        """Hide the hint for the rest of the session."""
        self._hint_dismissed = True
