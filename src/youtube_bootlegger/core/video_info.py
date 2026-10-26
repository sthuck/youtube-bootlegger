"""Video information fetching using yt-dlp."""

import json
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from urllib.parse import urlparse

import yt_dlp

from .exceptions import ValidationError
from .settings import AppSettings, get_settings

# How many of the best-ranked thumbnails to consider before the fallback.
MAX_THUMBNAIL_CANDIDATES = 4
THUMBNAIL_PROBE_TIMEOUT_SECONDS = 5


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
    settings = settings or get_settings()
    if settings.use_external_ytdlp:
        info = _fetch_video_info_external(url, settings)
    else:
        info = _fetch_video_info_library(url)
    return resolve_thumbnail(info)


def _fetch_video_info_library(url: str) -> VideoInfo:
    """Fetch video info using the bundled yt-dlp Python library."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                raise ValidationError("Could not fetch video information")

            return _build_video_info(info)

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        if "private" in error_msg:
            raise ValidationError("This video is private") from e
        if "unavailable" in error_msg or "not available" in error_msg:
            raise ValidationError("This video is unavailable") from e
        if "removed" in error_msg:
            raise ValidationError("This video has been removed") from e
        raise ValidationError(f"Could not fetch video: {e}") from e
    except Exception as e:
        raise ValidationError(f"Error fetching video info: {e}") from e


def _fetch_video_info_external(url: str, settings: AppSettings) -> VideoInfo:
    """Fetch video info by invoking the external yt-dlp executable."""
    command = settings.resolved_ytdlp_command()
    cmd = [command, "-j", "--no-warnings", "--skip-download", url]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as e:
        raise ValidationError(
            f"yt-dlp executable not found: '{command}'. Check the yt-dlp path in Settings."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise ValidationError("Timed out fetching video information") from e

    if result.returncode != 0:
        error_msg = (result.stderr or result.stdout or "").strip()
        lowered = error_msg.lower()
        if "private" in lowered:
            raise ValidationError("This video is private")
        if "unavailable" in lowered or "not available" in lowered:
            raise ValidationError("This video is unavailable")
        if "removed" in lowered:
            raise ValidationError("This video has been removed")
        raise ValidationError(f"Could not fetch video: {error_msg or 'unknown error'}")

    try:
        info = json.loads(result.stdout.splitlines()[0])
    except (json.JSONDecodeError, IndexError) as e:
        raise ValidationError("Could not parse yt-dlp output") from e

    return _build_video_info(info)


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
    )


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
