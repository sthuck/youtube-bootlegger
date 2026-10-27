"""Fetch track-list source material without downloading media or calling an LLM."""

import json
import math
import subprocess
from dataclasses import dataclass

import yt_dlp

from .exceptions import ValidationError
from .settings import AppSettings, get_settings

DEFAULT_COMMENT_LIMIT = 20
EXTERNAL_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class VideoChapter:
    title: str
    start_seconds: float
    end_seconds: float | None = None


@dataclass(frozen=True)
class VideoComment:
    comment_id: str
    text: str


@dataclass(frozen=True)
class VideoSources:
    video_id: str
    title: str
    description: str = ""
    chapters: tuple[VideoChapter, ...] = ()
    comments: tuple[VideoComment, ...] = ()


def fetch_video_sources(
    url: str,
    settings: AppSettings | None = None,
    *,
    comment_limit: int = DEFAULT_COMMENT_LIMIT,
) -> VideoSources:
    """Fetch description, named chapters and up to N YouTube Top comments.

    Honors the shared external-yt-dlp setting. Replies are excluded and YouTube's
    order is preserved. Zero disables comment fetching. Missing description,
    chapters or disabled/empty comments produce empty fields. Extraction failures
    raise ValidationError. No AI calls or media/sidecar downloads are performed.

    This blocking function belongs on a background thread. Library socket/retry
    limits are not a total deadline; the external process has a 120s deadline.
    """
    if isinstance(comment_limit, bool) or not isinstance(comment_limit, int) or comment_limit < 0:
        raise ValidationError("Comment limit must be a nonnegative integer")
    settings = settings or get_settings()
    if settings.use_external_ytdlp:
        info = _fetch_sources_external(url, settings, comment_limit)
    else:
        info = _fetch_sources_library(url, comment_limit)
    if not isinstance(info, dict) or info.get("_type") in ("playlist", "multi_video"):
        raise ValidationError("Expected information for a single video")
    return _build_video_sources(info, comment_limit)


def _fetch_sources_library(url: str, comment_limit: int) -> dict:
    options = {
        "quiet": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
        "getcomments": bool(comment_limit),
        "extractor_args": {"youtube": {
            "comment_sort": ["top"],
            "max_comments": [str(comment_limit), str(comment_limit), "0", "0"],
        }},
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            if isinstance(info, dict) and info.get("_type") not in ("playlist", "multi_video"):
                # download=False leaves comment extraction deferred in yt-dlp.
                if comment_limit:
                    ydl.post_extract(info)
            return info
    except (yt_dlp.utils.DownloadError, yt_dlp.utils.ExtractorError, OSError) as exc:
        raise ValidationError(f"Could not fetch video sources: {exc}") from exc


def _fetch_sources_external(url: str, settings: AppSettings, comment_limit: int) -> dict:
    command = settings.resolved_ytdlp_command()
    args = [
        command, "--ignore-config", "--no-playlist", "--skip-download",
        "--dump-single-json", "--socket-timeout", "15", "--retries", "1",
        "--extractor-retries", "1",
    ]
    if comment_limit:
        args += [
            "--write-comments", "--extractor-args",
            f"youtube:comment_sort=top;max_comments={comment_limit},{comment_limit},0,0",
        ]
    try:
        result = subprocess.run(
            [*args, "--", url], capture_output=True, text=True, encoding="utf-8",
            timeout=EXTERNAL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise ValidationError(
            f"yt-dlp executable not found: '{command}'. Check the yt-dlp path in Settings."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValidationError("Timed out fetching video sources") from exc
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"Could not run yt-dlp: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise ValidationError(f"Could not fetch video sources: {detail}")
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Could not parse yt-dlp video sources output") from exc


def _seconds(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(value) and value >= 0:
            return float(value)
    return None


def _build_video_sources(info: dict, comment_limit: int) -> VideoSources:
    """Normalize either backend's JSON while preserving source text and order."""
    chapters = []
    for chapter in info.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        title = chapter.get("title")
        start = _seconds(chapter.get("start_time"))
        end = _seconds(chapter.get("end_time"))
        if not isinstance(title, str) or not title.strip() or start is None:
            continue
        if end is not None and end <= start:
            continue
        chapters.append(VideoChapter(title, start, end))

    comments = []
    for comment in info.get("comments") or []:
        if len(comments) >= comment_limit:
            break
        if not isinstance(comment, dict) or comment.get("parent") not in (None, "root"):
            continue
        text = comment.get("text")
        if isinstance(text, str) and text.strip():
            comments.append(VideoComment(str(comment.get("id") or ""), text))
    return VideoSources(
        video_id=info.get("id") or "",
        title=info.get("title") or "",
        description=info.get("description") or "",
        chapters=tuple(chapters),
        comments=tuple(comments),
    )
