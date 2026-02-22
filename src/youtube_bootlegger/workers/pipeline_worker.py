"""Background worker for pipeline execution."""

from PySide6.QtCore import QRunnable

from ..core import DownloadSplitPipeline
from ..core.exceptions import YouTubeBootleggerError
from ..models import DownloadJob
from .signals import WorkerSignals


class PipelineWorker(QRunnable):
    """QRunnable worker for background pipeline execution."""

    def __init__(self, job: DownloadJob):
        """Initialize the worker.

        Args:
            job: The download job to execute.
        """
        super().__init__()
        self.job = job
        self.signals = WorkerSignals()
        self._pipeline: DownloadSplitPipeline | None = None

    def run(self) -> None:
        """Execute pipeline in background thread."""
        self.signals.started.emit()

        try:
            self._pipeline = DownloadSplitPipeline(
                progress_callback=self._on_progress,
            )

            output_files = self._pipeline.execute(self.job)
            output_paths = [str(f) for f in output_files]
            self.signals.finished.emit(output_paths)

        except YouTubeBootleggerError as e:
            self.signals.error.emit(str(e))
        except Exception as e:
            self.signals.error.emit(f"Unexpected error: {e}")

    def cancel(self) -> None:
        """Request cancellation of the pipeline."""
        if self._pipeline:
            self._pipeline.cancel()

    def _on_progress(self, stage: str, percent: float, message: str) -> None:
        """Forward progress to signal."""
        self.signals.progress.emit(stage, percent, message)
