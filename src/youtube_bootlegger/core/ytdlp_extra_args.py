"""Extra yt-dlp options set in Settings, such as a proxy or a rate limit.

The text is split like a shell command line, except that backslashes are kept
as typed so Windows paths work; quote values that contain spaces. Only the
external yt-dlp executable reads them, so the checks here are static: options
the app sets itself, options with a setting of their own and stray URLs are
rejected up front. Anything yt-dlp itself doesn't accept (an unknown option, a
missing value) is reported when it runs, through option_error.
"""

import re
import shlex

from .exceptions import ValidationError

EXTRA_ARGS_LABEL = "Extra yt-dlp options"

# Options the app sets itself or reads back: where the file goes, its format
# and post-processing, and what yt-dlp prints.
_APP_OPTIONS = frozenset({
    "-o", "--output", "-P", "--paths", "-f", "--format",
    "-x", "--extract-audio", "--audio-format", "--audio-quality",
    "--remux-video", "--recode-video", "--split-chapters", "--remove-chapters",
    "--sponsorblock-remove", "--exec", "--use-postprocessor", "--download-archive",
    "-q", "--quiet", "--no-progress", "--progress-template", "--newline", "--no-newline",
    "-O", "--print", "--print-to-file", "-j", "--dump-json", "-J", "--dump-single-json",
    "--flat-playlist", "-s", "--simulate", "--skip-download", "--no-download",
})
# Options that have a setting of their own.
_SETTING_OPTIONS = {
    "--ffmpeg-location": "set the ffmpeg path instead",
    "--cookies-from-browser": "use the Browser cookies setting instead",
}
# Options that print and exit, update yt-dlp, or read other files at parse time.
_RESERVED_FLAGS = frozenset({
    "-h", "--help", "--version", "-U", "--update", "--update-to",
    "--config-location", "--config-locations", "-a", "--batch-file",
})
# Options whose value is itself a URL.
_URL_VALUE_OPTIONS = frozenset({"--proxy", "--geo-verification-proxy", "--referer"})
_URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_YOUTUBE_URL_RE = re.compile(r"^(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE)
_VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}\Z")
# A bare ID can also be a perfectly valid option value (e.g. a username).
# Recognize common switches; leave yt-dlp's full option grammar to yt-dlp.
_SWITCHES = frozenset({"-v", "--verbose", "--yes-playlist", "--ignore-errors", "-i"})
_USAGE_ERROR_RE = re.compile(r"^yt-dlp: error: (.+)$", re.MULTILINE)


def parse_extra_args(text: str) -> list[str]:
    """Check extra yt-dlp options and return them as command-line arguments.

    Raises:
        ValidationError: With a message naming the option at fault.
    """
    args = _split(text)
    previous = ""
    for arg in args:
        name = _option_name(arg)
        if name in _RESERVED_FLAGS:
            raise ValidationError(f"{EXTRA_ARGS_LABEL}: '{arg}' can't be used here.")
        if name in _APP_OPTIONS or name in _SETTING_OPTIONS:
            reason = _SETTING_OPTIONS.get(name, "the app sets this itself")
            raise ValidationError(f"{EXTRA_ARGS_LABEL}: '{name}' can't be used: {reason}.")
        is_value = bool(_option_name(previous)) and not (
            previous in _SWITCHES or previous.startswith("--no-") or "=" in previous
        )
        is_video = _YOUTUBE_URL_RE.match(arg) or (
            not name and _VIDEO_ID_RE.fullmatch(arg) and not is_value
        )
        if (_URL_RE.match(arg) or is_video) and previous not in _URL_VALUE_OPTIONS:
            raise ValidationError(f"{EXTRA_ARGS_LABEL}: only options, no video URLs ('{arg}').")
        previous = arg
    return args


def youtube_extractor_args(args: list[str]) -> dict[str, list[str]]:
    """The YouTube --extractor-args among the extra options, as yt-dlp reads them.

    yt-dlp replaces, not merges, a second set for the same site, so the last wins.
    """
    found: dict[str, list[str]] = {}
    for i, arg in enumerate(args):
        if arg == "--extractor-args" and i + 1 < len(args):
            value = args[i + 1]
        elif arg.startswith("--extractor-args="):
            value = arg.split("=", 1)[1]
        else:
            continue
        site, _, spec = value.partition(":")
        if site.strip().lower() == "youtube":
            found = dict(_extractor_arg(item) for item in spec.split(";") if item.strip())
    return found


def option_error(output: str, extra_args: str) -> str | None:
    """A readable message when yt-dlp refused its command line, else None."""
    match = _USAGE_ERROR_RE.search(output or "")
    if not match:
        return None
    reason = match.group(1).strip().rstrip(".")
    if extra_args.strip():
        return f"{EXTRA_ARGS_LABEL}: {reason}."
    return f"yt-dlp rejected its options: {reason}."


def _extractor_arg(item: str) -> tuple[str, list[str]]:
    key, _, values = item.partition("=")
    return (
        key.strip().lower().replace("-", "_"),
        [value.replace(r"\,", ",").strip() for value in re.split(r"(?<!\\),", values)],
    )


def _option_name(arg: str) -> str:
    """The option an argument names: '--print=x' is '--print', '-ofile' is '-o'."""
    if arg.startswith("--"):
        return arg.split("=", 1)[0]
    if arg.startswith("-") and len(arg) > 1:
        return arg[:2]
    return ""


def _split(text: str) -> list[str]:
    lexer = shlex.shlex(text or "", posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as e:
        raise ValidationError(f"{EXTRA_ARGS_LABEL}: a quote is not closed.") from e
