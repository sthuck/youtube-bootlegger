"""Shared helpers for driving the QML UI headlessly with QTest."""

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPointF, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.app_qml import create_qml_engine
from src.youtube_bootlegger.core.exceptions import ValidationError
from src.youtube_bootlegger.core.video_info import VideoInfo
from src.youtube_bootlegger.qml_backend import AppBackend

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
OTHER_URL = "https://www.youtube.com/watch?v=9bZkp7q19f0"


class DictBackend:
    """In-memory QSettings stand-in for isolated test runs."""

    def __init__(self):
        self.data = {}
        self.synced = 0

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def sync(self):
        self.synced += 1


def make_video(**overrides) -> VideoInfo:
    fields = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Live at the Venue",
        "channel": "Band Channel",
        "duration": 3600,
        "duration_string": "1:00:00",
        "thumbnail_url": "",
        "view_count": 1_500,
        "upload_date": "20240131",
    }
    fields.update(overrides)
    return VideoInfo(**fields)


class FakePipeline:
    """Stands in for DownloadSplitPipeline; behaviour configured per test.

    Mirrors the real pipeline's contract: the constructor takes the same
    arguments (checked by a test), and a cancelled run returns [].
    """

    instances: list["FakePipeline"] = []
    outcome: object = None
    gate: threading.Event | None = None

    def __init__(self, progress_callback=None, log_callback=None, settings=None):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.settings = settings
        self.cancelled = False
        self.job = None
        FakePipeline.instances.append(self)

    def execute(self, job):
        self.job = job
        if self.log_callback:
            self.log_callback("Starting fake pipeline")
        if self.progress_callback:
            self.progress_callback("download", 50.0, "Downloading 50%")
        if FakePipeline.gate is not None:
            FakePipeline.gate.wait(timeout=5)
        if self.cancelled:
            return []
        if isinstance(FakePipeline.outcome, Exception):
            raise FakePipeline.outcome
        return FakePipeline.outcome

    def cancel(self):
        self.cancelled = True


class FetchCall:
    """One blocked fetch_video_info call, resolved explicitly by the test."""

    def __init__(self, url: str):
        self.url = url
        self._released = threading.Event()
        self._title = ""
        self._error = ""

    def succeed(self, title: str) -> None:
        self._title = title
        self._released.set()

    def fail(self, message: str) -> None:
        self._error = message
        self._released.set()

    def wait(self) -> VideoInfo:
        self._released.wait(timeout=5)
        if self._error:
            raise ValidationError(self._error)
        return make_video(title=self._title)


class GatedFetch:
    """fetch_video_info replacement whose calls block until the test resolves them.

    Lets tests deliver video-info results out of order, the way slow network
    responses really arrive.
    """

    def __init__(self):
        self.calls: list[FetchCall] = []

    def __call__(self, url, settings=None):
        call = FetchCall(url)
        self.calls.append(call)
        return call.wait()

    def release_all(self) -> None:
        for call in self.calls:
            call.succeed("released")


@contextmanager
def capture_qml_warnings():
    """Collect every QML warning/error emitted while the block runs."""
    messages: list[str] = []

    def handler(mode, context, message):
        if mode == QtMsgType.QtDebugMsg or mode == QtMsgType.QtInfoMsg:
            return
        source = context.file or ""
        if ".qml" in source or ".qml:" in message:
            messages.append(message)

    previous = qInstallMessageHandler(handler)
    try:
        yield messages
    finally:
        qInstallMessageHandler(previous)


@contextmanager
def open_window(backend: AppBackend):
    """Load Main.qml against backend; yield (window, qml_warnings), then tear down.

    QML warnings are captured from before the engine loads, so binding and
    reference errors raised during startup are seen too.
    """
    app = QApplication.instance()
    with capture_qml_warnings() as warnings:
        engine = create_qml_engine(backend)
        roots = engine.rootObjects()
        assert roots, f"QML failed to load: {warnings}"
        window: QQuickWindow = roots[0]
        QTest.qWaitForWindowExposed(window)
        window.requestActivate()
        QTest.qWaitForWindowActive(window)
        app.processEvents()
        try:
            yield window, warnings
        finally:
            backend._thread_pool.waitForDone(2000)
            window.close()
            app.processEvents()
            del window
            del roots
            del engine
            app.processEvents()


def _walk_visual_items(item: QQuickItem, object_name: str) -> QQuickItem | None:
    if item.objectName() == object_name:
        return item
    for child in item.childItems():
        found = _walk_visual_items(child, object_name)
        if found is not None:
            return found
    return None


def find_item(window: QQuickWindow, object_name: str) -> QObject:
    """Look up a QML object by objectName across both QObject and visual item trees."""
    item = window.findChild(QObject, object_name)
    if item is not None:
        return item
    if isinstance(window, QQuickWindow) and window.contentItem() is not None:
        item = _walk_visual_items(window.contentItem(), object_name)
    assert item is not None, f"QML item {object_name!r} not found"
    return item


def click_item(window: QQuickWindow, object_name: str) -> None:
    """Click the center of a visible QQuickItem using QTest.mouseClick.

    If the item is inside a Flickable/ScrollView and currently scrolled outside
    the Flickable's viewport, scrolls the enclosing Flickable first.
    """
    item = find_item(window, object_name)
    assert isinstance(item, QQuickItem), f"{object_name!r} is not a QQuickItem"
    local_center = QPointF(item.width() / 2, item.height() / 2)
    parent = item.parentItem()
    while parent is not None:
        if parent.metaObject().indexOfProperty("contentY") != -1:
            in_flick = item.mapToItem(parent, local_center)
            if in_flick.y() >= parent.height() or in_flick.y() < 0:
                current_y = parent.property("contentY")
                delta = in_flick.y() - (parent.height() / 2)
                parent.setProperty("contentY", max(0.0, current_y + delta))
                QApplication.processEvents()
            break
        parent = parent.parentItem()
    center = item.mapToScene(local_center)
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        center.toPoint(),
    )
    QApplication.processEvents()


def type_text(window: QQuickWindow, object_name: str, value: str) -> None:
    """Focus a text field, replace its contents, and type value key by key.

    Use this for anything a user types: every keystroke goes through the
    field's handlers and back through the backend, as it does in the app.
    """
    item = find_item(window, object_name)
    item.forceActiveFocus()
    QApplication.processEvents()
    assert item.property("activeFocus"), f"{object_name!r} did not take focus"
    QTest.keyClick(window, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    if value:
        # QTest.keyClicks only accepts QWidgets; send one key per character.
        for char in value:
            QTest.keyClick(window, char)
    else:
        QTest.keyClick(window, Qt.Key.Key_Backspace)
    QApplication.processEvents()


def press_key(window: QQuickWindow, key: Qt.Key) -> None:
    QTest.keyClick(window, key)
    QApplication.processEvents()


def set_text(window: QQuickWindow, object_name: str, value: str) -> None:
    """Replace a field's text in one step, like a paste.

    Use for pasted input (URLs, multi-line tracklists); use type_text for
    anything typed.
    """
    item = find_item(window, object_name)
    item.setProperty("text", value)
    QApplication.processEvents()


def prop(window: QQuickWindow, object_name: str, property_name: str = "text"):
    """Read a QML property from a named item."""
    return find_item(window, object_name).property(property_name)


def wait_until(condition, timeout_ms: int = 2000, step_ms: int = 15) -> None:
    """Spin the Qt event loop until condition() is truthy or timeout expires."""
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
        QTest.qWait(step_ms)
    QApplication.processEvents()
    assert condition(), "Timed out waiting for condition"


def wait_for_workers(backend: AppBackend) -> None:
    """Wait until background workers finish and their queued signals are delivered."""
    backend._thread_pool.waitForDone(2000)
    QTest.qWait(20)


def load_video(window: QQuickWindow, backend: AppBackend, url: str = VALID_URL) -> None:
    set_text(window, "urlField", url)
    wait_until(lambda: backend.videoLoaded)


def fill_form(
    window: QQuickWindow,
    backend: AppBackend,
    artist: str = "The Band",
    output_dir: str | Path = "/tmp",
) -> None:
    load_video(window, backend)
    set_text(window, "tracklistArea", "Intro - 0:00\nSong - 4:30")
    type_text(window, "artistField", artist)
    type_text(window, "dirField", str(output_dir))
