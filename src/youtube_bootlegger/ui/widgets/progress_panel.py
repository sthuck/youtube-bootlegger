"""Progress and status display widget."""

from datetime import datetime

from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ProgressPanelWidget(QWidget):
    """Widget displaying progress and status messages."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        self._stage_label = QLabel("Ready")
        layout.addWidget(self._stage_label)

        log_label = QLabel("Status Log:")
        layout.addWidget(log_label)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(100)
        layout.addWidget(self._log)

    def set_progress(self, percent: float) -> None:
        """Update progress bar."""
        self._progress_bar.setValue(int(percent))

    def add_message(self, message: str, level: str = "info") -> None:
        """Add status message to log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_upper = level.upper()
        self._log.append(f"[{timestamp}] [{level_upper}] {message}")
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )

    def clear(self) -> None:
        """Clear progress and messages."""
        self._progress_bar.setValue(0)
        self._stage_label.setText("Ready")
        self._log.clear()

    def set_stage(self, stage: str) -> None:
        """Display current pipeline stage."""
        self._stage_label.setText(stage)

    def set_complete(self) -> None:
        """Mark as complete."""
        self._progress_bar.setValue(100)
        self._stage_label.setText("Complete!")

    def set_error(self) -> None:
        """Mark as error state."""
        self._stage_label.setText("Error")
        self._stage_label.setStyleSheet("color: red;")

    def reset_style(self) -> None:
        """Reset label style."""
        self._stage_label.setStyleSheet("")
