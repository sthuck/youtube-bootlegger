"""Shared pytest fixtures."""

import pytest
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.core.video_info import VideoInfo


@pytest.fixture(scope="session")
def qapp():
    """Provide a single QApplication for the whole test session."""
    app = QApplication.instance() or QApplication([])
    yield app


class FakeSettingsBackend:
    """In-memory stand-in for QSettings, avoiding disk I/O in tests."""

    def __init__(self, initial: dict | None = None):
        self._values = dict(initial or {})
        self.sync_count = 0

    def value(self, key, default=None):
        return self._values.get(key, default)

    def setValue(self, key, value):
        self._values[key] = value

    def sync(self):
        self.sync_count += 1


@pytest.fixture
def settings():
    """Return AppSettings backed by in-memory storage."""
    return AppSettings(FakeSettingsBackend())


@pytest.fixture
def video_info():
    """Return a representative VideoInfo."""
    return VideoInfo(
        video_id="abc123",
        title="Live at the Roxy 1979",
        channel="Bootleg Channel",
        duration=3600,
        duration_string="1:00:00",
        thumbnail_url="https://example.com/thumb.jpg",
        view_count=12345,
        upload_date="20240101",
    )
