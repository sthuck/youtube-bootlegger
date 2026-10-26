"""Audio splitting using FFmpeg."""

import subprocess
from collections.abc import Callable
from pathlib import Path

from ..models import Track
from ..utils import format_seconds_to_timestamp, sanitize_filename
from .cancellation import CancelToken
from .exceptions import FFmpegNotFoundError, OperationCancelledError, SplitError
from .settings import AppSettings, get_settings


class AudioSplitter:
    """Split audio files using FFmpeg subprocess."""

    def __init__(
        self,
        progress_callback: Callable[[int, int, str], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
        settings: AppSettings | None = None,
        cancel_token: CancelToken | None = None,
    ):
        """Initialize the splitter.

        Args:
            progress_callback: Callback for progress (current, total, track_name).
            log_callback: Callback for log messages.
            settings: Application settings. Defaults to the shared singleton.
            cancel_token: Stops the running ffmpeg and the split when triggered.
        """
        self._cancel = cancel_token or CancelToken()
        self._progress_callback = progress_callback
        self._log_callback = log_callback
        self._ffmpeg_command = (settings or get_settings()).resolved_ffmpeg_command()

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
            OperationCancelledError: If cancelled. Files written by this call,
                including a partially written one, are removed first.
        """
        self._check_ffmpeg()

        if not input_file.exists():
            raise SplitError(f"Input file not found: {input_file}")

        output_dir.mkdir(parents=True, exist_ok=True)
        output_files: list[Path] = []

        try:
            for i, track in enumerate(tracks, 1):
                self._cancel.raise_if_cancelled()
                if self._progress_callback:
                    self._progress_callback(i, len(tracks), track.name)

                safe_name = sanitize_filename(track.name)
                output_file = output_dir / f"{i:02d} - {safe_name}.{audio_format}"
                self._run_ffmpeg(input_file, output_file, track, written=output_files)
        except OperationCancelledError:
            self._remove_files(output_files)
            raise

        return output_files

    def _remove_files(self, files: list[Path]) -> None:
        """Delete outputs of a cancelled split so no half album is left behind."""
        for file in files:
            try:
                file.unlink(missing_ok=True)
            except OSError as e:
                self._log(f"Could not remove {file}: {e}")

    def _check_ffmpeg(self) -> None:
        """Verify ffmpeg is available."""
        try:
            subprocess.run(
                [self._ffmpeg_command, "-version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
        except FileNotFoundError as e:
            raise FFmpegNotFoundError(
                f"FFmpeg not found at '{self._ffmpeg_command}'. Please install FFmpeg, "
                "ensure it's in your PATH, or set a custom path in Settings."
            ) from e
        except subprocess.SubprocessError as e:
            raise FFmpegNotFoundError(f"FFmpeg check failed: {e}") from e

    def _run_ffmpeg(
        self,
        input_file: Path,
        output_file: Path,
        track: Track,
        written: list[Path] | None = None,
    ) -> None:
        """Execute single FFmpeg split command.

        Args:
            written: Gets output_file appended once ffmpeg has started (and so
                may have overwritten it). Cancel cleanup only deletes these,
                never a same-named file from an earlier run that ffmpeg
                didn't get to touch.
        """
        start_time = format_seconds_to_timestamp(track.start_seconds)

        cmd = [
            self._ffmpeg_command,
            "-nostdin",
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
            with self._cancel.child_process(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as process:
                if written is not None:
                    written.append(output_file)
                _, stderr = process.communicate(timeout=300)
        except subprocess.TimeoutExpired as e:
            raise SplitError(f"FFmpeg timed out for '{track.name}'") from e
        except (OSError, subprocess.SubprocessError) as e:
            raise SplitError(f"FFmpeg error for '{track.name}': {e}") from e

        # A cancelled (killed) ffmpeg exits non-zero; report it as a cancel.
        self._cancel.raise_if_cancelled()
        if process.returncode != 0:
            raise SplitError(f"FFmpeg failed for '{track.name}': {stderr}")

        self._log(f"Created: {output_file}")
