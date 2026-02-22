"""Application factory and setup."""

import sys

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
    window.show()
    return app.exec()
