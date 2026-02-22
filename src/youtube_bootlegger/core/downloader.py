"""YouTube audio downloader using yt-dlp."""

import tempfile
from collections.abc import Callable
from pathlib import Path

import yt_dlp

from .exceptions import DownloadError


class AudioDownloader:
    """Wrapper around yt-dlp for audio downloads."""

    def __init__(
        self,
        output_dir: Path | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ):
        """Initialize the downloader.

        Args:
            output_dir: Directory to save downloaded audio. Uses temp dir if None.
            progress_callback: Callback for progress updates (percent, status).
        """
        self._output_dir = output_dir or Path(tempfile.gettempdir())
        self._progress_callback = progress_callback
        self._last_percent = 0.0

    def download(self, url: str) -> Path:
        """Download audio from YouTube URL.

        Args:
            url: YouTube video URL.

        Returns:
            Path to the downloaded audio file.

        Raises:
            DownloadError: If the download fails.
        """
        output_template = str(self._output_dir / "%(title)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": output_template,
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("Failed to extract video information")

                filename = ydl.prepare_filename(info)
                audio_path = Path(filename).with_suffix(".mp3")

                if not audio_path.exists():
                    raise DownloadError(f"Downloaded file not found: {audio_path}")

                return audio_path

        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(f"Download failed: {e}") from e
        except Exception as e:
            raise DownloadError(f"Unexpected error during download: {e}") from e

    def _progress_hook(self, d: dict) -> None:
        """Handle yt-dlp progress updates."""
        if self._progress_callback is None:
            return

        status = d.get("status", "")

        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                percent = (downloaded / total) * 100
                if percent - self._last_percent >= 1:
                    self._last_percent = percent
                    self._progress_callback(percent, "Downloading...")

        elif status == "finished":
            self._progress_callback(100, "Download complete, processing...")

        elif status == "error":
            self._progress_callback(0, "Download error")
