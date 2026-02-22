"""Unit tests for audio tagger."""

import tempfile
from pathlib import Path

import pytest
from mutagen.mp3 import MP3

from src.youtube_bootlegger.core.tagger import (
    AudioTagger,
    MP3Tagger,
    TrackMetadata,
    tag_audio_files,
)


def create_test_mp3(path: Path) -> None:
    """Create a minimal valid MP3 file.

    Creates a valid MPEG Audio Layer III file with proper frame structure.
    """
    # Valid MPEG Audio frame header for Layer III, 128kbps, 44100Hz, stereo
    # Frame sync (11 bits of 1s) + MPEG Version 1, Layer III, no CRC
    # Bitrate index 1001 (128kbps), Sampling rate 00 (44100Hz)
    # Padding bit, private bit, channel mode, mode extension, copyright, original, emphasis
    #
    # Byte 0: 0xFF - First 8 bits of sync
    # Byte 1: 0xFB - Remaining sync + MPEG1 + Layer3 + no protection
    # Byte 2: 0x90 - 128kbps + 44100Hz + no padding
    # Byte 3: 0x00 - Stereo, mode ext, no copyright/original, no emphasis

    # Frame size for 128kbps @ 44100Hz = 417 bytes (no padding)
    frame_size = 417

    # Create multiple valid frames
    frames = []
    for _ in range(10):
        frame = bytearray(frame_size)
        frame[0] = 0xFF
        frame[1] = 0xFB
        frame[2] = 0x90
        frame[3] = 0x00
        frames.append(bytes(frame))

    with open(path, 'wb') as f:
        for frame in frames:
            f.write(frame)


class TestTrackMetadata:
    """Tests for TrackMetadata dataclass."""

    def test_create_minimal(self):
        """Create metadata with only required fields."""
        meta = TrackMetadata(title="Test Song")
        assert meta.title == "Test Song"
        assert meta.artist is None
        assert meta.album is None
        assert meta.track_number is None

    def test_create_full(self):
        """Create metadata with all fields."""
        cover = b"fake image data"
        meta = TrackMetadata(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_number=5,
            total_tracks=10,
            cover_art=cover,
            cover_mime_type="image/png",
        )
        assert meta.title == "Test Song"
        assert meta.artist == "Test Artist"
        assert meta.album == "Test Album"
        assert meta.track_number == 5
        assert meta.total_tracks == 10
        assert meta.cover_art == cover
        assert meta.cover_mime_type == "image/png"

    def test_frozen(self):
        """Metadata should be immutable."""
        meta = TrackMetadata(title="Test")
        with pytest.raises(AttributeError):
            meta.title = "Changed"


class TestAudioTagger:
    """Tests for AudioTagger factory."""

    def test_get_mp3_tagger(self):
        """Should return MP3Tagger for mp3 format."""
        tagger = AudioTagger.for_format("mp3")
        assert isinstance(tagger, MP3Tagger)

    def test_get_mp3_tagger_uppercase(self):
        """Should handle uppercase format."""
        tagger = AudioTagger.for_format("MP3")
        assert isinstance(tagger, MP3Tagger)

    def test_unsupported_format(self):
        """Should raise for unsupported format."""
        with pytest.raises(ValueError) as exc_info:
            AudioTagger.for_format("wav")
        assert "wav" in str(exc_info.value).lower()


class TestMP3Tagger:
    """Tests for MP3Tagger."""

    def test_apply_title(self):
        """Should apply title tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            tagger = MP3Tagger()
            tagger.apply_tags(mp3_path, TrackMetadata(title="My Song"))

            audio = MP3(mp3_path)
            assert audio.tags is not None
            assert str(audio.tags.get("TIT2")) == "My Song"

    def test_apply_artist(self):
        """Should apply artist tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            tagger = MP3Tagger()
            tagger.apply_tags(
                mp3_path,
                TrackMetadata(title="Song", artist="The Artist")
            )

            audio = MP3(mp3_path)
            assert str(audio.tags.get("TPE1")) == "The Artist"

    def test_apply_album(self):
        """Should apply album tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            tagger = MP3Tagger()
            tagger.apply_tags(
                mp3_path,
                TrackMetadata(title="Song", album="The Album")
            )

            audio = MP3(mp3_path)
            assert str(audio.tags.get("TALB")) == "The Album"

    def test_apply_track_number(self):
        """Should apply track number tag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            tagger = MP3Tagger()
            tagger.apply_tags(
                mp3_path,
                TrackMetadata(title="Song", track_number=3)
            )

            audio = MP3(mp3_path)
            assert str(audio.tags.get("TRCK")) == "3"

    def test_apply_track_with_total(self):
        """Should apply track number with total."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            tagger = MP3Tagger()
            tagger.apply_tags(
                mp3_path,
                TrackMetadata(title="Song", track_number=3, total_tracks=10)
            )

            audio = MP3(mp3_path)
            assert str(audio.tags.get("TRCK")) == "3/10"

    def test_apply_cover_art(self):
        """Should apply cover art."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            cover_data = b"fake jpeg data"
            tagger = MP3Tagger()
            tagger.apply_tags(
                mp3_path,
                TrackMetadata(
                    title="Song",
                    cover_art=cover_data,
                    cover_mime_type="image/jpeg"
                )
            )

            audio = MP3(mp3_path)
            apic_frames = [
                frame for frame in audio.tags.values()
                if frame.FrameID == "APIC"
            ]
            assert len(apic_frames) == 1
            assert apic_frames[0].data == cover_data
            assert apic_frames[0].mime == "image/jpeg"

    def test_apply_all_tags(self):
        """Should apply all metadata at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mp3_path = Path(tmpdir) / "test.mp3"
            create_test_mp3(mp3_path)

            tagger = MP3Tagger()
            tagger.apply_tags(
                mp3_path,
                TrackMetadata(
                    title="Full Song",
                    artist="Full Artist",
                    album="Full Album",
                    track_number=7,
                    total_tracks=12,
                    cover_art=b"cover",
                )
            )

            audio = MP3(mp3_path)
            assert str(audio.tags.get("TIT2")) == "Full Song"
            assert str(audio.tags.get("TPE1")) == "Full Artist"
            assert str(audio.tags.get("TALB")) == "Full Album"
            assert str(audio.tags.get("TRCK")) == "7/12"


class TestTagAudioFiles:
    """Tests for tag_audio_files helper function."""

    def test_tag_multiple_files(self):
        """Should tag multiple files with track numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(3):
                path = Path(tmpdir) / f"track{i}.mp3"
                create_test_mp3(path)
                files.append(path)

            tag_audio_files(
                files=files,
                track_names=["First", "Second", "Third"],
                artist="The Band",
                album="The Album",
            )

            for i, path in enumerate(files):
                audio = MP3(path)
                assert str(audio.tags.get("TIT2")) == ["First", "Second", "Third"][i]
                assert str(audio.tags.get("TPE1")) == "The Band"
                assert str(audio.tags.get("TALB")) == "The Album"
                assert str(audio.tags.get("TRCK")) == f"{i+1}/3"

    def test_mismatched_lists_raises(self):
        """Should raise if files and names don't match."""
        with pytest.raises(ValueError):
            tag_audio_files(
                files=[Path("a.mp3"), Path("b.mp3")],
                track_names=["Only One"],
            )

    def test_with_cover_art(self):
        """Should apply cover art to all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            for i in range(2):
                path = Path(tmpdir) / f"track{i}.mp3"
                create_test_mp3(path)
                files.append(path)

            cover = b"shared cover image"
            tag_audio_files(
                files=files,
                track_names=["Song A", "Song B"],
                cover_art=cover,
            )

            for path in files:
                audio = MP3(path)
                apic_frames = [
                    f for f in audio.tags.values() if f.FrameID == "APIC"
                ]
                assert len(apic_frames) == 1
                assert apic_frames[0].data == cover
