"""Video information fetching using yt-dlp."""

from dataclasses import dataclass

import yt_dlp

from .exceptions import ValidationError


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


def fetch_video_info(url: str) -> VideoInfo:
    """Fetch video information from YouTube URL.

    Args:
        url: YouTube video URL.

    Returns:
        VideoInfo object with video details.

    Raises:
        ValidationError: If the URL is invalid or video unavailable.
    """
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
