"""Input validation utilities."""

import re

YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/live/)[\w\-]+"
)

TIMESTAMP_PATTERN = re.compile(r"^(\d+:)?\d{1,2}:\d{2}$")

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_valid_youtube_url(url: str) -> bool:
    """Check if URL is a valid YouTube URL.

    Args:
        url: The URL to validate.

    Returns:
        True if the URL is a valid YouTube URL.
    """
    if not url or not isinstance(url, str):
        return False
    return bool(YOUTUBE_URL_PATTERN.match(url.strip()))


def is_valid_timestamp(timestamp: str) -> bool:
    """Check if timestamp is in valid mm:ss or hh:mm:ss format.

    Args:
        timestamp: The timestamp string to validate.

    Returns:
        True if the timestamp is valid.
    """
    if not timestamp or not isinstance(timestamp, str):
        return False
    return bool(TIMESTAMP_PATTERN.match(timestamp.strip()))


def sanitize_filename(name: str) -> str:
    """Remove/replace invalid filename characters.

    Args:
        name: The filename to sanitize.

    Returns:
        A sanitized filename safe for all operating systems.
    """
    sanitized = INVALID_FILENAME_CHARS.sub("_", name)
    sanitized = sanitized.strip(". ")
    if not sanitized:
        sanitized = "untitled"
    return sanitized
