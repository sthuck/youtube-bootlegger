"""AI track-list finder: locate a set list in a video's description, chapters or comments.

Unlike ``tracklist`` (which infers a template for a list the user already
has), this finds the list itself. The AI only picks and cleans entries; the
app validates every entry against the source text and writes the track list
in its own format, so the AI never chooses the template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from ..core.settings import AppSettings, LlmProvider
from ..core.video_info import VideoInfo
from .client import complete_structured
from .config import endpoint_from_settings
from .http import LlmError, PostJson, post_json
from .prompt import FIND_SYSTEM_PROMPT, build_find_prompt

SCHEMA_NAME = "tracklist_discovery"

# Bounds on source text sent to the AI. A source over its bound keeps its
# leading whole lines; sources past the total budget are dropped, last first.
MAX_SOURCE_CHARS = 8_000
MAX_TOTAL_SOURCE_CHARS = 40_000

NEEDS_API_MODEL_ERROR = "Finding a track list needs an API model, not ChatGPT Lite."

# M:SS, MM:SS, MMM:SS or H:MM:SS, not inside a longer run of digits.
_TIMESTAMP_RE = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,3}):(\d{2})(?![\d:])")


class TracklistFindError(LlmError):
    """Raised when finding fails: not configured, network/provider error,
    unparseable output, or a response that fails validation."""


@dataclass(frozen=True)
class TrackSource:
    """One piece of text the AI may take a track list from.

    Attributes:
        source_id: Stable ID used in the prompt and response: ``description``,
            ``chapters`` or ``comment:<n>`` (n counts from 1 in YouTube's order).
        label: How the log names it: "the description", "the chapters",
            "comment #3".
        text: The (possibly truncated) text sent to the AI. Chapters are
            rendered by the app, one ``M:SS Title`` line per chapter
            (``H:MM:SS`` past an hour), with fractional starts floored.
    """

    source_id: str
    label: str
    text: str


class FoundEntryResponse(BaseModel):
    """One track as the AI returns it."""

    title: str = Field(description="Cleaned song title, without numbering or timestamp.")
    start_seconds: int = Field(description="Start time in whole seconds, from the source line.")
    source_line: str = Field(description="The exact source line this track came from.")


class TracklistDiscovery(BaseModel):
    """Structured AI response. Empty strings mean "none" (no nulls in the schema)."""

    source_id: str = Field(description='Source of the chosen timestamped list, or "".')
    entries: list[FoundEntryResponse] = Field(description="Tracks in order; empty if none.")
    untimed_source_id: str = Field(
        description='When the only list found has no timestamps, its source; else "".'
    )
    artist_name: str = Field(description='Performer or band name, or "".')
    album_name: str = Field(description='Album or release title, or "".')


class FindOutcome(StrEnum):
    """What the finder concluded."""

    FOUND = "found"  # A validated, timestamped list.
    UNTIMED = "untimed"  # Only song names without timestamps; nothing to fill.
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class FoundTrack:
    """A validated track: nonempty title, whole-second start."""

    title: str
    start_seconds: int


@dataclass(frozen=True)
class TracklistFindResult:
    """Validated finder result.

    Attributes:
        outcome: FOUND, UNTIMED or NOT_FOUND.
        source: For FOUND, the list's source; for UNTIMED, the untimed
            list's source; None for NOT_FOUND.
        tracks: For FOUND, at least one track with strictly increasing starts
            below the video duration; empty otherwise.
        artist_name: Stripped; "" if unknown.
        album_name: Stripped; "" if unknown.
    """

    outcome: FindOutcome
    source: TrackSource | None = None
    tracks: tuple[FoundTrack, ...] = ()
    artist_name: str = ""
    album_name: str = ""


def build_track_sources(info: VideoInfo) -> tuple[TrackSource, ...]:
    """Return the non-empty sources for ``info``, bounded as described above.

    Order: description, chapters, then comments in YouTube's order. A video
    with no description, chapters or comments yields ().
    """
    candidates = [("description", "the description", info.description)]
    if info.chapters:
        chapter_lines = (
            f"{format_timestamp(int(chapter.start_seconds))} {_one_line(chapter.title)}"
            for chapter in info.chapters
        )
        candidates.append(("chapters", "the chapters", "\n".join(chapter_lines)))
    candidates += [
        (f"comment:{n}", f"comment #{n}", comment.text)
        for n, comment in enumerate(info.comments, start=1)
    ]

    sources = []
    total = 0
    for source_id, label, text in candidates:
        text = _truncate_lines(text.strip(), MAX_SOURCE_CHARS)
        if not text:
            continue
        if total + len(text) > MAX_TOTAL_SOURCE_CHARS:
            break
        total += len(text)
        sources.append(TrackSource(source_id, label, text))
    return tuple(sources)


def format_timestamp(seconds: int) -> str:
    """``M:SS``, or ``H:MM:SS`` from one hour."""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _truncate_lines(text: str, limit: int) -> str:
    """Keep the leading whole lines of ``text`` that fit in ``limit`` characters."""
    if len(text) <= limit:
        return text
    kept = []
    size = 0
    for line in text.splitlines():
        size += len(line) + (1 if kept else 0)
        if size > limit:
            break
        kept.append(line)
    # A single line longer than the limit is cut rather than dropped.
    return "\n".join(kept) if kept else text[:limit]


def find_tracklist(
    settings: AppSettings,
    info: VideoInfo,
    *,
    http_post: PostJson = post_json,
) -> TracklistFindResult:
    """Ask the configured API model to find a track list for ``info``.

    Blocking; run it off the UI thread. A video with no sources returns
    NOT_FOUND without calling the AI.

    Raises:
        TracklistFindError: If the provider isn't an API model (including
            ChatGPT Lite), the request fails, or the response is invalid
            (see validate_discovery).
    """
    if settings.llm_provider == LlmProvider.CHATGPT_LITE:
        raise TracklistFindError(NEEDS_API_MODEL_ERROR)
    try:
        endpoint = endpoint_from_settings(settings)
    except LlmError as exc:
        raise TracklistFindError(str(exc)) from exc

    sources = build_track_sources(info)
    if not sources:
        return TracklistFindResult(FindOutcome.NOT_FOUND)

    try:
        response = complete_structured(
            endpoint,
            system=FIND_SYSTEM_PROMPT,
            user=build_find_prompt(info.title, info.duration, sources),
            output=TracklistDiscovery,
            schema_name=SCHEMA_NAME,
            http_post=http_post,
        )
    except LlmError as exc:
        raise TracklistFindError(str(exc)) from exc
    return validate_discovery(response, sources, info.duration)


def validate_discovery(
    response: TracklistDiscovery,
    sources: tuple[TrackSource, ...],
    duration_seconds: int,
) -> TracklistFindResult:
    """Turn an AI response into a result, enforcing the contract.

    - No source_id and no entries: UNTIMED if untimed_source_id names a known
      source, else NOT_FOUND.
    - Otherwise FOUND, and all of these must hold: source_id is a known
      source; there is at least one entry; each source_line is a line of
      that source (compared after stripping whitespace) containing a
      timestamp (``M:SS``, ``MM:SS`` or ``H:MM:SS``) equal to start_seconds;
      titles are nonempty after stripping; starts are nonnegative, strictly
      increasing, and below duration_seconds when it is positive. A list may
      start after 0:00.

    Raises:
        TracklistFindError: With a short reason, if a FOUND response breaks
            any rule (e.g. "AI returned a line that isn't in comment #3").
    """
    by_id = {source.source_id: source for source in sources}
    artist = response.artist_name.strip()
    album = response.album_name.strip()
    source_id = response.source_id.strip()

    if not source_id and not response.entries:
        untimed = by_id.get(response.untimed_source_id.strip())
        if untimed is None:
            return TracklistFindResult(FindOutcome.NOT_FOUND, artist_name=artist, album_name=album)
        return TracklistFindResult(
            FindOutcome.UNTIMED, untimed, artist_name=artist, album_name=album,
        )

    source = by_id.get(source_id)
    if source is None:
        raise TracklistFindError(f"AI returned an unknown source: {source_id!r}")
    if not response.entries:
        raise TracklistFindError(f"AI returned no tracks from {source.label}")

    lines = {_one_line(line) for line in source.text.splitlines()}
    tracks = []
    for entry in response.entries:
        line = _one_line(entry.source_line)
        if line not in lines:
            raise TracklistFindError(f"AI returned a line that isn't in {source.label}: {line!r}")
        if entry.start_seconds not in _line_timestamps(line):
            raise TracklistFindError(
                f"AI returned a start time that doesn't match its line in {source.label}: {line!r}"
            )
        title = _one_line(entry.title)
        if not title:
            raise TracklistFindError(f"AI returned a track without a title: {line!r}")
        if tracks and entry.start_seconds <= tracks[-1].start_seconds:
            raise TracklistFindError("AI returned track start times that don't increase")
        if duration_seconds > 0 and entry.start_seconds >= duration_seconds:
            raise TracklistFindError(f"AI returned a track starting after the video ends: {line!r}")
        tracks.append(FoundTrack(title, entry.start_seconds))

    return TracklistFindResult(
        FindOutcome.FOUND, source, tuple(tracks), artist_name=artist, album_name=album,
    )


def _line_timestamps(line: str) -> set[int]:
    """Every valid timestamp in ``line``, in seconds."""
    found = set()
    for match in _TIMESTAMP_RE.finditer(line):
        hours, minutes, seconds = match.groups()
        if int(seconds) >= 60 or (hours is not None and int(minutes) >= 60):
            continue
        found.add(int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds))
    return found
