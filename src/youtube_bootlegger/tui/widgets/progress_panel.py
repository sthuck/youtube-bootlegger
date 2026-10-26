"""Pipeline progress bar with stage label, and the timestamped status log."""

from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import ProgressBar, RichLog, Static

LEVEL_STYLES = {
    "info": "",
    "debug": "dim",
    "warn": "yellow",
    "error": "bold red",
}


class ProgressPanel(Horizontal):
    """Stage text (e.g. "Downloading: 42%") next to a progress bar."""

    def compose(self) -> ComposeResult:
        yield Static("Ready", id="progress-stage")
        yield ProgressBar(total=100, show_eta=False, id="progress-bar")

    def set_progress(self, stage: str, percent: float | None = None) -> None:
        self.query_one("#progress-stage", Static).update(stage)
        if percent is not None:
            self.query_one("#progress-bar", ProgressBar).update(progress=percent)


class StatusLog(RichLog):
    """Append-only log with a timestamp and per-level styling."""

    def __init__(self, **kwargs) -> None:
        super().__init__(wrap=True, markup=False, max_lines=2000, **kwargs)

    def log_message(self, message: str, level: str = "info") -> None:
        line = Text(datetime.now().strftime("%H:%M:%S "), style="dim")
        line.append(message, style=LEVEL_STYLES.get(level, ""))
        self.write(line)
