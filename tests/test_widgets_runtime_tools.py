"""Widget UI: first-run runtime-tool downloads, the tools banner and Settings section.

The real RuntimeToolsSession, installer and ToolStore run against a temporary
tools folder; only HTTP (FakeToolServer), PATH and the video/pipeline
boundaries are faked. Tests click real widgets and read what they show.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import urllib.error

import pytest
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
)

from src.youtube_bootlegger.app_logic.runtime_tools import (
    FFMPEG_PATH_PLACEHOLDER,
    TOOLS_SECTION_TITLE,
    YTDLP_PATH_PLACEHOLDER,
)
from src.youtube_bootlegger.core.settings import AppSettings
from src.youtube_bootlegger.ui import main_window as main_window_module
from src.youtube_bootlegger.ui.widgets.settings_dialog import SettingsDialog
from tests.qml_support import DictBackend, make_video, wait_until
from tests.tools_support import fake_path, install_fake_tools, use_fake_tools


class FakeMessageBox:
    """Records message boxes instead of showing modal dialogs."""

    shown: list[tuple[str, str, str]] = []

    @classmethod
    def _record(cls, kind, _parent, title, text):
        cls.shown.append((kind, title, text))

    @classmethod
    def warning(cls, *args):
        cls._record("warning", *args)

    @classmethod
    def critical(cls, *args):
        cls._record("critical", *args)

    @classmethod
    def information(cls, *args):
        cls._record("information", *args)


@pytest.fixture
def widgets_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def server(monkeypatch):
    server = use_fake_tools(monkeypatch)
    yield server
    server.release()


@pytest.fixture
def store():
    return DictBackend()


@pytest.fixture
def tools_dir(tmp_path):
    return tmp_path / "tools"


@pytest.fixture
def open_main_window(widgets_app, server, store, tools_dir, monkeypatch):
    """Factory: a shown MainWindow on the shared settings store and tools folder."""
    monkeypatch.setattr(main_window_module, "QMessageBox", FakeMessageBox)
    FakeMessageBox.shown = []
    windows = []

    def open_window():
        settings = AppSettings(store, tools_dir=tools_dir)
        window = main_window_module.MainWindow(settings=settings, tools_http_get=server.http_get)
        window.URL_DEBOUNCE_MS = 10
        window.show()
        windows.append(window)
        return window

    yield open_window
    server.release()
    for window in windows:
        window.close()
        for pool in window.findChildren(QThreadPool):
            pool.waitForDone(5000)
        window._thread_pool.waitForDone(5000)
        window.deleteLater()
    QApplication.processEvents()


def child(parent, kind, name):
    widget = parent.findChild(kind, name)
    assert widget is not None, f"no {kind.__name__} named {name}"
    return widget


def banner_shown(window) -> bool:
    return child(window, QFrame, "toolsBanner").isVisibleTo(window)


def banner_text(window) -> str:
    return child(window, QLabel, "toolsBannerText").text()


def banner_button(window) -> QPushButton:
    return child(window, QPushButton, "toolsBannerButton")


def click(widget) -> None:
    assert widget.isVisible() and widget.isEnabled(), widget.objectName()
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton)


def installed(tools_dir, name) -> bool:
    return AppSettings(DictBackend(), tools_dir=tools_dir).tool_store.executable(name) is not None


def tools_warnings() -> list[str]:
    return [text for kind, title, text in FakeMessageBox.shown if title == "Tools Missing"]


def test_first_launch_downloads_by_itself_then_hides_banner(open_main_window, server, tools_dir, monkeypatch):
    fake_path(monkeypatch, set())
    server.hold()

    window = open_main_window()

    assert banner_shown(window)
    assert banner_button(window).text() == "Cancel"
    assert child(window, QProgressBar, "toolsBannerProgress").isVisibleTo(window)
    wait_until(lambda: len(server.requests) == 1)

    server.release()
    wait_until(lambda: not banner_shown(window), 5000)
    assert len(server.requests) == 3
    for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno"):
        assert installed(tools_dir, name), name

    click(child(window, QPushButton, "startButton"))
    assert tools_warnings() == []


def test_restart_with_tools_installed_downloads_nothing(open_main_window, server, monkeypatch):
    fake_path(monkeypatch, set())
    first = open_main_window()
    wait_until(lambda: not banner_shown(first), 5000)
    first.close()
    server.requests.clear()

    second = open_main_window()

    QTest.qWait(50)
    assert server.requests == []
    assert not banner_shown(second)


def test_cancel_mid_download_then_download_from_banner(open_main_window, server, tools_dir, monkeypatch):
    fake_path(monkeypatch, set())
    server.hold()
    window = open_main_window()
    wait_until(lambda: len(server.requests) == 1)

    click(banner_button(window))
    server.release()

    wait_until(lambda: banner_button(window).text() == "Download", 5000)
    assert banner_shown(window)
    assert "Download cancelled." in banner_text(window)
    assert not child(window, QProgressBar, "toolsBannerProgress").isVisibleTo(window)
    assert not installed(tools_dir, "ffmpeg")

    click(banner_button(window))

    wait_until(lambda: not banner_shown(window), 5000)
    assert installed(tools_dir, "ffmpeg")


def test_network_failure_shows_retry_that_recovers(open_main_window, server, tools_dir, monkeypatch):
    fake_path(monkeypatch, set())
    server.error = urllib.error.URLError("offline")

    window = open_main_window()

    wait_until(lambda: banner_button(window).text() == "Retry", 5000)
    assert banner_text(window).startswith("Tool download failed:")
    assert "offline" in banner_text(window)
    assert child(window, QFrame, "toolsBanner").property("isError") is True

    server.error = None
    click(banner_button(window))

    wait_until(lambda: not banner_shown(window), 5000)
    assert installed(tools_dir, "yt-dlp")


def test_tools_on_path_only_fetch_ytdlp(open_main_window, server, tools_dir, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})

    window = open_main_window()

    wait_until(lambda: not banner_shown(window), 5000)
    assert server.requests == [server.specs["yt-dlp"].assets[0].url]
    assert installed(tools_dir, "yt-dlp")
    assert not installed(tools_dir, "ffmpeg")


def fill_form(window, output_dir) -> None:
    child(window, QLineEdit, "urlField").setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    title = make_video().title
    wait_until(lambda: any(label.text() == title for label in window.findChildren(QLabel)))
    child(window, QPlainTextEdit, "tracklistArea").setPlainText("Intro - 0:00\nSong - 4:30")
    artist = child(window, QLineEdit, "artistField")
    artist.setFocus()
    QTest.keyClicks(artist, "The Band")
    child(window, QLineEdit, "dirField").setText(str(output_dir))


def test_start_while_ffmpeg_missing_shows_reason_and_does_not_start(
    open_main_window, server, fake_video, fake_pipeline, tmp_path, monkeypatch
):
    fake_path(monkeypatch, set())
    server.hold()
    window = open_main_window()
    fill_form(window, tmp_path)

    click(child(window, QPushButton, "startButton"))

    assert len(tools_warnings()) == 1
    assert "FFmpeg" in tools_warnings()[0]
    assert "finish downloading" in tools_warnings()[0]
    assert fake_pipeline.instances == []

    server.release()
    wait_until(lambda: not banner_shown(window), 5000)
    click(child(window, QPushButton, "startButton"))
    wait_until(lambda: len(fake_pipeline.instances) == 1)
    assert len(tools_warnings()) == 1


def test_start_with_ffmpeg_not_downloadable_explains(widgets_app, monkeypatch, fake_pipeline):
    """Without a tools folder nothing can be downloaded; Start says what to do."""
    fake_path(monkeypatch, set())
    monkeypatch.setattr(main_window_module, "QMessageBox", FakeMessageBox)
    FakeMessageBox.shown = []
    window = main_window_module.MainWindow(settings=AppSettings(DictBackend()))
    window.show()

    assert banner_shown(window)
    assert not banner_button(window).isVisibleTo(window)
    assert child(window, QFrame, "toolsBanner").property("isError") is True

    click(child(window, QPushButton, "startButton"))

    assert tools_warnings() == ["FFmpeg not found. Install it, or set its path in Settings."]
    assert fake_pipeline.instances == []
    window.close()
    window.deleteLater()


def in_settings(window, interact, *, save: bool = False) -> None:
    """Open Settings from the File menu and run interact(dialog) while it is up.

    The dialog is modal: its exec() loop runs until it closes, so the
    interaction runs from a timer inside that loop. Save clicks the dialog's
    Save button afterwards; otherwise it is cancelled. Failures are re-raised.
    """
    action = next(a for a in window.findChildren(QAction) if a.text() == "Settings...")
    errors: list[BaseException] = []

    def drive():
        dialog = window.findChild(SettingsDialog)
        try:
            wait_until(dialog.isVisible)
            interact(dialog)
            if save:
                click(next(b for b in dialog.findChildren(QPushButton) if b.text() == "Save"))
        except BaseException as error:  # re-raised in the test below
            errors.append(error)
        finally:
            if dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(0, drive)
    action.trigger()
    if errors:
        raise errors[0]
    wait_until(lambda: window.findChild(SettingsDialog) is None)


def test_settings_lists_tools_and_verify_replaces_tampered_file(
    open_main_window, server, tools_dir, monkeypatch
):
    fake_path(monkeypatch, set())
    install_fake_tools(tools_dir, server)
    window = open_main_window()
    assert not banner_shown(window)
    ffmpeg = AppSettings(DictBackend(), tools_dir=tools_dir).tool_store.executable("ffmpeg")
    original = ffmpeg.read_bytes()
    ffmpeg.write_bytes(b"tampered")

    def interact(dialog):
        assert child(dialog, QGroupBox, "toolsGroup").title() == TOOLS_SECTION_TITLE
        assert child(dialog, QLabel, "toolStatus_ffmpeg").text() == f"Downloaded: {ffmpeg}"
        assert child(dialog, QLabel, "toolStatus_yt-dlp").text().startswith("Downloaded: ")
        assert child(dialog, QLabel, "toolStatus_deno").text().startswith("Downloaded: ")
        assert child(dialog, QPushButton, "toolsOpenFolderButton").isEnabled()
        placeholders = {edit.placeholderText() for edit in dialog.findChildren(QLineEdit)}
        assert {YTDLP_PATH_PLACEHOLDER, FFMPEG_PATH_PLACEHOLDER} <= placeholders

        verify = child(dialog, QPushButton, "toolsVerifyButton")
        download = child(dialog, QPushButton, "toolsDownloadButton")
        server.hold()
        click(verify)

        assert not verify.isEnabled() and not download.isEnabled()
        assert banner_button(window).text() == "Cancel"
        server.release()
        wait_until(verify.isEnabled, 5000)
        assert child(dialog, QLabel, "toolStatus_ffmpeg").text() == f"Downloaded: {ffmpeg}"

    in_settings(window, interact)

    assert server.requests == [server.specs["ffmpeg"].assets[0].url]
    assert ffmpeg.read_bytes() == original
    assert not banner_shown(window)


def test_settings_download_missing_button_fetches_missing_tools(
    open_main_window, server, tools_dir, monkeypatch
):
    fake_path(monkeypatch, set())
    server.error = urllib.error.URLError("offline")
    window = open_main_window()
    wait_until(lambda: banner_button(window).text() == "Retry", 5000)
    server.error = None

    def interact(dialog):
        assert child(dialog, QLabel, "toolStatus_ffmpeg").text() == "Not downloaded yet"
        click(child(dialog, QPushButton, "toolsDownloadButton"))
        wait_until(lambda: child(dialog, QLabel, "toolStatus_ffmpeg").text().startswith(
            "Downloaded: "
        ), 5000)

    in_settings(window, interact)

    # FFmpeg can finish before Deno does; wait for the whole download.
    wait_until(lambda: not banner_shown(window), 5000)
    assert all(installed(tools_dir, name) for name in ("yt-dlp", "ffmpeg", "deno"))


def test_saving_settings_downloads_what_is_now_missing(
    open_main_window, server, tools_dir, store, monkeypatch
):
    """Clearing a custom FFmpeg path in Settings downloads FFmpeg after Save."""
    fake_path(monkeypatch, set())
    install_fake_tools(tools_dir, server, ("yt-dlp", "deno"))
    AppSettings(store, tools_dir=tools_dir).ffmpeg_path = "/opt/ffmpeg"
    window = open_main_window()
    assert server.requests == []

    def interact(dialog):
        assert child(dialog, QLabel, "toolStatus_ffmpeg").text() == "Custom path: /opt/ffmpeg"
        ffmpeg_field = next(
            e for e in dialog.findChildren(QLineEdit)
            if e.placeholderText() == FFMPEG_PATH_PLACEHOLDER
        )
        ffmpeg_field.clear()

    in_settings(window, interact, save=True)

    wait_until(lambda: installed(tools_dir, "ffmpeg"), 5000)
    wait_until(lambda: not banner_shown(window), 5000)
    assert server.requests == [server.specs["ffmpeg"].assets[0].url]


def test_saving_settings_mid_download_keeps_the_downloaded_ytdlp_default(
    open_main_window, server, tools_dir, store, monkeypatch
):
    """Saving Settings before yt-dlp arrives must not store "external off" for good."""
    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno"})
    server.hold()
    window = open_main_window()
    wait_until(lambda: server.requests)

    in_settings(window, lambda dialog: None, save=True)

    server.release()
    wait_until(lambda: installed(tools_dir, "yt-dlp"), 5000)
    wait_until(lambda: not banner_shown(window), 5000)
    assert AppSettings(store, tools_dir=tools_dir).use_external_ytdlp is True


def test_open_folder_survives_a_folder_that_cannot_be_created(
    open_main_window, server, tools_dir, monkeypatch
):
    """The tools path is taken by a file: clicking Open folder must not raise."""
    import sys
    from src.youtube_bootlegger.workers import tools_download_runner

    fake_path(monkeypatch, {"ffmpeg", "ffprobe", "deno", "yt-dlp"})
    tools_dir.parent.mkdir(parents=True, exist_ok=True)
    tools_dir.write_text("not a folder")
    server.error = urllib.error.URLError("offline")  # nothing can be installed there anyway
    opened, raised = [], []
    monkeypatch.setattr(
        tools_download_runner.QDesktopServices, "openUrl", lambda url: opened.append(url) or True
    )
    monkeypatch.setattr(sys, "excepthook", lambda *exc: raised.append(exc))
    window = open_main_window()

    in_settings(window, lambda dialog: click(child(dialog, QPushButton, "toolsOpenFolderButton")))

    assert raised == []
    assert opened == []


def test_open_folder_disabled_without_tools_dir(widgets_app, monkeypatch):
    fake_path(monkeypatch, {"ffmpeg", "ffprobe"})
    dialog = SettingsDialog(settings=AppSettings(DictBackend()))
    assert not child(dialog, QPushButton, "toolsOpenFolderButton").isEnabled()
    assert child(dialog, QLabel, "toolStatus_ffmpeg").text() == "From PATH: /usr/bin/ffmpeg"
    dialog.deleteLater()
