"""Background worker for pipeline execution."""

from PySide6.QtCore import QRunnable

from ..core import DownloadSplitPipeline
from ..core.settings import AppSettings
from ..core.exceptions import YouTubeBootleggerError
from ..models import DownloadJob
from .signals import WorkerSignals


class PipelineWorker(QRunnable):
    """QRunnable worker for background pipeline execution."""

    def __init__(self, job: DownloadJob, settings: AppSettings | None = None):
        """Initialize the worker.

        Args:
            job: The download job to execute.
            settings: Application settings. Defaults to the shared singleton.
        """
        super().__init__()
        self.job = job
        self.signals = WorkerSignals()
        # Created here, not in run(): a Cancel while the worker is still
        # queued in the thread pool must reach the pipeline and stick.
        self._pipeline = DownloadSplitPipeline(
            progress_callback=self._on_progress,
            log_callback=self._on_log,
            settings=settings,
        )

    def run(self) -> None:
        """Execute pipeline in background thread."""
        self.signals.started.emit()

        try:
            output_files = self._pipeline.execute(self.job)
            output_paths = [str(f) for f in output_files]
            self.signals.finished.emit(output_paths)

        except YouTubeBootleggerError as e:
            self.signals.error.emit(str(e))
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {e}")

    def cancel(self) -> None:
        """Request cancellation of the pipeline, even before run() starts."""
        self._pipeline.cancel()

    def _on_progress(self, stage: str, percent: float, message: str) -> None:
        """Forward progress to signal."""
        self.signals.progress.emit(stage, percent, message)

    def _on_log(self, message: str) -> None:
        """Forward log message to signal."""
        self.signals.log.emit(message)
