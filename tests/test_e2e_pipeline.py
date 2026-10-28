"""Full-stack E2E smoke test: QML UI -> AppBackend -> PipelineWorker -> FFmpeg split -> Mutagen ID3 tags."""

import shutil
import subprocess
from pathlib import Path

import pytest
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from src.youtube_bootlegger.core import pipeline as pipeline_module
from src.youtube_bootlegger.qml_backend import AppBackend
from src.youtube_bootlegger.workers import video_info_worker as video_worker_module
from tests.qml_support import (
    VALID_URL,
    click_item,
    make_video,
    open_window,
    prop,
    set_text,
    type_text,
    wait_until,
)


def _ffmpeg_can_encode_mp3() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    encoders = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    )
    return "libmp3lame" in encoders.stdout


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _ffmpeg_can_encode_mp3(),
        reason="ffmpeg with the libmp3lame encoder is required for the full-stack E2E test",
    ),
]


@pytest.fixture
def source_mp3(tmp_path) -> Path:
    """A real 3-second MP3 synthesized with ffmpeg."""
    path = tmp_path / "fixture_source.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def test_qml_full_pipeline_splits_and_tags_real_mp3_files(
    qapp, app_settings, source_mp3, tmp_path, monkeypatch
):
    """Drive the QML UI end-to-end with real FFmpeg splitting and Mutagen tagging."""
    # Stub only the network boundaries: video metadata fetch and yt-dlp download.
    monkeypatch.setattr(
        video_worker_module,
        "fetch_video_info",
        lambda url, settings=None: make_video(
            title="Acoustic Session",
            channel="The Bootleggers",
            duration=3,
            duration_string="0:03",
        ),
    )

    def fake_download(self, url: str) -> Path:
        dest = self._output_dir / "downloaded.mp3"
        shutil.copyfile(source_mp3, dest)
        return dest

    monkeypatch.setattr(pipeline_module.AudioDownloader, "download", fake_download)

    backend = AppBackend(settings=app_settings)
    backend.URL_DEBOUNCE_MS = 10
    out_root = tmp_path / "output"
    out_root.mkdir()

    with open_window(backend) as (window, warnings):
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: backend.videoLoaded)
        assert prop(window, "videoTitleText") == "Acoustic Session"

        set_text(window, "tracklistArea", "First Part - 0:00\nSecond Part - 0:01")
        type_text(window, "artistField", "The Bootleggers")
        type_text(window, "albumField", "Live 2026")
        type_text(window, "dirField", str(out_root))

        click_item(window, "startButton")
        wait_until(lambda: prop(window, "progressStageText") == "Complete!", timeout_ms=10_000)

        assert backend.busy is False
        assert prop(window, "msgOverlay", "visible") is True
        assert prop(window, "msgTitle") == "Complete"
        assert "2 track(s)" in prop(window, "msgBody")
        assert warnings == []

    album_dir = out_root / "The Bootleggers - Live 2026"
    track1 = album_dir / "01 - First Part.mp3"
    track2 = album_dir / "02 - Second Part.mp3"
    assert track1.is_file() and track1.stat().st_size > 0
    assert track2.is_file() and track2.stat().st_size > 0

    assert 0.5 <= MP3(track1).info.length <= 1.6
    assert 1.4 <= MP3(track2).info.length <= 2.6

    for path, title, number in [(track1, "First Part", "1/2"), (track2, "Second Part", "2/2")]:
        tags = ID3(path)
        assert str(tags["TIT2"]) == title
        assert str(tags["TPE1"]) == "The Bootleggers"
        assert str(tags["TALB"]) == "Live 2026"
        assert str(tags["TRCK"]) == number
