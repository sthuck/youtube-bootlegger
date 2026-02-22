"""Worker signals for thread communication."""

from PySide6.QtCore import QObject, Signal


class WorkerSignals(QObject):
    """Signals for worker thread communication.

    Signals:
        started: Emitted when the worker starts.
        progress: Emitted with (stage, percent, message) on progress updates.
        finished: Emitted with list of output paths on success.
        error: Emitted with error message on failure.
    """

    started = Signal()
    progress = Signal(str, float, str)
    finished = Signal(list)
    error = Signal(str)
