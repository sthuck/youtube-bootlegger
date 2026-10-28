"""Video information fetching using yt-dlp."""

import math
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from urllib.parse import urlparse

from .settings import AppSettings, get_settings
from .ytdlp_metadata import fetch_info_dict

# How many of the best-ranked thumbnails to consider before the fallback.
MAX_THUMBNAIL_CANDIDATES = 4
THUMBNAIL_PROBE_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class VideoChapter:
    """A named chapter, in seconds. end_seconds is None when yt-dlp omits it."""

    title: str
    start_seconds: float
    end_seconds: float | None = None


@dataclass(frozen=True)
class VideoInfo:
    """Information about a YouTube video.

    Attributes:
        video_id: YouTube video ID.
        title: Video title.
        channel: Channel name.
        duration: Duration in seconds.
        duration_string: Human-readable duration.
        thumbnail_url: URL to video thumbnail.
        view_count: Number of views.
        upload_date: Upload date string (YYYYMMDD).
        thumbnail_candidates: Thumbnail URLs to try, best first.
        description: Video description text.
        chapters: Valid named chapters in video order. yt-dlp may derive these
            from timestamps in the description, so they aren't always songs.
    """

    video_id: str
    title: str
    channel: str
    duration: int
    duration_string: str
    thumbnail_url: str
    view_count: int | None = None
    upload_date: str | None = None
    thumbnail_candidates: tuple[str, ...] = ()
    description: str = ""
    chapters: tuple[VideoChapter, ...] = ()

    @property
    def formatted_views(self) -> str:
        """Format view count for display."""
        if self.view_count is None:
            return "Unknown views"
        if self.view_count >= 1_000_000:
            return f"{self.view_count / 1_000_000:.1f}M views"
        if self.view_count >= 1_000:
            return f"{self.view_count / 1_000:.1f}K views"
        return f"{self.view_count} views"

    @property
    def formatted_date(self) -> str:
        """Format upload date for display."""
        if not self.upload_date or len(self.upload_date) != 8:
            return ""
        year = self.upload_date[:4]
        month = self.upload_date[4:6]
        day = self.upload_date[6:8]
        return f"{year}-{month}-{day}"


def fetch_video_info(url: str, settings: AppSettings | None = None) -> VideoInfo:
    """Fetch video information from YouTube URL.

    Args:
        url: YouTube video URL.
        settings: Application settings. Defaults to the shared singleton.

    Returns:
        VideoInfo object with video details.

    Raises:
        ValidationError: If the URL is invalid or video unavailable.
    """
    info = fetch_info_dict(url, settings or get_settings())
    return resolve_thumbnail(_build_video_info(info))


def _build_video_info(info: dict) -> VideoInfo:
    """Build a VideoInfo from a yt-dlp info dict (Python API or CLI JSON)."""
    duration = info.get("duration", 0) or 0
    duration_string = _format_duration(duration)

    video_id = info.get("id", "")
    candidates = thumbnail_candidates(info.get("thumbnails") or [], video_id)

    return VideoInfo(
        video_id=video_id,
        title=info.get("title", "Unknown Title"),
        channel=info.get("channel", info.get("uploader", "Unknown Channel")),
        duration=duration,
        duration_string=duration_string,
        thumbnail_url=candidates[0] if candidates else "",
        view_count=info.get("view_count"),
        upload_date=info.get("upload_date"),
        thumbnail_candidates=tuple(candidates),
        description=info.get("description") or "",
        chapters=parse_chapters(info.get("chapters")),
    )


def _seconds(value) -> float | None:
    """Return value as finite, nonnegative seconds, or None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and value >= 0:
            return float(value)
    return None


def parse_chapters(chapters) -> tuple[VideoChapter, ...]:
    """Keep yt-dlp chapters that have a name and a valid time range."""
    result = []
    for chapter in chapters or []:
        if not isinstance(chapter, dict):
            continue
        title = chapter.get("title")
        start = _seconds(chapter.get("start_time"))
        end = _seconds(chapter.get("end_time"))
        if not isinstance(title, str) or not title.strip() or start is None:
            continue
        if end is not None and end <= start:
            continue
        result.append(VideoChapter(title, start, end))
    return tuple(result)


def _format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds <= 0:
        return "Live"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _is_jpeg(url: str) -> bool:
    return urlparse(url).path.lower().endswith((".jpg", ".jpeg"))


def thumbnail_candidates(thumbnails: list[dict], video_id: str) -> list[str]:
    """Rank thumbnail URLs best-first for preview and cover art.

    yt-dlp lists many *guessed* YouTube thumbnail URLs (e.g. maxresdefault)
    that 404 for older or low-resolution videos, so this only ranks; use
    resolve_thumbnail() to pick one that exists. JPEGs come first because
    WebP cover art isn't shown by many music players. hqdefault.jpg, which
    YouTube serves for every video, is always the final fallback.
    """
    usable = [t for t in thumbnails if t.get("url")]
    ranked = sorted(
        usable,
        key=lambda t: (
            _is_jpeg(t["url"]),
            t.get("preference") or 0,
            t.get("width") or 0,
        ),
        reverse=True,
    )
    urls = [t["url"] for t in ranked[:MAX_THUMBNAIL_CANDIDATES]]
    if video_id:
        urls.append(f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg")
    return list(dict.fromkeys(urls))


def _url_exists(url: str) -> bool:
    """Return True if a HEAD request for the URL succeeds."""
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=THUMBNAIL_PROBE_TIMEOUT_SECONDS) as response:
            return response.status == 200
    except OSError:
        return False


def resolve_thumbnail(
    info: VideoInfo,
    url_exists: Callable[[str], bool] | None = None,
) -> VideoInfo:
    """Return info with thumbnail_url set to the first candidate that exists.

    Leaves info unchanged when no candidate is reachable (e.g. offline).
    """
    url_exists = url_exists or _url_exists
    for url in info.thumbnail_candidates:
        if url_exists(url):
            return info if url == info.thumbnail_url else replace(info, thumbnail_url=url)
    return info
