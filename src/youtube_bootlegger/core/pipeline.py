"""Download and split pipeline orchestration."""

import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from ..models import DownloadJob
from .downloader import AudioDownloader
from .splitter import AudioSplitter
from .tagger import tag_audio_files


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

            # Create output subdirectory based on artist/album
            output_dir = self._create_output_dir(job)

            splitter = AudioSplitter(
                progress_callback=self._on_split_progress,
                log_callback=self._log,
            )

            output_files = splitter.split(
                input_file=audio_file,
                output_dir=output_dir,
                tracks=list(job.tracks),
                audio_format=job.audio_format,
            )

            if self._cancelled:
                return []

            # Apply metadata tags
            self._emit_progress("tagging", 0, "Applying metadata tags...")
            self._apply_tags(output_files, job)

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

    def _create_output_dir(self, job: DownloadJob) -> Path:
        """Create output subdirectory based on artist and album.

        Creates a directory named "Artist - Album" or just "Album" if no artist.

        Args:
            job: The download job with metadata.

        Returns:
            Path to the output directory.
        """
        # Build directory name from artist and album
        if job.artist and job.album:
            dir_name = f"{job.artist} - {job.album}"
        elif job.album:
            dir_name = job.album
        else:
            dir_name = "Unknown Album"

        # Sanitize directory name (remove invalid characters)
        dir_name = self._sanitize_filename(dir_name)

        output_dir = job.output_dir / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        self._log(f"Output directory: {output_dir}")
        return output_dir

    def _sanitize_filename(self, name: str) -> str:
        """Remove or replace characters invalid for filenames.

        Args:
            name: The filename to sanitize.

        Returns:
            Sanitized filename.
        """
        # Characters not allowed in filenames on various OS
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        # Remove leading/trailing whitespace and dots
        name = name.strip(". ")
        return name or "Unknown"

    def _apply_tags(self, output_files: list[Path], job: DownloadJob) -> None:
        """Apply metadata tags to output files.

        Args:
            output_files: List of output audio files.
            job: The download job with metadata.
        """
        if not output_files:
            return

        # Get track names in order
        track_names = [track.name for track in job.tracks]

        # Download cover art from thumbnail URL
        cover_art = None
        cover_mime_type = "image/jpeg"

        if job.thumbnail_url:
            self._log(f"Downloading cover art from: {job.thumbnail_url}")
            cover_art, cover_mime_type = self._download_cover_art(job.thumbnail_url)

        try:
            tag_audio_files(
                files=output_files,
                track_names=track_names,
                artist=job.artist,
                album=job.album,
                cover_art=cover_art,
                cover_mime_type=cover_mime_type,
                audio_format=job.audio_format,
            )
            self._log(f"Applied metadata tags to {len(output_files)} files")
            self._emit_progress("tagging", 100, "Metadata tags applied")
        except ValueError as e:
            self._log(f"Warning: Could not apply tags: {e}")

    def _download_cover_art(self, url: str) -> tuple[bytes | None, str]:
        """Download cover art from URL.

        Args:
            url: URL to download from.

        Returns:
            Tuple of (image_data, mime_type).
        """
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type", "image/jpeg")
                return data, content_type
        except Exception as e:
            self._log(f"Warning: Could not download cover art: {e}")
            return None, "image/jpeg"

    def _cleanup_temp(self, temp_dir: Path) -> None:
        """Clean up temporary files."""
        try:
            for file in temp_dir.iterdir():
                file.unlink()
            temp_dir.rmdir()
        except OSError:
            pass
