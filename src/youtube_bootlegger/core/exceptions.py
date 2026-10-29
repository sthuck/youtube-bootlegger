"""Custom exceptions for YouTube Bootlegger."""


class YouTubeBootleggerError(Exception):
    """Base exception for all app errors."""


class ValidationError(YouTubeBootleggerError):
    """Input validation failed."""


class DownloadError(YouTubeBootleggerError):
    """Audio download failed."""


class ParseError(YouTubeBootleggerError):
    """Tracklist parsing failed."""


class SplitError(YouTubeBootleggerError):
    """FFmpeg splitting failed."""


class FFmpegNotFoundError(YouTubeBootleggerError):
    """FFmpeg is not installed or not in PATH."""


class OperationCancelledError(YouTubeBootleggerError):
    """The user cancelled a running download or split."""


class ToolInstallError(YouTubeBootleggerError):
    """Downloading or unpacking a runtime tool failed."""
