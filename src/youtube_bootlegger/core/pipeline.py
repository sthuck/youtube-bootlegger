"""Download and split pipeline orchestration."""

import tempfile
from collections.abc import Callable
from pathlib import Path

from ..models import DownloadJob
from .downloader import AudioDownloader
from .splitter import AudioSplitter


class DownloadSplitPipeline:
    """Orchestrates the full download and split workflow."""

    def __init__(
        self,
        progress_callback: Callable[[str, float, str], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ):
        """Initialize the pipeline.

        Args:
            progress_callback: Callback for progress (stage, percent, message).
            log_callback: Callback for log messages.
        """
        self._progress_callback = progress_callback
        self._log_callback = log_callback
        self._cancelled = False

    def _log(self, message: str) -> None:
        """Emit a log message."""
        if self._log_callback:
            self._log_callback(message)

    def execute(self, job: DownloadJob) -> list[Path]:
        """Execute full pipeline.

        Args:
            job: The download job to execute.

        Returns:
            List of output file paths.

        Raises:
            Various exceptions from downloader and splitter.
        """
        self._cancelled = False
        temp_dir = Path(tempfile.mkdtemp(prefix="youtube-bootlegger-"))

        try:
            self._emit_progress("download", 0, "Starting download...")

            downloader = AudioDownloader(
                output_dir=temp_dir,
                progress_callback=self._on_download_progress,
                log_callback=self._log,
            )

            audio_file = downloader.download(job.url)

            if self._cancelled:
                return []

            self._emit_progress("split", 0, "Starting split...")

            splitter = AudioSplitter(
                progress_callback=self._on_split_progress,
                log_callback=self._log,
            )

            output_files = splitter.split(
                input_file=audio_file,
                output_dir=job.output_dir,
                tracks=list(job.tracks),
                audio_format=job.audio_format,
            )

            self._emit_progress("complete", 100, "Complete!")
            return output_files

        finally:
            self._cleanup_temp(temp_dir)

    def cancel(self) -> None:
        """Request cancellation of the pipeline."""
        self._cancelled = True

    def _emit_progress(self, stage: str, percent: float, message: str) -> None:
        """Emit progress update."""
        if self._progress_callback:
            self._progress_callback(stage, percent, message)

    def _on_download_progress(self, percent: float, message: str) -> None:
        """Handle download progress."""
        self._emit_progress("download", percent, message)

    def _on_split_progress(self, current: int, total: int, track_name: str) -> None:
        """Handle split progress."""
        percent = (current / total) * 100
        message = f"Splitting track {current}/{total}: {track_name}"
        self._emit_progress("split", percent, message)

    def _cleanup_temp(self, temp_dir: Path) -> None:
        """Clean up temporary files."""
        try:
            for file in temp_dir.iterdir():
                file.unlink()
            temp_dir.rmdir()
        except OSError:
            pass
