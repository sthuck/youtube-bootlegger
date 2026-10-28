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
from .video_info import VideoChapter, VideoInfo, fetch_video_info
from .video_comments import VideoComment, fetch_video_comments
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
    "VideoChapter",
    "VideoInfo",
    "fetch_video_info",
    "VideoComment",
    "fetch_video_comments",
    "DEFAULT_TEMPLATE",
    "ParsePreview",
    "TrackPreview",
    "TemplateValidation",
    "parse_tracklist_with_template",
    "preview_parse",
    "validate_template",
]
