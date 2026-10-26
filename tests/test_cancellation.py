"""Tests for mid-operation cancellation of downloads and splits."""

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yt_dlp

from src.youtube_bootlegger.core.cancellation import CancelToken
from src.youtube_bootlegger.core.downloader import AudioDownloader
from src.youtube_bootlegger.core.exceptions import OperationCancelledError
from src.youtube_bootlegger.core.pipeline import DownloadSplitPipeline
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.splitter import AudioSplitter
from src.youtube_bootlegger.models import DownloadJob, Track

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX fake executables")

# Generous bound: a cancelled operation must finish well before its natural end.
FAST_SECONDS = 5


class FakeSettingsBackend:
    def __init__(self):
        self._data = {}

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, value):
        self._data[key] = value

    def sync(self):
        pass


def make_settings(**values) -> AppSettings:
    settings = AppSettings(FakeSettingsBackend())
    for key, value in values.items():
        setattr(settings, key, value)
    return settings


def write_script(path: Path, body: str) -> Path:
    """Create an executable Python script standing in for yt-dlp/ffmpeg."""
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(0o755)
    return path


def cancel_after(token: CancelToken, seconds: float) -> threading.Thread:
    thread = threading.Thread(target=lambda: (time.sleep(seconds), token.cancel()))
    thread.start()
    return thread


# A fake ffmpeg: answers -version instantly, otherwise writes the output
# file partially and then hangs like a long encode.
SLOW_FFMPEG = """
import sys, time
if "-version" in sys.argv:
    print("ffmpeg version fake"); sys.exit(0)
open(sys.argv[-1], "wb").write(b"partial")
time.sleep(60)
"""

FAST_FFMPEG = """
import subprocess
import sys
if "-version" in sys.argv:
    print("ffmpeg version fake"); sys.exit(0)
open(sys.argv[-1], "wb").write(b"mp3")
"""

# A fake yt-dlp CLI: reports some progress, then stalls mid-download.
SLOW_YTDLP = """
import sys, time
print("[download]   5.0% of 10.00MiB", flush=True)
time.sleep(60)
"""


class TestCancelToken:
    def test_not_cancelled_initially(self):
        token = CancelToken()
        assert token.cancelled is False
        token.raise_if_cancelled()  # no exception

    def test_raise_if_cancelled(self):
        token = CancelToken()
        token.cancel()
        with pytest.raises(OperationCancelledError):
            token.raise_if_cancelled()

    def test_cancel_kills_running_child_process(self):
        token = CancelToken()
        start = time.monotonic()
        cancel_after(token, 0.3)
        with token.child_process([sys.executable, "-c", "import time; time.sleep(60)"]) as proc:
            proc.wait(timeout=FAST_SECONDS)
        assert time.monotonic() - start < FAST_SECONDS
        assert proc.returncode != 0

    def test_cancel_kills_grandchildren(self, tmp_path):
        # yt-dlp spawns ffmpeg; cancelling must not orphan the grandchild.
        pid_file = tmp_path / "grandchild.pid"
        script = (
            "import subprocess, sys, time\n"
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
            "time.sleep(60)\n"
        )
        token = CancelToken()
        cancel_after(token, 0.5)
        with token.child_process([sys.executable, "-c", script]) as proc:
            proc.wait(timeout=FAST_SECONDS)
        grandchild = int(pid_file.read_text())
        deadline = time.monotonic() + FAST_SECONDS
        while time.monotonic() < deadline and Path(f"/proc/{grandchild}").exists():
            stat = Path(f"/proc/{grandchild}/stat").read_text().split()
            if stat[2] == "Z":  # zombie: already dead, awaiting reaping
                break
            time.sleep(0.05)
        else:
            assert not Path(f"/proc/{grandchild}").exists()

    def test_starting_process_after_cancel_raises(self):
        token = CancelToken()
        token.cancel()
        with pytest.raises(OperationCancelledError):
            with token.child_process([sys.executable, "-c", "pass"]):
                pass


class TestDownloaderCancellation:
    def test_progress_hook_aborts_library_download(self):
        token = CancelToken()
        downloader = AudioDownloader(settings=make_settings(), cancel_token=token)
        token.cancel()
        with pytest.raises(yt_dlp.utils.DownloadCancelled):
            downloader._progress_hook({"status": "downloading", "downloaded_bytes": 1})

    def test_hook_aborts_even_without_progress_callback(self):
        token = CancelToken()
        downloader = AudioDownloader(
            settings=make_settings(), cancel_token=token, progress_callback=None
        )
        token.cancel()
        with pytest.raises(yt_dlp.utils.DownloadCancelled):
            downloader._postprocessor_hook({"status": "started"})

    def test_library_cancel_maps_to_operation_cancelled(self, monkeypatch, tmp_path):
        class CancellingYDL:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def extract_info(self, url, download):
                raise yt_dlp.utils.DownloadCancelled("cancelled")

        monkeypatch.setattr(yt_dlp, "YoutubeDL", CancellingYDL)
        downloader = AudioDownloader(output_dir=tmp_path, settings=make_settings())
        with pytest.raises(OperationCancelledError):
            downloader.download("https://youtu.be/x")

    def test_external_download_killed_mid_way(self, tmp_path):
        ytdlp = write_script(tmp_path / "yt-dlp", SLOW_YTDLP)
        settings = make_settings(use_external_ytdlp=True, ytdlp_path=str(ytdlp))
        token = CancelToken()
        progress = []
        downloader = AudioDownloader(
            output_dir=tmp_path,
            settings=settings,
            cancel_token=token,
            progress_callback=lambda pct, msg: progress.append(pct),
        )
        cancel_after(token, 0.5)
        start = time.monotonic()
        with pytest.raises(OperationCancelledError):
            downloader.download("https://youtu.be/x")
        assert time.monotonic() - start < FAST_SECONDS
        assert progress == [5.0]


class TestSplitterCancellation:
    def make_tracks(self):
        return [Track("One", 0, 10), Track("Two", 10, 20), Track("Three", 20)]

    def test_running_ffmpeg_killed_and_partial_outputs_removed(self, tmp_path):
        ffmpeg = write_script(tmp_path / "ffmpeg", SLOW_FFMPEG)
        source = tmp_path / "in.mp3"
        source.write_bytes(b"audio")
        out = tmp_path / "out"
        token = CancelToken()
        splitter = AudioSplitter(settings=make_settings(ffmpeg_path=str(ffmpeg)), cancel_token=token)
        cancel_after(token, 0.5)
        start = time.monotonic()
        with pytest.raises(OperationCancelledError):
            splitter.split(source, out, self.make_tracks())
        assert time.monotonic() - start < FAST_SECONDS
        assert list(out.iterdir()) == []

    def test_stops_between_tracks_and_removes_finished_ones(self, tmp_path):
        ffmpeg = write_script(tmp_path / "ffmpeg", FAST_FFMPEG)
        source = tmp_path / "in.mp3"
        source.write_bytes(b"audio")
        out = tmp_path / "out"
        token = CancelToken()

        def on_progress(current, total, name):
            if current == 2:
                token.cancel()

        splitter = AudioSplitter(
            settings=make_settings(ffmpeg_path=str(ffmpeg)),
            cancel_token=token,
            progress_callback=on_progress,
        )
        with pytest.raises(OperationCancelledError):
            splitter.split(source, out, self.make_tracks())
        assert list(out.iterdir()) == []


class TestPipelineCancellation:
    def make_job(self, tmp_path):
        return DownloadJob(
            url="https://youtu.be/x",
            output_dir=tmp_path / "music",
            tracks=(Track("One", 0, 10), Track("Two", 10)),
            artist="Band",
            album="Album",
        )

    def test_cancel_during_download_returns_empty_quickly(self, tmp_path):
        ytdlp = write_script(tmp_path / "yt-dlp", SLOW_YTDLP)
        settings = make_settings(use_external_ytdlp=True, ytdlp_path=str(ytdlp))
        pipeline = DownloadSplitPipeline(settings=settings)
        threading.Thread(target=lambda: (time.sleep(0.5), pipeline.cancel())).start()
        start = time.monotonic()
        assert pipeline.execute(self.make_job(tmp_path)) == []
        assert time.monotonic() - start < FAST_SECONDS
        assert not (tmp_path / "music").exists() or not any((tmp_path / "music").rglob("*"))

    def test_cancel_during_split_removes_outputs(self, tmp_path, monkeypatch):
        ffmpeg = write_script(tmp_path / "ffmpeg", SLOW_FFMPEG)
        settings = make_settings(ffmpeg_path=str(ffmpeg))
        source = tmp_path / "downloaded.mp3"

        def fake_download(self, url):
            source.write_bytes(b"audio")
            return source

        monkeypatch.setattr(AudioDownloader, "download", fake_download)
        pipeline = DownloadSplitPipeline(settings=settings)
        threading.Thread(target=lambda: (time.sleep(0.5), pipeline.cancel())).start()
        start = time.monotonic()
        assert pipeline.execute(self.make_job(tmp_path)) == []
        assert time.monotonic() - start < FAST_SECONDS
        assert not (tmp_path / "music").exists() or not any((tmp_path / "music").rglob("*"))

    def test_cancel_before_execute_is_honoured(self, tmp_path):
        pipeline = DownloadSplitPipeline(settings=make_settings())
        pipeline.cancel()
        assert pipeline.execute(self.make_job(tmp_path)) == []


class TestChildProcessesDoNotReadTerminal:
    """Children must not share the TUI's terminal input (review finding #1)."""

    def test_child_stdin_is_closed_by_default(self):
        token = CancelToken()
        with token.child_process(
            [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
            stdout=subprocess.PIPE,
            text=True,
        ) as proc:
            out, _ = proc.communicate(timeout=FAST_SECONDS)
        assert out.strip() == "''"

    def test_ffmpeg_runs_with_nostdin(self, tmp_path):
        args_file = tmp_path / "args.txt"
        ffmpeg = write_script(
            tmp_path / "ffmpeg",
            "import sys\n"
            "if '-version' in sys.argv: sys.exit(0)\n"
            f"open({str(args_file)!r}, 'w').write(' '.join(sys.argv[1:]))\n"
            "open(sys.argv[-1], 'wb').write(b'mp3')\n",
        )
        source = tmp_path / "in.mp3"
        source.write_bytes(b"audio")
        AudioSplitter(settings=make_settings(ffmpeg_path=str(ffmpeg))).split(
            source, tmp_path / "out", [Track("One", 0)]
        )
        assert "-nostdin" in args_file.read_text().split()


class TestCancelDoesNotDeleteUnwrittenFiles:
    """Review finding #7: only files this run started writing may be removed."""

    def test_existing_file_kept_when_cancel_lands_before_ffmpeg_starts(self, tmp_path):
        ffmpeg = write_script(tmp_path / "ffmpeg", FAST_FFMPEG)
        source = tmp_path / "in.mp3"
        source.write_bytes(b"audio")
        out = tmp_path / "out"
        out.mkdir()
        previous = out / "02 - Two.mp3"
        previous.write_bytes(b"from an earlier run")
        token = CancelToken()

        def on_progress(current, total, name):
            if current == 2:  # After the loop's check, before ffmpeg starts.
                token.cancel()

        splitter = AudioSplitter(
            settings=make_settings(ffmpeg_path=str(ffmpeg)),
            cancel_token=token,
            progress_callback=on_progress,
        )
        with pytest.raises(OperationCancelledError):
            splitter.split(source, out, [Track("One", 0, 10), Track("Two", 10)])
        assert previous.read_bytes() == b"from an earlier run"
        assert not (out / "01 - One.mp3").exists()


class TestCancelDuringTagging:
    """Review finding #4: cancel during cover-art download/tagging is honoured."""

    def test_cancel_while_tagging_returns_empty_and_removes_files(self, tmp_path, monkeypatch):
        ffmpeg = write_script(tmp_path / "ffmpeg", FAST_FFMPEG)
        settings = make_settings(ffmpeg_path=str(ffmpeg))
        source = tmp_path / "downloaded.mp3"

        def fake_download(self, url):
            source.write_bytes(b"audio")
            return source

        monkeypatch.setattr(AudioDownloader, "download", fake_download)
        pipeline = DownloadSplitPipeline(settings=settings)
        monkeypatch.setattr(
            "src.youtube_bootlegger.core.pipeline.tag_audio_files",
            lambda **kwargs: pipeline.cancel(),
        )
        job = DownloadJob(
            url="https://youtu.be/x",
            output_dir=tmp_path / "music",
            tracks=(Track("One", 0, 10), Track("Two", 10)),
            artist="Band",
            album="Album",
        )
        assert pipeline.execute(job) == []
        assert not (tmp_path / "music").exists() or not any((tmp_path / "music").rglob("*"))
