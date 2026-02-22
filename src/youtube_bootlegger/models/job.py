"""Download job data model."""

from dataclasses import dataclass
from pathlib import Path

from .track import Track


@dataclass(frozen=True)
class DownloadJob:
    """Represents a complete download and split job.

    Attributes:
        url: YouTube video URL.
        output_dir: Directory to save output files.
        tracks: Tuple of tracks to extract.
        audio_format: Output audio format (default: mp3).
    """

    url: str
    output_dir: Path
    tracks: tuple[Track, ...]
    audio_format: str = "mp3"

    @property
    def track_count(self) -> int:
        """Return the number of tracks."""
        return len(self.tracks)
