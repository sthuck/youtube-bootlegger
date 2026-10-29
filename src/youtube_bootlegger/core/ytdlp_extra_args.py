"""Extra yt-dlp options set in Settings, such as a proxy or a rate limit.

The text is split like a shell command line, except that backslashes are kept
as typed so Windows paths work; quote values that contain spaces. yt-dlp's own
parser checks it, which also turns it into YoutubeDL options for library mode.
"""

import contextlib
import io
import optparse
import shlex
from typing import Any

import yt_dlp

from .exceptions import ValidationError

EXTRA_ARGS_LABEL = "Extra yt-dlp options"

# YoutubeDL options the app sets itself or reads back: where the file goes,
# its format and post-processing, and what yt-dlp prints.
_RESERVED_OPTIONS = frozenset({
    "outtmpl", "paths", "format", "postprocessors", "final_ext", "download_archive",
    "quiet", "noprogress", "progress_template", "forceprint", "print_to_file",
    "forcejson", "dump_single_json", "extract_flat", "simulate", "skip_download",
})
# Options that have a setting of their own.
_SETTING_OPTIONS = {
    "ffmpeg_location": "set the ffmpeg path instead",
    "cookiesfrombrowser": "use the Browser cookies setting instead",
}
# Options that print and exit, update yt-dlp, or read other files at parse time.
_RESERVED_FLAGS = (
    "-h", "--help", "--version", "-U", "--update", "--update-to",
    "--config-location", "--config-locations", "-a", "--batch-file",
)


def parse_extra_args(text: str) -> tuple[list[str], dict[str, Any]]:
    """Check extra yt-dlp options.

    Returns:
        The command-line arguments and the matching YoutubeDL options (only
        those that differ from yt-dlp's defaults).

    Raises:
        ValidationError: With a message naming the option at fault.
    """
    args = _split(text)
    if not args:
        return [], {}
    for arg in args:
        if any(arg == flag or arg.startswith(f"{flag}=") for flag in _RESERVED_FLAGS):
            raise ValidationError(f"{EXTRA_ARGS_LABEL}: '{arg}' can't be used here.")
    parsed = _parse(args)
    if parsed.urls:
        raise ValidationError(
            f"{EXTRA_ARGS_LABEL}: only options, no video URLs ('{parsed.urls[0]}')."
        )
    options = _changed_options(parsed.ydl_opts)
    blocked = (_RESERVED_OPTIONS | _SETTING_OPTIONS.keys()) & options.keys()
    if blocked:
        key, flag = _first_blocked(args, blocked)
        reason = _SETTING_OPTIONS.get(key, "the app sets this itself")
        raise ValidationError(f"{EXTRA_ARGS_LABEL}: '{flag}' can't be used: {reason}.")
    return args, options


def _split(text: str) -> list[str]:
    lexer = shlex.shlex(text or "", posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as e:
        raise ValidationError(f"{EXTRA_ARGS_LABEL}: a quote is not closed.") from e


def _parse(args: list[str]):
    # --ignore-config: only these options count, not the user's config files.
    # yt-dlp prints debug lines while parsing --verbose; keep them quiet.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return yt_dlp.parse_options(["--ignore-config", *args])
    except optparse.OptParseError as e:
        reason = e.msg.strip().rsplit("error: ", 1)[-1]
        raise ValidationError(f"{EXTRA_ARGS_LABEL}: {reason}.") from e
    except SystemExit as e:
        raise ValidationError(f"{EXTRA_ARGS_LABEL}: '{' '.join(args)}' can't be used here.") from e


def _defaults() -> dict[str, Any]:
    return _parse([]).ydl_opts


def _changed_options(options: dict[str, Any]) -> dict[str, Any]:
    defaults = _defaults()
    return {key: value for key, value in options.items() if defaults.get(key) != value}


def _first_blocked(args: list[str], blocked: set[str]) -> tuple[str, str]:
    """Find which typed option set a blocked key, by parsing ever-longer prefixes."""
    for end in range(1, len(args) + 1):
        try:
            options = _changed_options(_parse(args[:end]).ydl_opts)
        except ValidationError:
            continue  # an option still missing its value
        hit = sorted(blocked & options.keys())
        if hit:
            flag = next(arg for arg in reversed(args[:end]) if arg.startswith("-"))
            return hit[0], flag
    key = sorted(blocked)[0]
    return key, key
