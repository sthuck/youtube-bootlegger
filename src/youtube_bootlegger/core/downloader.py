"""YouTube audio downloader using yt-dlp."""

import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import yt_dlp

from .exceptions import DownloadError
from .settings import AppSettings, get_settings

_PROGRESS_RE = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%")


class AudioDownloader:
    """Wrapper around yt-dlp for audio downloads."""

    def __init__(
        self,
        output_dir: Path | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
        settings: AppSettings | None = None,
    ):
        """Initialize the downloader.

        Args:
            output_dir: Directory to save downloaded audio. Uses temp dir if None.
            progress_callback: Callback for progress updates (percent, status).
            log_callback: Callback for log messages.
            settings: Application settings. Defaults to the shared singleton.
        """
        self._output_dir = output_dir or Path(tempfile.gettempdir())
        self._progress_callback = progress_callback
        self._log_callback = log_callback
        self._last_percent = 0.0
        self._settings = settings or get_settings()

    def _log(self, message: str) -> None:
        """Emit a log message."""
        if self._log_callback:
            self._log_callback(message)

    def download(self, url: str) -> Path:
        """Download audio from YouTube URL.

        Args:
            url: YouTube video URL.

        Returns:
            Path to the downloaded audio file.

        Raises:
            DownloadError: If the download fails.
        """
        if self._settings.use_external_ytdlp:
            return self._download_external(url)
        return self._download_library(url)

    def _download_library(self, url: str) -> Path:
        """Download using the bundled yt-dlp Python library."""
        output_template = str(self._output_dir / "%(title)s.%(ext)s")

        self._log(f"Download directory: {self._output_dir}")

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

        if self._settings.ffmpeg_path:
            ydl_opts["ffmpeg_location"] = self._settings.ffmpeg_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    raise DownloadError("Failed to extract video information")

                filename = ydl.prepare_filename(info)
                audio_path = Path(filename).with_suffix(".mp3")

                if not audio_path.exists():
                    raise DownloadError(f"Downloaded file not found: {audio_path}")

                self._log(f"Downloaded to: {audio_path}")
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

    def _download_external(self, url: str) -> Path:
        """Download audio by invoking the external yt-dlp executable.

        Args:
            url: YouTube video URL.

        Returns:
            Path to the downloaded audio file.

        Raises:
            DownloadError: If the download fails or the executable is missing.
        """
        output_template = str(self._output_dir / "%(title)s.%(ext)s")
        command = self._settings.resolved_ytdlp_command()

        cmd = [
            command,
            "-f", "bestaudio/best",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "192",
            "-o", output_template,
            "--newline",
            "--no-warnings",
        ]

        if self._settings.ffmpeg_path:
            cmd.extend(["--ffmpeg-location", self._settings.ffmpeg_path])

        cmd.append(url)

        self._log(f"Running: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as e:
            raise DownloadError(
                f"yt-dlp executable not found: '{command}'. "
                "Check the yt-dlp path in Settings."
            ) from e

        output_lines: list[str] = []
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            output_lines.append(line)
            self._log(line)
            self._report_external_progress(line)

        returncode = process.wait()
        if returncode != 0:
            tail = "\n".join(output_lines[-10:])
            raise DownloadError(f"yt-dlp failed (exit code {returncode}): {tail}")

        audio_path = self._latest_output_file()
        if audio_path is None:
            raise DownloadError("Downloaded file not found after yt-dlp completed")

        if self._progress_callback:
            self._progress_callback(100, "Download complete, processing...")

        self._log(f"Downloaded to: {audio_path}")
        return audio_path

    def _report_external_progress(self, line: str) -> None:
        """Parse a yt-dlp CLI output line and emit progress if it reports a percent."""
        if self._progress_callback is None:
            return

        match = _PROGRESS_RE.search(line)
        if not match:
            return

        percent = float(match.group(1))
        if percent - self._last_percent >= 1 or percent >= 100:
            self._last_percent = percent
            self._progress_callback(percent, "Downloading...")

    def _latest_output_file(self) -> Path | None:
        """Return the most recently modified mp3 file in the output directory."""
        candidates = sorted(
            self._output_dir.glob("*.mp3"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None
