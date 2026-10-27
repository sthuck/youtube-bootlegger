"""Full-stack E2E smoke test: QML UI -> AppBackend -> PipelineWorker -> FFmpeg split -> Mutagen ID3 tags."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.app_qml import create_qml_engine
from src.youtube_bootlegger.core import pipeline as pipeline_module
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.qml_backend import AppBackend
from src.youtube_bootlegger.workers import video_info_worker as video_worker_module
from tests.test_qml import (
     VALID_URL,
    DictBackend,
    click_item,
    make_video,
    prop,
    set_text,
    wait_until,
)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is required for full-stack E2E test")
def test_qml_full_pipeline_splits_and_tags_real_mp3_files(tmp_path, monkeypatch):
    """Drive the QML UI end-to-end with real FFmpeg splitting and Mutagen tagging."""
    app = QApplication.instance() or QApplication(sys.argv)

    # 1. Synthesize a real 3-second MP3 fixture using ffmpeg.
    source_mp3 = tmp_path / "fixture_source.mp3"
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
            str(source_mp3),
        ],
        check=True,
        capture_output=True,
    )

    # 2. Stub only the external network boundaries (video metadata fetch & yt-dlp download).
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

    # 3. Launch the QML UI wired to a fresh AppBackend.
    settings = AppSettings(DictBackend())
    backend = AppBackend(settings=settings)
    backend.URL_DEBOUNCE_MS = 10
    engine = create_qml_engine(backend)
    window: QQuickWindow = engine.rootObjects()[0]
    QTest.qWaitForWindowExposed(window)
    app.processEvents()

    try:
        out_root = tmp_path / "output"
        out_root.mkdir()

        # 4. Fill out the QML form controls and start the pipeline.
        set_text(window, "urlField", VALID_URL)
        wait_until(lambda: backend.videoLoaded)
        assert prop(window, "videoTitleText") == "Acoustic Session"

        set_text(window, "tracklistArea", "First Part - 0:00\nSecond Part - 0:01")
        set_text(window, "artistField", "The Bootleggers")
        set_text(window, "albumField", "Live 2026")
        set_text(window, "dirField", str(out_root))

        click_item(window, "startButton")
        wait_until(lambda: prop(window, "progressStageText") == "Complete!", timeout_ms=10_000)

        # 5. Verify QML completion UI state.
        assert backend.busy is False
        assert prop(window, "msgOverlay", "visible") is True
        assert prop(window, "msgTitle") == "Complete"
        assert "2 track(s)" in prop(window, "msgBody")

        # 6. Verify real split MP3 files and ID3 metadata tags on disk.
        album_dir = out_root / "The Bootleggers - Live 2026"
        track1 = album_dir / "01 - First Part.mp3"
        track2 = album_dir / "02 - Second Part.mp3"
        assert track1.is_file() and track1.stat().st_size > 0
        assert track2.is_file() and track2.stat().st_size > 0

        mp3_1 = MP3(track1)
        mp3_2 = MP3(track2)
        assert 0.5 <= mp3_1.info.length <= 1.6
        assert 1.4 <= mp3_2.info.length <= 2.6

        tags1 = ID3(track1)
        assert str(tags1["TIT2"]) == "First Part"
        assert str(tags1["TPE1"]) == "The Bootleggers"
        assert str(tags1["TALB"]) == "Live 2026"
        assert str(tags1["TRCK"]) == "1/2"

        tags2 = ID3(track2)
        assert str(tags2["TIT2"]) == "Second Part"
        assert str(tags2["TPE1"]) == "The Bootleggers"
        assert str(tags2["TALB"]) == "Live 2026"
        assert str(tags2["TRCK"]) == "2/2"
    finally:
        backend._thread_pool.waitForDone(2000)
        window.close()
        app.processEvents()
        del window
        del engine
        app.processEvents()
