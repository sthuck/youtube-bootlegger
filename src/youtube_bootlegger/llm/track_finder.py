"""AI track-list finder: locate a set list in a video's description, chapters or comments.

Unlike ``tracklist`` (which infers a template for a list the user already
has), this finds the list itself. The AI only picks and cleans entries; the
app validates every entry against the source text and writes the track list
in its own format, so the AI never chooses the template.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from ..core.settings import AppSettings
from ..core.video_info import VideoInfo
from .http import LlmError, PostJson, post_json

SCHEMA_NAME = "tracklist_discovery"

# Bounds on source text sent to the AI. A source over its bound keeps its
# leading whole lines; sources past the total budget are dropped, last first.
MAX_SOURCE_CHARS = 8_000
MAX_TOTAL_SOURCE_CHARS = 40_000


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
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError
