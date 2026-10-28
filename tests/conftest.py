"""Fixtures for the headless QML tests (test_qml.py, test_e2e_pipeline.py)."""

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.qml_backend import AppBackend
from src.youtube_bootlegger.qml_backend import backend as backend_module
from src.youtube_bootlegger.workers import pipeline_worker as pipeline_worker_module
from src.youtube_bootlegger.workers import tracklist_find_worker as find_worker_module
from src.youtube_bootlegger.workers import video_info_worker as video_worker_module
from tests.qml_support import (
    DictBackend,
    FakeFind,
    FakePipeline,
    GatedFetch,
    make_video,
    open_window,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def settings_store():
    return DictBackend()


@pytest.fixture
def app_settings(settings_store):
    return AppSettings(settings_store)


@pytest.fixture
def ffmpeg_available(monkeypatch):
    monkeypatch.setattr(backend_module, "is_ffmpeg_available", lambda cmd: True)


@pytest.fixture
def fake_video(monkeypatch, ffmpeg_available):
    calls = []

    def fetch(url, settings=None, comment_limit=0):
        calls.append((url, settings))
        return make_video()

    monkeypatch.setattr(video_worker_module, "fetch_video_info", fetch)
    return calls


@pytest.fixture
def gated_fetch(monkeypatch, ffmpeg_available):
    fetch = GatedFetch()
    monkeypatch.setattr(video_worker_module, "fetch_video_info", fetch)
    yield fetch
    fetch.release_all()


@pytest.fixture
def fake_find(monkeypatch):
    """Replace the AI track-list finder; never makes a real AI request."""
    find = FakeFind()
    monkeypatch.setattr(find_worker_module, "find_tracklist", find)
    yield find
    find.release()


@pytest.fixture
def fake_pipeline(monkeypatch):
    FakePipeline.instances = []
    FakePipeline.outcome = [Path("/out/01 - Intro.mp3"), Path("/out/02 - Song.mp3")]
    FakePipeline.gate = None
    monkeypatch.setattr(pipeline_worker_module, "DownloadSplitPipeline", FakePipeline)
    yield FakePipeline
    if FakePipeline.gate is not None:
        FakePipeline.gate.set()


@pytest.fixture
def qml_harness(qapp, app_settings, fake_video, fake_find):
    """Main.qml + AppBackend; fails the test if any QML warning was emitted.

    Network access is faked via fake_video and AI track-list finding via
    fake_find; tests that request gated_fetch after qml_harness replace it.
    """
    backend = AppBackend(settings=app_settings)
    backend.URL_DEBOUNCE_MS = 10
    with open_window(backend) as (window, warnings):
        yield window, backend, app_settings
        assert warnings == [], f"QML emitted warnings: {warnings}"
