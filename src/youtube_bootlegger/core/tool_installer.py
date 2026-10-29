"""Download, verify and unpack the pinned runtime tools into a ToolStore.

Each tool is assembled in a hidden staging folder next to its final place,
checked against the pinned SHA-256s, and renamed into place in one step with
its installed.json marker already inside. A lock file keeps two running copies
of the app from installing at the same time.
"""

import json
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PySide6.QtCore import QLockFile

from .cancellation import CancelToken
from .exceptions import ToolInstallError
from .tool_manifest import ToolAsset
from .tools import MARKER_NAME, ToolStore, exe_name, file_sha256

HttpGet = Callable[[str], AbstractContextManager[BinaryIO]]

CHUNK_SIZE = 256 * 1024
HTTP_TIMEOUT_SECONDS = 60
LOCK_POLL_MS = 250
_STAGING_PREFIX = ".staging-"


@dataclass(frozen=True)
class InstallProgress:
    """Overall progress across every tool in one install_tools call."""

    label: str  # tool being downloaded
    done_bytes: int
    total_bytes: int


def urlopen_get(url: str) -> AbstractContextManager[BinaryIO]:
    request = urllib.request.Request(url, headers={"User-Agent": "YouTubeBootlegger"})
    return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS)


def install_tools(
    tool_ids: Sequence[str],
    store: ToolStore,
    *,
    verify: bool = False,
    http_get: HttpGet = urlopen_get,
    on_progress: Callable[[InstallProgress], None] | None = None,
    cancel: CancelToken | None = None,
) -> None:
    """Install the given tools unless already installed, then drop older versions.

    Args:
        tool_ids: Tools to ensure; ids without a download for this
            platform are ignored.
        verify: Re-hash installed tools first and replace any that changed.

    Raises:
        ToolInstallError: A download, checksum or unpack failed.
        OperationCancelledError: cancel was triggered.
    """
    if store.root is None:
        raise ToolInstallError("There is no folder for downloaded tools")
    cancel = cancel or CancelToken()
    try:
        store.root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ToolInstallError(f"Could not create {store.root}: {e}") from e

    lock = QLockFile(str(store.root / ".install.lock"))
    lock.setStaleLockTime(0)  # Stale only if its owner process is gone.
    while not lock.tryLock(LOCK_POLL_MS):
        cancel.raise_if_cancelled()
    try:
        _remove_leftover_staging(store.root)
        specs = [store.specs[tool_id] for tool_id in tool_ids if tool_id in store.specs]
        if verify:
            for spec in specs:
                store.verify(spec.tool_id)
        # Another copy of the app may have finished these while we waited.
        pending = [spec for spec in specs if not store.is_installed(spec.tool_id)]
        progress = _Progress(sum(spec.download_size for spec in pending), on_progress)
        for spec in pending:
            _install_one(spec, store, http_get, progress, cancel)
            store.remove_other_versions(spec.tool_id)
    finally:
        lock.unlock()


class _Progress:
    """Reports at most once per whole percent (or new tool), not per chunk:
    each report re-renders a UI."""

    def __init__(self, total: int, callback):
        self.total = total
        self.done = 0
        self._callback = callback
        self._last: tuple[str, int] | None = None

    def advance(self, label: str, count: int) -> None:
        self.done += count
        step = (label, 100 * self.done // self.total if self.total else 0)
        if self._callback and (step != self._last or self.done >= self.total):
            self._last = step
            self._callback(InstallProgress(label, self.done, self.total))


def _remove_leftover_staging(root: Path) -> None:
    for entry in root.glob(f"{_STAGING_PREFIX}*"):
        shutil.rmtree(entry, ignore_errors=True)


def _install_one(spec, store, http_get, progress, cancel) -> None:
    final = store.install_dir(spec)
    staging = Path(tempfile.mkdtemp(prefix=f"{_STAGING_PREFIX}{spec.tool_id}-", dir=store.root))
    try:
        for asset in spec.assets:
            archive = staging / ".download"
            _download(asset, archive, spec.label, http_get, progress, cancel)
            _extract(archive, asset, staging)
            archive.unlink()
        files = {}
        for name in spec.executables:
            path = staging / exe_name(name)
            path.chmod(0o755)
            files[path.name] = file_sha256(path)
        marker = {
            "tool": spec.tool_id,
            "version": spec.version,
            "urls": [asset.url for asset in spec.assets],
            "files": files,
        }
        (staging / MARKER_NAME).write_text(json.dumps(marker, indent=2), encoding="utf-8")
        cancel.raise_if_cancelled()
        if final.exists():  # An incomplete earlier copy (files deleted by hand).
            shutil.rmtree(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(final)
    except OSError as e:
        raise ToolInstallError(f"Could not install {spec.label}: {e}") from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _download(asset: ToolAsset, target: Path, label: str, http_get, progress, cancel) -> None:
    written = 0
    try:
        with http_get(asset.url) as response, target.open("wb") as output:
            while chunk := response.read(CHUNK_SIZE):
                cancel.raise_if_cancelled()
                written += len(chunk)
                if written > asset.size:
                    raise ToolInstallError(f"{label} download is larger than expected")
                output.write(chunk)
                progress.advance(label, len(chunk))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        reason = getattr(e, "reason", e)
        raise ToolInstallError(f"Could not download {label}: {reason}") from e
    cancel.raise_if_cancelled()
    if file_sha256(target) != asset.sha256:
        raise ToolInstallError(
            f"{label} download is corrupted (checksum mismatch). Try again later."
        )


def _extract(archive: Path, asset: ToolAsset, destination: Path) -> None:
    """Copy only the named regular files, wherever they sit in the archive."""
    if asset.archive == "raw":
        shutil.copyfile(archive, destination / asset.files[0])
        return
    if asset.archive != "zip":
        raise ToolInstallError(f"Unsupported archive type: {asset.archive}")
    try:
        with zipfile.ZipFile(archive) as bundle:
            for name in asset.files:
                members = [
                    m for m in bundle.infolist()
                    if not m.is_dir() and Path(m.filename).name == name
                ]
                is_link = members and (members[0].external_attr >> 16) & 0o170000 == 0o120000
                if len(members) != 1 or is_link:
                    raise ToolInstallError(f"Expected one {name} in {Path(asset.url).name}")
                with bundle.open(members[0]) as source, (destination / name).open("wb") as target:
                    shutil.copyfileobj(source, target)
    except zipfile.BadZipFile as e:
        raise ToolInstallError(f"Could not unpack {Path(asset.url).name}: {e}") from e
