"""Fetch yt-dlp metadata for one video by running the yt-dlp executable.

This is the only place that asks yt-dlp for metadata.
"""

import json
import subprocess

from .exceptions import ValidationError
from .settings import AppSettings, format_ytdlp_age_or_cookie_error
from .ytdlp_extra_args import option_error, youtube_extractor_args

METADATA_TIMEOUT_SECONDS = 30
# Comment extraction pages through many extra requests.
COMMENTS_TIMEOUT_SECONDS = 120
COMMENTS_SOCKET_TIMEOUT_SECONDS = 15


def fetch_info_dict(url: str, settings: AppSettings, *, comment_limit: int = 0) -> dict:
    """Return yt-dlp's info dict for a single video without downloading media.

    Args:
        url: Video URL. Playlist parameters are ignored.
        settings: Which yt-dlp to run, and its options.
        comment_limit: When positive, also fetch up to this many top-level
            comments into info["comments"], in YouTube's Top order, in the
            same request. If only the comments fail, the metadata is still
            returned, without comments.

    Raises:
        ValidationError: If the video can't be fetched or isn't a single video.
    """
    try:
        return _fetch(url, settings, comment_limit)
    except ValidationError:
        if not comment_limit:
            raise
        # Comments are optional: retry once for the video's metadata alone,
        # which also reports the real error if the video itself failed.
        return _fetch(url, settings, 0)


def _fetch(url: str, settings: AppSettings, comment_limit: int) -> dict:
    info = _fetch_external(url, settings, comment_limit)
    if not _is_single_video(info):
        raise ValidationError("Expected information for a single video")
    return info


def _is_single_video(info) -> bool:
    return isinstance(info, dict) and info.get("_type") not in ("playlist", "multi_video")


def _max_comments(limit: int) -> list[str]:
    # yt-dlp's max_comments is: total, parents, replies, replies per thread.
    # Zero replies makes the total apply to top-level comments only.
    return [str(limit), str(limit), "0", "0"]


def _comment_extractor_args(settings: AppSettings, comment_limit: int) -> dict[str, list[str]]:
    """YouTube extractor args for comments, keeping any from the extra options.

    yt-dlp replaces, not merges, a second set of args for the same site.
    """
    extra = youtube_extractor_args(settings.ytdlp_extra_cli_args())
    return {**extra, "comment_sort": ["top"], "max_comments": _max_comments(comment_limit)}


def _fetch_external(url: str, settings: AppSettings, comment_limit: int):
    result = _run_external(url, settings, comment_limit)
    if result.returncode != 0:
        raise _fetch_error((result.stderr or result.stdout or "").strip(), settings)

    try:
        return json.loads(result.stdout)
    except ValueError as e:
        hint = " Check Extra yt-dlp options in Settings." if settings.ytdlp_extra_args.strip() else ""
        raise ValidationError("yt-dlp did not return valid video information." + hint) from e


def _run_external(url: str, settings: AppSettings, comment_limit: int):
    command = settings.resolved_ytdlp_command()
    cmd = [
        command,
        *settings.ytdlp_config_cli_args(),
        "--dump-single-json",
        "--no-warnings",
        "--no-playlist",
        "--skip-download",
        *settings.ytdlp_cookie_cli_args(),
        *settings.ytdlp_tool_cli_args(),
    ]
    timeout = METADATA_TIMEOUT_SECONDS
    if comment_limit:
        cmd += [
            "--write-comments",
            "--socket-timeout", str(COMMENTS_SOCKET_TIMEOUT_SECONDS),
            "--retries", "1",
            "--extractor-retries", "1",
            "--extractor-args",
            "youtube:" + ";".join(
                f"{key}={','.join(value.replace(',', r'\,') for value in values)}"
                for key, values in _comment_extractor_args(settings, comment_limit).items()
            ),
        ]
        timeout = COMMENTS_TIMEOUT_SECONDS
    cmd += ["--", url]

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise ValidationError(
            f"yt-dlp executable not found: '{command}'. Check the yt-dlp path in Settings."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise ValidationError("Timed out fetching video information") from e
    except (OSError, UnicodeError) as e:
        raise ValidationError(f"Could not run yt-dlp: {e}") from e


def _fetch_error(message: str, settings: AppSettings) -> ValidationError:
    """Turn a yt-dlp failure message into a user-facing error."""
    friendly = option_error(message, settings.ytdlp_extra_args) or (
        format_ytdlp_age_or_cookie_error(message, settings)
    )
    if friendly:
        return ValidationError(friendly)
    lowered = message.lower()
    if "private" in lowered:
        return ValidationError("This video is private")
    if "unavailable" in lowered or "not available" in lowered:
        return ValidationError("This video is unavailable")
    if "removed" in lowered:
        return ValidationError("This video has been removed")
    return ValidationError(f"Could not fetch video: {message or 'unknown error'}")
