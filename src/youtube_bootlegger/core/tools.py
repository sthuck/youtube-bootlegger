"""Find runtime tools: a user path, a downloaded copy, or the system PATH.

Downloads live in a per-user data folder (see default_tools_dir), one folder
per tool and pinned version: <root>/<tool>/<install key>/. A folder counts as
installed only once its installed.json marker exists, which the installer
writes last, so a cancelled or crashed download is never picked up.
"""

import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .tool_manifest import TOOL_LABELS, ToolSpec, tool_specs

MARKER_NAME = "installed.json"
DENO_CHECK_NAME = ".deno-on-path.json"
MIN_DENO_MAJOR = 2


def exe_name(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def default_tools_dir() -> Path:
    """Per-user folder for downloaded tools.

    Windows: %LOCALAPPDATA%\\YouTubeBootlegger\\tools (not roaming: these are
    large, machine-specific binaries). Linux and macOS: $XDG_DATA_HOME, or
    ~/.local/share, then youtube-bootlegger/tools.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "YouTubeBootlegger" / "tools"
    xdg = os.environ.get("XDG_DATA_HOME", "")
    # The XDG spec says relative paths are invalid and must be ignored.
    base = Path(xdg) if os.path.isabs(xdg) else Path.home() / ".local" / "share"
    return base / "youtube-bootlegger" / "tools"


def file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class ToolStore:
    """Downloaded tools under one root folder. A None root holds nothing."""

    def __init__(self, root: Path | None, specs: dict[str, ToolSpec] | None = None):
        self.root = root
        self.specs = tool_specs() if specs is None else specs

    def install_dir(self, spec: ToolSpec) -> Path | None:
        if self.root is None:
            return None
        return self.root / spec.tool_id / spec.install_key

    def is_installed(self, tool_id: str) -> bool:
        spec = self.specs.get(tool_id)
        directory = self.install_dir(spec) if spec else None
        if directory is None:
            return False
        return (directory / MARKER_NAME).is_file() and all(
            (directory / exe_name(name)).is_file() for name in spec.executables
        )

    def executable(self, name: str) -> Path | None:
        """Path of a downloaded executable such as "ffprobe", if installed."""
        for spec in self.specs.values():
            if name in spec.executables and self.is_installed(spec.tool_id):
                return self.install_dir(spec) / exe_name(name)
        return None

    def verify(self, tool_id: str) -> bool:
        """Re-hash an installed tool and remove it if any file changed.

        Returns False when the tool is not installed (any more).
        """
        if not self.is_installed(tool_id):
            return False
        directory = self.install_dir(self.specs[tool_id])
        try:
            recorded = json.loads((directory / MARKER_NAME).read_text(encoding="utf-8"))["files"]
            intact = all(file_sha256(directory / name) == digest for name, digest in recorded.items())
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            intact = False
        if not intact:
            shutil.rmtree(directory, ignore_errors=True)
        return intact

    def remove_other_versions(self, tool_id: str) -> None:
        """Delete folders of older pins. Files still in use are left for next time."""
        spec = self.specs.get(tool_id)
        current = self.install_dir(spec) if spec else None
        if current is None or not current.parent.is_dir():
            return
        for entry in current.parent.iterdir():
            if entry != current and entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)


class ToolSource(StrEnum):
    CUSTOM = "custom"  # a path set in Settings
    DOWNLOADED = "downloaded"
    SYSTEM = "system"  # found on PATH
    MISSING = "missing"


@dataclass(frozen=True)
class ToolStatus:
    """Where a tool comes from right now.

    Attributes:
        tool_id: "yt-dlp", "ffmpeg" or "deno".
        label: Name shown to users.
        source: Which lookup step found it.
        path: The executable in use, or None when missing.
        needs_download: True if the downloader should fetch it.
        downloadable: True if this platform has a pinned download.
    """

    tool_id: str
    label: str
    source: ToolSource
    path: str | None
    needs_download: bool
    downloadable: bool


def tool_status(
    tool_id: str, store: ToolStore, *, custom_path: str = "", use_path: bool = True
) -> ToolStatus:
    """Resolve one tool: custom path, then the download, then PATH.

    Args:
        custom_path: The user's override from Settings, if any.
        use_path: Whether a copy on PATH saves the download. yt-dlp passes
            False: the app always fetches its own pinned copy, using the
            PATH one only until that arrives.
    """
    label = TOOL_LABELS[tool_id]
    downloadable = tool_id in store.specs and store.root is not None
    if custom_path:
        return ToolStatus(tool_id, label, ToolSource.CUSTOM, custom_path, False, downloadable)
    downloaded = store.executable(tool_id)
    if downloaded:
        return ToolStatus(tool_id, label, ToolSource.DOWNLOADED, str(downloaded), False, downloadable)
    system = _on_path(tool_id, store.root)
    if system:
        return ToolStatus(
            tool_id, label, ToolSource.SYSTEM, system, downloadable and not use_path, downloadable
        )
    return ToolStatus(tool_id, label, ToolSource.MISSING, None, downloadable, downloadable)


def _on_path(tool_id: str, cache_dir: Path | None) -> str | None:
    if tool_id == "ffmpeg":
        # yt-dlp looks for ffprobe beside FFmpeg; a lone ffmpeg isn't enough.
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        return ffmpeg if ffmpeg and ffprobe else None
    found = shutil.which(tool_id)
    if found and tool_id == "deno" and not _deno_is_supported(found, cache_dir):
        return None
    return found


def _deno_is_supported(path: str, cache_dir: Path | None) -> bool:
    """yt-dlp needs Deno 2 or later; an older Deno on PATH doesn't count.

    Running `deno --version` happens on the UI thread at start-up and can be
    slow behind version-manager shims, so the answer is kept in the tools
    folder and reused until that Deno file changes.
    """
    try:
        stat = os.stat(path)
    except OSError:
        return False
    key = {"path": path, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
    cache_file = cache_dir / DENO_CHECK_NAME if cache_dir else None
    try:
        cached = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file else {}
    except (OSError, ValueError):
        cached = {}
    if isinstance(cached, dict) and all(cached.get(k) == v for k, v in key.items()):
        return bool(cached.get("supported"))
    supported = _run_deno_version(path, stat.st_mtime_ns, stat.st_size)
    if cache_file:
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({**key, "supported": supported}), encoding="utf-8")
        except OSError:
            pass  # Only a cache: checked again next time.
    return supported


@functools.cache
def _run_deno_version(path: str, mtime_ns: int, size: int) -> bool:
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=10,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    match = re.match(r"deno (\d+)\.", result.stdout or "")
    return bool(match) and int(match.group(1)) >= MIN_DENO_MAJOR
