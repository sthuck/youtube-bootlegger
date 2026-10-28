"""Fetch a video's leading YouTube comments, e.g. to look for a set list.

Comments are a separate, slower request from fetch_video_info, so the video
preview stays fast and comments are only fetched when needed.
"""

from dataclasses import dataclass

from .exceptions import ValidationError
from .settings import AppSettings, get_settings
from .ytdlp_metadata import fetch_info_dict

DEFAULT_COMMENT_LIMIT = 20


@dataclass(frozen=True)
class VideoComment:
    """A top-level comment's text, with yt-dlp's comment ID."""

    comment_id: str
    text: str


def fetch_video_comments(
    url: str,
    settings: AppSettings | None = None,
    *,
    limit: int = DEFAULT_COMMENT_LIMIT,
) -> tuple[VideoComment, ...]:
    """Fetch up to `limit` top-level comments in YouTube's Top order.

    Replies and blank comments are skipped. YouTube's ranking is dynamic, so
    repeated calls may return different comments; they are not re-sorted.
    Zero returns no comments without a request. Blocks, so run it off the UI
    thread.

    Raises:
        ValidationError: If the limit is invalid or the video can't be fetched.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValidationError("Comment limit must be a nonnegative integer")
    if limit == 0:
        return ()
    info = fetch_info_dict(url, settings or get_settings(), comment_limit=limit)
    return parse_comments(info.get("comments"), limit)


def parse_comments(comments, limit: int) -> tuple[VideoComment, ...]:
    """Keep up to `limit` nonblank top-level comments, in their given order."""
    result = []
    for comment in comments or []:
        if len(result) >= limit:
            break
        if not isinstance(comment, dict) or comment.get("parent") not in (None, "root"):
            continue
        text = comment.get("text")
        if isinstance(text, str) and text.strip():
            result.append(VideoComment(str(comment.get("id") or ""), text))
    return tuple(result)
