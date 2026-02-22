"""Tracklist parsing logic."""

import re

from ..models import Track
from ..utils import is_valid_timestamp, parse_timestamp_to_seconds
from .exceptions import ParseError

TRACK_LINE_PATTERN = re.compile(r"^(.+?)\s*-\s*(\d+:?\d*:\d{2})$")


def parse_tracklist(text: str) -> list[Track]:
    """Parse tracklist text into Track objects.

    Expected format (one per line):
        songName - mm:ss
        songName - hh:mm:ss

    Args:
        text: The tracklist text to parse.

    Returns:
        List of Track objects with calculated end times.

    Raises:
        ParseError: If the format is invalid or no tracks found.
    """
    if not text or not text.strip():
        raise ParseError("Tracklist is empty")

    lines = text.strip().split("\n")
    tracks: list[Track] = []
    errors: list[str] = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        match = TRACK_LINE_PATTERN.match(line)
        if not match:
            errors.append(f"Line {i}: Invalid format. Expected 'Song Name - mm:ss'")
            continue

        name = match.group(1).strip()
        timestamp = match.group(2).strip()

        if not is_valid_timestamp(timestamp):
            errors.append(f"Line {i}: Invalid timestamp '{timestamp}'")
            continue

        try:
            start_seconds = parse_timestamp_to_seconds(timestamp)
        except ValueError:
            errors.append(f"Line {i}: Could not parse timestamp '{timestamp}'")
            continue

        tracks.append(Track(name=name, start_seconds=start_seconds))

    if errors:
        raise ParseError("\n".join(errors))

    if not tracks:
        raise ParseError("No valid tracks found in tracklist")

    tracks.sort(key=lambda t: t.start_seconds)

    tracks_with_end_times: list[Track] = []
    for i, track in enumerate(tracks):
        if i < len(tracks) - 1:
            end_seconds = tracks[i + 1].start_seconds
            tracks_with_end_times.append(track.with_end_time(end_seconds))
        else:
            tracks_with_end_times.append(track)

    return tracks_with_end_times
