"""Core business logic for YouTube Bootlegger."""

from .exceptions import (
    YouTubeBootleggerError,
    ValidationError,
    DownloadError,
    ParseError,
    SplitError,
    FFmpegNotFoundError,
)
from .parser import parse_tracklist
from .downloader import AudioDownloader
from .splitter import AudioSplitter
from .pipeline import DownloadSplitPipeline

__all__ = [
    "YouTubeBootleggerError",
    "ValidationError",
    "DownloadError",
    "ParseError",
    "SplitError",
    "FFmpegNotFoundError",
    "parse_tracklist",
    "AudioDownloader",
    "AudioSplitter",
    "DownloadSplitPipeline",
]
