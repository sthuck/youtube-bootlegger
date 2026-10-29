"""Runtime tool status and download state shared by every front-end.

Front-ends hold one RuntimeToolsSession per window. At start-up and after
Settings are saved they call auto_download_ids(); a non-empty result means
"start a download of these now" (core.tool_installer.install_tools on a
background thread), reporting back through on_progress / on_finished /
on_failed / on_cancelled. They render banner() and gate Start on
start_blocked_reason().
"""

import shutil
from dataclasses import dataclass
from enum import StrEnum

from ..core.settings import AppSettings
from ..core.tool_installer import InstallProgress
from ..core.tools import ToolSource, ToolStatus

YTDLP_PATH_PLACEHOLDER = "Leave empty to use the downloaded yt-dlp"
FFMPEG_PATH_PLACEHOLDER = "Leave empty to use FFmpeg from PATH, or the downloaded one"
TOOLS_SECTION_TITLE = "Runtime tools"
EXTRA_ARGS_PLACEHOLDER = "e.g. --proxy socks5://127.0.0.1:9050 --limit-rate 2M"
EXTRA_ARGS_NOTE = (
    "Added to every yt-dlp run. Options that change where files go, their format "
    "or what yt-dlp prints can't be used. yt-dlp config files are read only by a "
    "yt-dlp whose path you set."
)


class ToolsPhase(StrEnum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BannerAction(StrEnum):
    NONE = ""
    CANCEL = "cancel"
    DOWNLOAD = "download"  # also used as "Retry" after a failure


@dataclass(frozen=True)
class ToolsBanner:
    """What the tools banner shows.

    Attributes:
        visible: Whether to show the banner at all.
        text: The message.
        action: What the banner's button does; NONE hides the button.
        action_label: Button text ("Cancel", "Retry", "Download").
        progress: 0..1 while a download runs, else None.
        is_error: Style the banner as an error.
    """

    visible: bool
    text: str = ""
    action: BannerAction = BannerAction.NONE
    action_label: str = ""
    progress: float | None = None
    is_error: bool = False


HIDDEN_BANNER = ToolsBanner(visible=False)


@dataclass(frozen=True)
class ToolsView:
    """Everything a front-end renders, computed from one status lookup."""

    statuses: list[ToolStatus]
    banner: ToolsBanner
    start_blocked_reason: str | None


def format_size(size: int) -> str:
    return f"{size / 1_000_000:.0f} MB" if size >= 1_000_000 else f"{size / 1000:.0f} kB"


def _join(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def _ffprobe_hint(detail: str) -> str:
    return f"FFmpeg can't be used: {detail}. Install ffprobe (it comes with FFmpeg)."


def status_text(status: ToolStatus) -> str:
    """One line describing where a tool comes from, for the Settings list."""
    if status.source == ToolSource.CUSTOM:
        return f"Custom path: {status.path}"
    if status.source == ToolSource.DOWNLOADED:
        return f"Downloaded: {status.path}"
    if status.source == ToolSource.SYSTEM:
        if status.needs_download:
            return f"Using {status.path} until the download finishes"
        return f"From PATH: {status.path}"
    if status.downloadable:
        return "Not downloaded yet"
    if status.detail:
        return f"Not usable: {status.detail}. Install ffprobe or set a path."
    return "Not found. No download exists for this platform; install it or set a path."


class RuntimeToolsSession:
    """Per-window download state; front-ends only wire events to it."""

    def __init__(self, settings: AppSettings):
        self._settings = settings
        self._phase = ToolsPhase.IDLE
        self._progress: InstallProgress | None = None
        self._error = ""
        # Looked up once per download: progress ticks re-render often, and
        # nothing a lookup finds changes until the download ends.
        self._download_statuses: list[ToolStatus] | None = None

    @property
    def phase(self) -> ToolsPhase:
        return self._phase

    @property
    def downloading(self) -> bool:
        return self._phase == ToolsPhase.DOWNLOADING

    def statuses(self) -> list[ToolStatus]:
        if self.downloading and self._download_statuses is not None:
            return self._download_statuses
        return self._settings.tool_statuses()

    def pending_ids(self) -> list[str]:
        return [s.tool_id for s in self.statuses() if s.needs_download]

    def auto_download_ids(self) -> list[str]:
        """Tools to download now without asking: at start-up or after Settings.

        Empty while a download runs, or after the user cancelled or a
        download failed; the banner's button restarts those.
        """
        if self.downloading:
            # Called after Settings change: look the tools up again.
            self._download_statuses = self._settings.tool_statuses()
            return []
        if self._phase in (ToolsPhase.FAILED, ToolsPhase.CANCELLED) and not self.pending_ids():
            self._phase = ToolsPhase.IDLE  # The user provided the tools some other way.
        if self._phase != ToolsPhase.IDLE:
            return []
        return self.start()

    def start(self, *, verify: bool = False) -> list[str]:
        """Begin a download (banner button, Settings "Download"/"Verify").

        Returns the tool ids to pass to install_tools, or [] if nothing is
        needed (the phase then stays as it was). With verify, every
        downloaded tool is included so the installer can re-check it.
        """
        if self.downloading:
            return []
        ids = self.pending_ids()
        if verify:
            ids += [
                s.tool_id for s in self.statuses()
                if s.source == ToolSource.DOWNLOADED and s.tool_id not in ids
            ]
        if not ids:
            if self._phase != ToolsPhase.IDLE and not self.pending_ids():
                self._phase = ToolsPhase.IDLE
            return []
        self._phase = ToolsPhase.DOWNLOADING
        self._progress = None
        self._error = ""
        self._download_statuses = self._settings.tool_statuses()
        return ids

    def on_progress(self, progress: InstallProgress) -> None:
        self._progress = progress

    def on_finished(self) -> None:
        self._download_statuses = None
        self._progress = None
        if self.pending_ids():
            self._phase = ToolsPhase.FAILED
            self._error = "Some tools are still missing after the download."
        else:
            self._phase = ToolsPhase.IDLE

    def on_failed(self, message: str) -> None:
        self._download_statuses = None
        self._phase = ToolsPhase.FAILED
        self._progress = None
        self._error = message

    def on_cancelled(self) -> None:
        self._download_statuses = None
        self._phase = ToolsPhase.CANCELLED
        self._progress = None

    def view(self) -> ToolsView:
        """Statuses, banner and Start gating together; looks tools up only once."""
        statuses = self.statuses()
        return ToolsView(statuses, self.banner(statuses), self.start_blocked_reason(statuses))

    def banner(self, statuses: list[ToolStatus] | None = None) -> ToolsBanner:
        if self._phase == ToolsPhase.DOWNLOADING:
            return ToolsBanner(
                True, self._progress_text(), BannerAction.CANCEL, "Cancel",
                progress=self._progress_fraction(),
            )
        statuses = self.statuses() if statuses is None else statuses
        pending = [s for s in statuses if s.needs_download]
        # A failure only matters while something is still missing.
        if self._phase == ToolsPhase.FAILED and pending:
            return ToolsBanner(
                True, f"Tool download failed: {self._error}", BannerAction.DOWNLOAD, "Retry",
                is_error=True,
            )
        if pending:
            size = self._download_size([s.tool_id for s in pending])
            names = _join([s.label for s in pending])
            prefix = "Download cancelled. " if self._phase == ToolsPhase.CANCELLED else ""
            return ToolsBanner(
                True, f"{prefix}{names} need a one-time download ({format_size(size)}).",
                BannerAction.DOWNLOAD, "Download",
            )
        unavailable = [
            s for s in self._needed(statuses)
            if s.source == ToolSource.MISSING and not s.downloadable
        ]
        if unavailable:
            details = [s.detail for s in unavailable if s.detail]
            if details:
                return ToolsBanner(True, _ffprobe_hint(details[0]), is_error=True)
            names = _join([s.label for s in unavailable])
            return ToolsBanner(
                True,
                f"{names} can't be downloaded on this platform. "
                "Install it, or set its path in Settings.",
                is_error=True,
            )
        return HIDDEN_BANNER

    def start_blocked_reason(self, statuses: list[ToolStatus] | None = None) -> str | None:
        """Why Start can't run now, or None. FFmpeg is always needed; yt-dlp in external mode."""
        needed = self._needed(self.statuses() if statuses is None else statuses)
        for status in needed:
            if status.source == ToolSource.CUSTOM and not shutil.which(status.path):
                return f"{status.label} not found at '{status.path}'. Fix the path in Settings."
        missing = [s for s in needed if s.source == ToolSource.MISSING]
        if not missing:
            return None
        names = _join([s.label for s in missing])
        if self.downloading:
            return f"Wait for {names} to finish downloading."
        if all(s.downloadable for s in missing):
            return f"{names} not downloaded yet. Use Download in the banner."
        details = [s.detail for s in missing if s.detail and not s.downloadable]
        if details:
            return _ffprobe_hint(details[0])
        return f"{names} not found. Install it, or set its path in Settings."

    def _needed(self, statuses: list[ToolStatus]) -> list[ToolStatus]:
        """Tools Start can't run without: FFmpeg, and yt-dlp in external mode."""
        needed = {"ffmpeg", "yt-dlp"} if self._settings.use_external_ytdlp else {"ffmpeg"}
        return [s for s in statuses if s.tool_id in needed]

    def _download_size(self, tool_ids: list[str]) -> int:
        specs = self._settings.tool_store.specs
        return sum(specs[t].download_size for t in tool_ids if t in specs)

    def _progress_fraction(self) -> float | None:
        p = self._progress
        if p is None or p.total_bytes <= 0:
            return None
        return min(p.done_bytes / p.total_bytes, 1.0)

    def _progress_text(self) -> str:
        p = self._progress
        if p is None:
            return "Preparing tool download…"
        percent = int(100 * (self._progress_fraction() or 0))
        return (
            f"Downloading {p.label}… {format_size(p.done_bytes)} of "
            f"{format_size(p.total_bytes)} ({percent}%)"
        )
