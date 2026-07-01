"""Core business logic for YouTube Bootlegger."""

from .exceptions import (
    YouTubeBootleggerError,
    ValidationError,
    DownloadError,
    ParseError,
    SplitError,
    FFmpegNotFoundError,
)
from .downloader import AudioDownloader
from .splitter import AudioSplitter
from .pipeline import DownloadSplitPipeline
from .settings import AppSettings, get_settings
from .video_info import VideoInfo, fetch_video_info
from .template_parser import (
    DEFAULT_TEMPLATE,
    ParsePreview,
    TrackPreview,
    TemplateValidation,
    parse_tracklist_with_template,
    preview_parse,
    validate_template,
)

__all__ = [
    "YouTubeBootleggerError",
    "ValidationError",
    "DownloadError",
    "ParseError",
    "SplitError",
    "FFmpegNotFoundError",
    "AudioDownloader",
    "AudioSplitter",
    "DownloadSplitPipeline",
    "AppSettings",
    "get_settings",
    "VideoInfo",
    "fetch_video_info",
    "DEFAULT_TEMPLATE",
    "ParsePreview",
    "TrackPreview",
    "TemplateValidation",
    "parse_tracklist_with_template",
    "preview_parse",
    "validate_template",
]
