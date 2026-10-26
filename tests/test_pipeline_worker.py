"""Tests for the Qt PipelineWorker used by the widget and QML front-ends."""

from pathlib import Path

from src.youtube_bootlegger.core import pipeline as pipeline_module
from src.youtube_bootlegger.models import DownloadJob, Track
from src.youtube_bootlegger.workers import pipeline_worker as worker_module
from src.youtube_bootlegger.workers.pipeline_worker import PipelineWorker


def make_job(tmp_path: Path) -> DownloadJob:
    return DownloadJob(
        url="https://youtu.be/x",
        output_dir=tmp_path / "music",
        tracks=(Track("One", 0),),
        artist="Band",
    )


class TestCancelBeforeRun:
    """Review finding #3: Cancel while the worker is still queued must stick."""

    def test_cancel_before_run_skips_the_job(self, tmp_path, monkeypatch):
        downloads = []
        monkeypatch.setattr(
            pipeline_module.AudioDownloader,
            "download",
            lambda self, url: downloads.append(url),
        )
        worker = PipelineWorker(make_job(tmp_path))
        finished = []
        worker.signals.finished.connect(finished.append)

        worker.cancel()  # Still queued in QThreadPool: run() hasn't started.
        worker.run()

        assert downloads == []
        assert finished == [[]]

    def test_pipeline_uses_given_settings(self, tmp_path, monkeypatch):
        created = {}

        class SpyPipeline:
            def __init__(self, **kwargs):
                created.update(kwargs)

        monkeypatch.setattr(worker_module, "DownloadSplitPipeline", SpyPipeline)
        sentinel = object()
        PipelineWorker(make_job(tmp_path), settings=sentinel)
        assert created["settings"] is sentinel
