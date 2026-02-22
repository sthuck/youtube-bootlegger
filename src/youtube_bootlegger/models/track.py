"""Track data model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    """Represents a single track/song to extract.

    Attributes:
        name: The name of the track.
        start_seconds: Start time in seconds.
        end_seconds: End time in seconds (None for last track).
    """

    name: str
    start_seconds: float
    end_seconds: float | None = None

    @property
    def duration(self) -> float | None:
        """Calculate track duration in seconds."""
        if self.end_seconds is None:
            return None
        return self.end_seconds - self.start_seconds

    def with_end_time(self, end_seconds: float) -> "Track":
        """Return a new Track with the specified end time."""
        return Track(
            name=self.name,
            start_seconds=self.start_seconds,
            end_seconds=end_seconds,
        )
