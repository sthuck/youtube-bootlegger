"""Video information fetching using yt-dlp."""

import json
import subprocess
from dataclasses import dataclass

import yt_dlp

from .exceptions import ValidationError
from .settings import AppSettings, get_settings


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
    """

    video_id: str
    title: str
    channel: str
    duration: int
    duration_string: str
    thumbnail_url: str
    view_count: int | None = None
    upload_date: str | None = None

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
        return _fetch_video_info_external(url, settings)
    return _fetch_video_info_library(url)


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

    thumbnails = info.get("thumbnails", [])
    thumbnail_url = _get_best_thumbnail(thumbnails)

    return VideoInfo(
        video_id=info.get("id", ""),
        title=info.get("title", "Unknown Title"),
        channel=info.get("channel", info.get("uploader", "Unknown Channel")),
        duration=duration,
        duration_string=duration_string,
        thumbnail_url=thumbnail_url,
        view_count=info.get("view_count"),
        upload_date=info.get("upload_date"),
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


def _get_best_thumbnail(thumbnails: list[dict]) -> str:
    """Get the best quality thumbnail URL."""
    if not thumbnails:
        return ""

    sorted_thumbnails = sorted(
        [t for t in thumbnails if t.get("url")],
        key=lambda t: (t.get("preference", 0), t.get("width", 0)),
        reverse=True,
    )

    for thumb in sorted_thumbnails:
        url = thumb.get("url", "")
        if "maxresdefault" in url or "hqdefault" in url or "mqdefault" in url:
            return url

    return sorted_thumbnails[0].get("url", "") if sorted_thumbnails else ""
