"""Audio splitting using FFmpeg."""

import subprocess
from collections.abc import Callable
from pathlib import Path

from ..models import Track
from ..utils import format_seconds_to_timestamp, sanitize_filename
from .exceptions import FFmpegNotFoundError, SplitError


class AudioSplitter:
    """Split audio files using FFmpeg subprocess."""

    def __init__(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ):
        """Initialize the splitter.

        Args:
            progress_callback: Callback for progress (current, total, track_name).
            log_callback: Callback for log messages.
        """
        self._progress_callback = progress_callback
        self._log_callback = log_callback

    def _log(self, message: str) -> None:
        """Emit a log message."""
        if self._log_callback:
            self._log_callback(message)

    def split(
        self,
        input_file: Path,
        output_dir: Path,
        tracks: list[Track],
        audio_format: str = "mp3",
    ) -> list[Path]:
        """Split input audio into separate track files.

        Args:
            input_file: Path to the source audio file.
            output_dir: Directory to save output files.
            tracks: List of tracks with start/end times.
            audio_format: Output audio format.

        Returns:
            List of output file paths.

        Raises:
            SplitError: If splitting fails.
            FFmpegNotFoundError: If ffmpeg is not available.
        """
        self._check_ffmpeg()

        if not input_file.exists():
            raise SplitError(f"Input file not found: {input_file}")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_files: list[Path] = []

        for i, track in enumerate(tracks, 1):
            if self._progress_callback:
                self._progress_callback(i, len(tracks), track.name)

            safe_name = sanitize_filename(track.name)
            output_file = output_dir / f"{i:02d} - {safe_name}.{audio_format}"

            self._run_ffmpeg(input_file, output_file, track)
            output_files.append(output_file)

        return output_files

    def _check_ffmpeg(self) -> None:
        """Verify ffmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except FileNotFoundError as e:
            raise FFmpegNotFoundError(
                "FFmpeg not found. Please install FFmpeg and ensure it's in your PATH."
            ) from e
        except subprocess.SubprocessError as e:
            raise FFmpegNotFoundError(f"FFmpeg check failed: {e}") from e

    def _run_ffmpeg(
        self,
        input_file: Path,
        output_file: Path,
        track: Track,
    ) -> None:
        """Execute single FFmpeg split command."""
        start_time = format_seconds_to_timestamp(track.start_seconds)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file),
            "-ss",
            start_time,
        ]

        if track.duration is not None:
            duration = format_seconds_to_timestamp(track.duration)
            cmd.extend(["-t", duration])

        cmd.extend([
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_file),
        ])

        self._log(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                raise SplitError(
                    f"FFmpeg failed for '{track.name}': {result.stderr}"
                )

            self._log(f"Created: {output_file}")

        except subprocess.TimeoutExpired as e:
            raise SplitError(f"FFmpeg timed out for '{track.name}'") from e
        except subprocess.SubprocessError as e:
            raise SplitError(f"FFmpeg error for '{track.name}': {e}") from e
