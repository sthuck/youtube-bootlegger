"""Runs runtime-tool downloads for the TUI on a background thread.

All decisions and strings live in app_logic.RuntimeToolsSession; this module
only starts install_tools on a daemon thread, forwards its progress and
outcome to the session on the UI thread, and tells the app to re-render.
"""

from collections.abc import Callable

from ..app_logic import RuntimeToolsSession
from ..core.cancellation import CancelToken
from ..core.exceptions import OperationCancelledError, ToolInstallError
from ..core.settings import AppSettings
from ..core.tool_installer import HttpGet, InstallProgress, install_tools


class ToolsDownloader:
    """Owns the per-app RuntimeToolsSession and the running download, if any.

    Args:
        settings: Where tools are stored and which are configured.
        http_get: Opens a download URL (injected by tests).
        run_in_background: Starts blocking work on a daemon thread.
        post: Runs a callback on the UI thread (dropped once the app exited).
        on_change: Called on the UI thread whenever the banner may change.
    """

    def __init__(
        self,
        settings: AppSettings,
        *,
        http_get: HttpGet,
        run_in_background: Callable[..., None],
        post: Callable[..., None],
        on_change: Callable[[], None],
    ) -> None:
        self.session = RuntimeToolsSession(settings)
        self._settings = settings
        self._http_get = http_get
        self._run_in_background = run_in_background
        self._post = post
        self._on_change = on_change
        self._token: CancelToken | None = None

    def auto_start(self) -> None:
        """At start-up and after Settings: download what's missing, unless paused."""
        self._run(self.session.auto_download_ids(), verify=False)

    def start(self, *, verify: bool = False) -> None:
        """Banner "Download"/"Retry", or Settings "Download missing"/"Verify"."""
        self._run(self.session.start(verify=verify), verify=verify)

    def cancel(self) -> None:
        if self._token is not None:
            self._token.cancel()

    def _run(self, tool_ids: list[str], *, verify: bool) -> None:
        if tool_ids:
            token = CancelToken()
            self._token = token
            self._run_in_background(self._install, tool_ids, verify, token)
        self._on_change()

    def _install(self, tool_ids: list[str], verify: bool, token: CancelToken) -> None:
        """Runs on a daemon thread."""
        try:
            install_tools(
                tool_ids,
                self._settings.tool_store,
                verify=verify,
                http_get=self._http_get,
                on_progress=lambda progress: self._post(self._progress, token, progress),
                cancel=token,
            )
        except OperationCancelledError:
            self._post(self._finish, token, self.session.on_cancelled)
        except ToolInstallError as e:
            self._post(self._finish, token, self.session.on_failed, str(e))
        except Exception as e:
            self._post(self._finish, token, self.session.on_failed, f"Unexpected error: {e}")
        else:
            self._post(self._finish, token, self.session.on_finished)

    def _progress(self, token: CancelToken, progress: InstallProgress) -> None:
        if token is self._token:
            self.session.on_progress(progress)
            self._on_change()

    def _finish(self, token: CancelToken, outcome: Callable[..., None], *args) -> None:
        if token is not self._token:
            return  # A newer download superseded this one.
        self._token = None
        outcome(*args)
        self._on_change()
