"""QML application factory and entry point."""

import signal
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from .qml_backend import AppBackend
from .resources import APP_LOGO_PNG

APP_NAME = "YouTube Bootlegger"
QML_MAIN_FILE = Path(__file__).parent / "qml" / "Main.qml"


def _configure_platform_identity() -> None:
    """Set the application identity used by Qt and the native menu bar."""
    if sys.platform == "darwin":
        # macOS shows the process name in the menu bar when running from a script.
        sys.argv[0] = APP_NAME

    QCoreApplication.setOrganizationName(APP_NAME)
    QCoreApplication.setApplicationName(APP_NAME)


def create_qml_engine(backend: AppBackend) -> QQmlApplicationEngine:
    """Create a QQmlApplicationEngine wired to the given AppBackend and load Main.qml."""
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty(
        "logoUrl",
        QUrl.fromLocalFile(str(APP_LOGO_PNG)),
    )
    engine.load(QUrl.fromLocalFile(str(QML_MAIN_FILE)))
    return engine


def run() -> int:
    """Launch the QML-based YouTube Bootlegger UI."""
    _configure_platform_identity()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion("0.1.0")
    app.setWindowIcon(QIcon(str(APP_LOGO_PNG)))

    backend = AppBackend()
    engine = create_qml_engine(backend)

    if not engine.rootObjects():
        return 1

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    exit_code = app.exec()
    del engine
    return exit_code
