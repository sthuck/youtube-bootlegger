"""Offscreen tests for the classic Qt widget UI's AI track-list finder flow.

Background workers are captured instead of run: tests emit their signals
directly, so no network, AI, or threads are involved.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from src.youtube_bootlegger.app_logic.track_finder import (
    API_HINT_TEXT,
    DETECT_FORMAT_BUTTON_LABEL,
    FIND_BUTTON_LABEL,
    FIND_TEMPLATE,
    NEEDS_API_MODEL_MESSAGE,
)
from src.youtube_bootlegger.core.settings import LlmProvider
from src.youtube_bootlegger.core.video_info import DEFAULT_COMMENT_LIMIT, VideoInfo
from src.youtube_bootlegger.llm.track_finder import (
    FindOutcome,
    FoundTrack,
    TrackSource,
    TracklistFindResult,
)
from src.youtube_bootlegger.ui import main_window as main_window_module
from src.youtube_bootlegger.ui.widgets.settings_dialog import SettingsDialog
from src.youtube_bootlegger.workers import (
    TracklistAiWorker,
    TracklistFindWorker,
    VideoInfoWorker,
)
from tests.test_downloader import make_settings
from tests.tools_support import fake_path

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
OTHER_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
COMMENT = TrackSource("comment:3", "comment #3", "0:00 Intro\n4:05 Second Song")
FOUND = TracklistFindResult(
    FindOutcome.FOUND,
    COMMENT,
    (FoundTrack("Intro", 0), FoundTrack("Second Song", 245)),
    artist_name="The Band",
    album_name="Live 2024",
)


class FakePool:
    """Captures started workers instead of running them."""

    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)

    def of_type(self, kind):
        return [worker for worker in self.started if isinstance(worker, kind)]


class FakeMessageBox:
    """Records message boxes instead of showing modal dialogs."""

    shown: list[tuple[str, str]] = []

    @classmethod
    def _record(cls, kind, _parent, _title, text):
        cls.shown.append((kind, text))

    @classmethod
    def warning(cls, *args):
        cls._record("warning", *args)

    @classmethod
    def critical(cls, *args):
        cls._record("critical", *args)

    @classmethod
    def information(cls, *args):
        cls._record("information", *args)


def make_video(**overrides) -> VideoInfo:
    fields = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Live at the Venue",
        "channel": "Band Channel",
        "duration": 3600,
        "duration_string": "1:00:00",
        "thumbnail_url": "",
        "description": "0:00 Intro",
    }
    fields.update(overrides)
    return VideoInfo(**fields)


@pytest.fixture
def widgets_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def settings():
    settings = make_settings()
    settings.llm_provider = LlmProvider.OPENAI
    settings.openai_api_key = "sk-test"
    return settings


@pytest.fixture
def window(widgets_app, settings, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe"})
    monkeypatch.setattr(main_window_module, "QMessageBox", FakeMessageBox)
    FakeMessageBox.shown = []
    window = main_window_module.MainWindow(settings=settings)
    window._thread_pool = FakePool()
    yield window
    window.deleteLater()


def tracklist(window) -> str:
    return window._tracklist_input.get_text()


def log_text(window) -> str:
    return window._progress_panel._log.toPlainText()


def load_video(window, url=URL, info=None):
    """Enter a URL and deliver its preview; returns the find worker, if one started."""
    window._url_input._input.setText(url)
    window._fetch_video_info()
    video_worker = window._thread_pool.of_type(VideoInfoWorker)[-1]
    video_worker.signals.finished.emit(info or make_video())
    finders = window._thread_pool.of_type(TracklistFindWorker)
    return finders[-1] if finders else None


def finish(worker, result=FOUND):
    worker.signals.finished.emit(worker._token, result)


class TestAutoFind:
    def test_fills_form_shows_banner_and_logs_source(self, window):
        worker = load_video(window)
        assert worker is not None
        assert window._tracklist_input._searching_row.isVisibleTo(window)

        finish(worker)

        assert tracklist(window) == "Intro - 0:00\nSecond Song - 4:05"
        assert window._tracklist_input.get_template() == FIND_TEMPLATE
        assert window._metadata_input.get_artist() == "The Band"
        assert window._metadata_input.get_album() == "Live 2024"
        tracklist_input = window._tracklist_input
        assert not tracklist_input._searching_row.isVisibleTo(window)
        assert tracklist_input._banner_row.isVisibleTo(window)
        assert "comment #3: 2 tracks" in tracklist_input._banner_label.text()
        assert tracklist_input._template_ai_marker.isVisibleTo(window)
        log = log_text(window)
        assert "Video info: description, 0 chapters, 0 comments" in log
        assert "AI: found 2 timestamped tracks in comment #3" in log
        assert f'AI: format set to "{FIND_TEMPLATE}"' in log
        assert tracklist_input._ai_button.text() == DETECT_FORMAT_BUTTON_LABEL

    def test_preview_requests_comments_with_an_api_model(self, window):
        load_video(window)
        assert window._thread_pool.of_type(VideoInfoWorker)[0].comment_limit == (
            DEFAULT_COMMENT_LIMIT
        )

    def test_untimed_leaves_box_empty_and_logs(self, window):
        worker = load_video(window)
        finish(worker, TracklistFindResult(FindOutcome.UNTIMED, COMMENT))

        assert tracklist(window) == ""
        assert not window._tracklist_input._banner_row.isVisibleTo(window)
        assert "found song names without timestamps in comment #3" in log_text(window)

    def test_checkbox_off_does_not_search(self, window, settings):
        settings.auto_find_tracklist = False
        assert load_video(window) is None
        assert window._tracklist_input._ai_button.text() == FIND_BUTTON_LABEL
        assert window._tracklist_input._ai_button.isEnabled()

    def test_same_video_again_uses_cache(self, window):
        finish(load_video(window))
        load_video(window, OTHER_URL, make_video(video_id="other"))  # clears the fill
        assert tracklist(window) == ""

        load_video(window, URL)

        finders = window._thread_pool.of_type(TracklistFindWorker)
        assert len(finders) == 2  # first video, other video; none for the repeat
        assert tracklist(window) == "Intro - 0:00\nSecond Song - 4:05"
        assert window._tracklist_input._banner_row.isVisibleTo(window)


class TestCancelling:
    def test_stop_discards_result(self, window):
        worker = load_video(window)
        window._tracklist_input.stop_find_requested.emit()
        assert not window._tracklist_input._searching_row.isVisibleTo(window)

        finish(worker)

        assert tracklist(window) == ""
        assert "AI: search stopped" in log_text(window)

    def test_typing_during_search_cancels_and_keeps_text(self, window):
        worker = load_video(window)
        window._tracklist_input._input.setPlainText("My Song - 0:00")

        finish(worker)

        assert tracklist(window) == "My Song - 0:00"
        assert "search stopped because you edited the track list" in log_text(window)

    def test_url_change_clears_unedited_fill(self, window):
        finish(load_video(window))
        window._url_input._input.setText(OTHER_URL)

        assert tracklist(window) == ""
        assert window._metadata_input.get_artist() == ""
        assert not window._tracklist_input._banner_row.isVisibleTo(window)

    def test_url_change_keeps_edited_fill(self, window):
        finish(load_video(window))
        window._tracklist_input._input.setPlainText("Intro - 0:00\nMy Fix - 4:05")
        window._url_input._input.setText(OTHER_URL)

        assert tracklist(window) == "Intro - 0:00\nMy Fix - 4:05"

    def test_stale_preview_is_ignored(self, window):
        window._url_input._input.setText(URL)
        window._fetch_video_info()
        old_worker = window._thread_pool.of_type(VideoInfoWorker)[-1]
        window._url_input._input.setText(OTHER_URL)
        window._fetch_video_info()

        old_worker.signals.finished.emit(make_video())

        assert window._video_preview.get_video_info() is None
        assert not window._thread_pool.of_type(TracklistFindWorker)


class TestBanner:
    def test_undo_restores_previous_values(self, window):
        window._metadata_input.set_album("My Album")
        finish(load_video(window))
        assert window._metadata_input.get_album() == "My Album"  # not overwritten

        window._tracklist_input.undo_find_requested.emit()

        assert tracklist(window) == ""
        assert window._metadata_input.get_artist() == ""
        assert not window._tracklist_input._banner_row.isVisibleTo(window)
        assert not window._tracklist_input._template_ai_marker.isVisibleTo(window)

    def test_dismiss_hides_banner_only(self, window):
        finish(load_video(window))
        window._tracklist_input.find_banner_dismissed.emit()

        assert not window._tracklist_input._banner_row.isVisibleTo(window)
        assert tracklist(window) == "Intro - 0:00\nSecond Song - 4:05"


class TestWithoutApiModel:
    def test_lite_shows_hint_and_find_explains(self, window, settings):
        settings.llm_provider = LlmProvider.CHATGPT_LITE
        assert load_video(window) is None
        assert window._thread_pool.of_type(VideoInfoWorker)[0].comment_limit == 0

        tracklist_input = window._tracklist_input
        assert tracklist_input._hint_row.isVisibleTo(window)
        assert API_HINT_TEXT in tracklist_input._hint_label.text()

        tracklist_input._ai_button.click()
        assert FakeMessageBox.shown == [("warning", NEEDS_API_MODEL_MESSAGE)]

        tracklist_input.api_hint_dismissed.emit()
        assert not tracklist_input._hint_row.isVisibleTo(window)


class TestManualButton:
    def test_find_click_searches_and_error_is_shown(self, window, settings):
        settings.auto_find_tracklist = False
        load_video(window)
        window._tracklist_input._ai_button.click()

        worker = window._thread_pool.of_type(TracklistFindWorker)[-1]
        worker.signals.error.emit(worker._token, "rate limited")

        assert FakeMessageBox.shown == [("critical", "rate limited")]
        assert "AI: couldn't find a track list: rate limited" in log_text(window)

    def test_auto_find_error_only_logs(self, window):
        worker = load_video(window)
        worker.signals.error.emit(worker._token, "rate limited")
        assert FakeMessageBox.shown == []
        assert "rate limited" in log_text(window)

    def test_filled_box_detects_format_as_before(self, window, settings):
        settings.auto_find_tracklist = False
        load_video(window)
        window._tracklist_input._input.setPlainText("1. Song (0:00)")
        assert window._tracklist_input._ai_button.text() == DETECT_FORMAT_BUTTON_LABEL

        window._tracklist_input._ai_button.click()

        assert not window._thread_pool.of_type(TracklistFindWorker)
        detect = window._thread_pool.of_type(TracklistAiWorker)
        assert len(detect) == 1


def test_settings_dialog_saves_log_ai_requests(widgets_app, settings):
    dialog = SettingsDialog(settings=settings)
    assert not dialog._log_requests_checkbox.isChecked()
    dialog._log_requests_checkbox.setChecked(True)
    dialog._on_save()
    assert settings.log_ai_requests is True
    dialog.deleteLater()


def test_settings_dialog_saves_auto_find(widgets_app, settings):
    dialog = SettingsDialog(settings=settings)
    assert dialog._auto_find_checkbox.isChecked()
    dialog._auto_find_checkbox.setChecked(False)
    dialog._on_save()
    assert settings.auto_find_tracklist is False
    dialog.deleteLater()


def test_settings_dialog_fits_screen_with_buttons_visible(widgets_app, settings):
    dialog = SettingsDialog(settings=settings)
    dialog.show()
    widgets_app.processEvents()
    available = dialog.screen().availableGeometry()
    assert dialog.height() <= max(available.height(), dialog.minimumHeight())
    save = dialog.findChild(QDialogButtonBox)
    assert save.isVisible()
    assert save.geometry().bottom() <= dialog.height()
    dialog.close()


def test_settings_dialog_saves_cookies_from_browser_and_shows_tooltip(widgets_app, settings):
    from src.youtube_bootlegger.core.settings import CookieBrowser

    dialog = SettingsDialog(settings=settings)
    assert "Windows" in dialog._cookies_info_icon.toolTip()
    assert "lock" in dialog._cookies_info_icon.toolTip().lower()
    idx = dialog._cookies_browser_combo.findData(CookieBrowser.FIREFOX)
    dialog._cookies_browser_combo.setCurrentIndex(idx)
    dialog._on_save()
    assert settings.cookies_from_browser == CookieBrowser.FIREFOX
    dialog.deleteLater()


def test_saving_settings_preserves_invalid_url_error(window, settings, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from src.youtube_bootlegger.core.settings import CookieBrowser

    window._url_input._input.setText("not-a-valid-url")
    window._url_input.set_error("Invalid YouTube URL")

    class AcceptedDialog:
        tools_download_requested = tools_verify_requested = type(
            "FakeSignal", (), {"connect": lambda self, slot: None}
        )()

        def __init__(self, parent=None, settings=None):
            pass

        def deleteLater(self):
            pass

        def exec(self):
            settings.cookies_from_browser = CookieBrowser.FIREFOX
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("src.youtube_bootlegger.ui.main_window.SettingsDialog", AcceptedDialog)
    window._open_settings_dialog()
    assert window._url_input._error_label.text() == "Invalid YouTube URL"
