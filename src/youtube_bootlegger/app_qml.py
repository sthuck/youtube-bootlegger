"""QML application factory and entry point."""

import signal
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

from .qml_backend import AppBackend
from .resources import APP_LOGO_PNG


def run() -> int:
    """Launch the QML-based YouTube Bootlegger UI."""
    app = QGuiApplication(sys.argv)
    app.setApplicationName("YouTube Bootlegger")
    app.setApplicationVersion("0.1.0")
    app.setWindowIcon(QIcon(str(APP_LOGO_PNG)))

    engine = QQmlApplicationEngine()

    backend = AppBackend()
    engine.rootContext().setContextProperty("backend", backend)

    qml_file = Path(__file__).parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        return 1

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    return app.exec()
