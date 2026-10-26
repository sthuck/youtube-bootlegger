"""Cancellation shared by pipeline stages, including killing child processes."""

import os
import signal
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from .exceptions import OperationCancelledError

# How long a terminated child gets to exit before it is force-killed.
TERMINATE_GRACE_SECONDS = 5

_IS_POSIX = os.name == "posix"


def _signal_process_tree(process: subprocess.Popen, sig: int) -> None:
    """Signal the process and everything it spawned (e.g. yt-dlp's ffmpeg)."""
    try:
        if _IS_POSIX:
            # Children are started in their own session, so the group id is the pid.
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except (ProcessLookupError, PermissionError):
        pass  # Already exited.


class CancelToken:
    """Thread-safe cancel flag that also stops the currently running child process.

    cancel() may be called from any thread (typically the UI thread) while a
    worker thread runs the pipeline. Work checks raise_if_cancelled() between
    steps; long-running subprocesses started via child_process() are
    terminated immediately so the worker unblocks right away.
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        """Request cancellation and terminate the running child process, if any."""
        self._event.set()
        # The lock keeps child_process from unregistering (and finally
        # reaping) the process mid-signal. Callers may still reap it inside
        # their with-block, so re-check with poll(): a reaped pid could
        # belong to an unrelated process by now.
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                _signal_process_tree(self._process, signal.SIGTERM)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelledError("Cancelled")

    @contextmanager
    def child_process(self, cmd: list[str], **popen_kwargs) -> Iterator[subprocess.Popen]:
        """Start a subprocess that cancel() can terminate.

        The process (and its process group on POSIX) is always stopped when
        the block exits, so nothing is orphaned on errors or cancellation.
        Callers should call raise_if_cancelled() after the process ends, before
        interpreting its exit code.

        Raises:
            OperationCancelledError: If already cancelled before starting.
        """
        self.raise_if_cancelled()
        # Never inherit the terminal as stdin: in the TUI, ffmpeg would read
        # the user's keystrokes (e.g. "q" quietly ends an encode early).
        popen_kwargs.setdefault("stdin", subprocess.DEVNULL)
        process = subprocess.Popen(cmd, start_new_session=_IS_POSIX, **popen_kwargs)
        with self._lock:
            self._process = process
        try:
            if self.cancelled:  # cancel() ran between Popen and registration.
                _signal_process_tree(process, signal.SIGTERM)
            yield process
        finally:
            with self._lock:
                self._process = None
            self._stop(process)

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        # Only signal while the child is unreaped: once reaped, its pid (and
        # so its process-group id) could be reused by an unrelated process.
        if process.poll() is None:
            _signal_process_tree(process, signal.SIGTERM)
            try:
                process.wait(timeout=TERMINATE_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                _signal_process_tree(process, getattr(signal, "SIGKILL", signal.SIGTERM))
                process.wait()
