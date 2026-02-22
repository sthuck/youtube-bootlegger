"""Application factory and setup."""

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .ui import MainWindow


def create_app() -> tuple[QApplication, MainWindow]:
    """Create and configure the application.

    Returns:
        Tuple of (QApplication, MainWindow).
    """
    app = QApplication(sys.argv)
    app.setApplicationName("YouTube Bootlegger")
    app.setApplicationVersion("0.1.0")

    window = MainWindow()
    return app, window


def run() -> int:
    """Run the application.

    Returns:
        Exit code.
    """
    app, window = create_app()

    # Allow Ctrl+C to work by letting Python process signals periodically
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Alternative: use a timer to allow Python signal processing
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    window.show()
    return app.exec()
