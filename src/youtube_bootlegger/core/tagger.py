"""Audio file tagging using mutagen.

Supports MP3 (ID3) with extensible design for other formats.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK
from mutagen.mp3 import MP3


@dataclass(frozen=True)
class TrackMetadata:
    """Metadata for a single track.

    Attributes:
        title: Track/song title.
        artist: Artist name.
        album: Album name.
        track_number: Track number in album.
        total_tracks: Total tracks in album.
        cover_art: Album cover image data (bytes).
        cover_mime_type: MIME type of cover art (e.g., "image/jpeg").
    """

    title: str
    artist: str | None = None
    album: str | None = None
    track_number: int | None = None
    total_tracks: int | None = None
    cover_art: bytes | None = None
    cover_mime_type: str = "image/jpeg"


class AudioTagger(ABC):
    """Abstract base class for audio file taggers."""

    @abstractmethod
    def apply_tags(self, file_path: Path, metadata: TrackMetadata) -> None:
        """Apply metadata tags to an audio file.

        Args:
            file_path: Path to the audio file.
            metadata: Metadata to apply.
        """
        pass

    @staticmethod
    def for_format(audio_format: str) -> "AudioTagger":
        """Get a tagger for the specified audio format.

        Args:
            audio_format: Audio format (e.g., "mp3", "m4a").

        Returns:
            Appropriate AudioTagger instance.

        Raises:
            ValueError: If format is not supported.
        """
        taggers = {
            "mp3": MP3Tagger,
        }

        tagger_class = taggers.get(audio_format.lower())
        if tagger_class is None:
            raise ValueError(f"Unsupported audio format for tagging: {audio_format}")

        return tagger_class()


class MP3Tagger(AudioTagger):
    """Tagger for MP3 files using ID3v2.4 tags."""

    def apply_tags(self, file_path: Path, metadata: TrackMetadata) -> None:
        """Apply ID3 tags to an MP3 file.

        Args:
            file_path: Path to the MP3 file.
            metadata: Metadata to apply.
        """
        audio = MP3(file_path)

        # Create ID3 tags if they don't exist
        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags
        if not isinstance(tags, ID3):
            audio.add_tags()
            tags = audio.tags

        # Title (TIT2)
        if metadata.title:
            tags.add(TIT2(encoding=3, text=metadata.title))

        # Artist (TPE1)
        if metadata.artist:
            tags.add(TPE1(encoding=3, text=metadata.artist))

        # Album (TALB)
        if metadata.album:
            tags.add(TALB(encoding=3, text=metadata.album))

        # Track number (TRCK)
        if metadata.track_number is not None:
            if metadata.total_tracks is not None:
                track_str = f"{metadata.track_number}/{metadata.total_tracks}"
            else:
                track_str = str(metadata.track_number)
            tags.add(TRCK(encoding=3, text=track_str))

        # Cover art (APIC)
        if metadata.cover_art:
            tags.add(APIC(
                encoding=3,
                mime=metadata.cover_mime_type,
                type=3,  # Cover (front)
                desc="Cover",
                data=metadata.cover_art,
            ))

        audio.save()


def tag_audio_files(
    files: list[Path],
    track_names: list[str],
    artist: str | None = None,
    album: str | None = None,
    cover_art: bytes | None = None,
    cover_mime_type: str = "image/jpeg",
    audio_format: str = "mp3",
) -> None:
    """Apply tags to multiple audio files.

    Args:
        files: List of audio file paths.
        track_names: List of track names (same order as files).
        artist: Artist name for all tracks.
        album: Album name for all tracks.
        cover_art: Album cover image data.
        cover_mime_type: MIME type of cover art.
        audio_format: Audio format of the files.
    """
    if len(files) != len(track_names):
        raise ValueError("Number of files must match number of track names")

    tagger = AudioTagger.for_format(audio_format)
    total_tracks = len(files)

    for i, (file_path, title) in enumerate(zip(files, track_names), 1):
        metadata = TrackMetadata(
            title=title,
            artist=artist,
            album=album,
            track_number=i,
            total_tracks=total_tracks,
            cover_art=cover_art,
            cover_mime_type=cover_mime_type,
        )
        tagger.apply_tags(file_path, metadata)
