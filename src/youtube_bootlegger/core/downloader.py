"""YouTube audio downloader that runs the external yt-dlp executable."""

import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from .cancellation import CancelToken
from .exceptions import DownloadError, OperationCancelledError
from .settings import AppSettings, format_ytdlp_age_or_cookie_error, get_settings
from .ytdlp_extra_args import option_error

_PROGRESS_RE = re.compile(r"\[download\]\s+(\d{1,3}(?:\.\d+)?)%")


class AudioDownloader:
    """Wrapper around yt-dlp for audio downloads."""

    def __init__(
        self,
        output_dir: Path | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
        settings: AppSettings | None = None,
        cancel_token: CancelToken | None = None,
    ):
        """Initialize the downloader.

        Args:
            output_dir: Directory to save downloaded audio. Uses temp dir if None.
            progress_callback: Callback for progress updates (percent, status).
            log_callback: Callback for log messages.
            settings: Application settings. Defaults to the shared singleton.
            cancel_token: Cancels the download mid-way when triggered.
        """
        self._output_dir = output_dir or Path(tempfile.gettempdir())
        self._progress_callback = progress_callback
        self._log_callback = log_callback
        self._last_percent = 0.0
        self._settings = settings or get_settings()
        self._cancel = cancel_token or CancelToken()

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
            OperationCancelledError: If cancelled via the cancel token.
        """
        return self._download_external(url)

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
            *self._settings.ytdlp_config_cli_args(),
            "-f", "bestaudio/best",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "192",
            "-o", output_template,
            "--newline",
        ]

        cmd.extend(self._settings.ytdlp_tool_cli_args())

        cmd.extend(self._settings.ytdlp_cookie_cli_args())
        cmd.append(url)

        self._log(f"yt-dlp executable: {shutil.which(command) or command}")
        self._log(f"Running: {shlex.join(cmd)}")

        output_lines: list[str] = []
        try:
            with self._cancel.child_process(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1,
            ) as process:
                assert process.stdout is not None
                for raw_line in process.stdout:
                    line = raw_line.rstrip()
                    if not line:
                        continue
                    output_lines.append(line)
                    self._log(line)
                    self._report_external_progress(line)
                returncode = process.wait()
        except FileNotFoundError as e:
            raise DownloadError(
                f"yt-dlp executable not found: '{command}'. "
                "Check the yt-dlp path in Settings."
            ) from e

        # A cancelled (killed) process exits non-zero; report it as a cancel.
        self._cancel.raise_if_cancelled()
        if returncode != 0:
            tail = "\n".join(output_lines[-10:])
            friendly = option_error(tail, self._settings.ytdlp_extra_args) or (
                format_ytdlp_age_or_cookie_error(tail, self._settings)
            )
            if friendly:
                raise DownloadError(friendly)
            raise DownloadError(f"yt-dlp failed (exit code {returncode}): {tail}")

        audio_path = self._latest_output_file()
        if audio_path is None:
            hint = " Check Extra yt-dlp options in Settings." if self._settings.ytdlp_extra_args.strip() else ""
            raise DownloadError(
                "yt-dlp finished without creating an MP3 audio file." + hint
                + " See the download log for details."
            )

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
