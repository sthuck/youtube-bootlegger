"""Fakes for runtime-tool downloads, shared by core and UI tests.

Only the outside world is faked: the pinned manifest (tiny archives instead of
real releases), HTTP, and which executables are on PATH. The real ToolStore
and installer run against a temporary tools folder.
"""

import hashlib
import io
import shutil
import threading
import zipfile
from contextlib import contextmanager

from src.youtube_bootlegger.core import tools
from src.youtube_bootlegger.core.tool_installer import install_tools
from src.youtube_bootlegger.core.tool_manifest import TOOL_LABELS, ToolAsset, ToolSpec
from src.youtube_bootlegger.core.tools import ToolStore, exe_name

_EXECUTABLES = {"yt-dlp": ("yt-dlp",), "ffmpeg": ("ffmpeg", "ffprobe"), "deno": ("deno",)}
TOOL_NAMES = {"yt-dlp", "ffmpeg", "ffprobe", "deno"}


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(zipfile.ZipInfo(f"pkg/bin/{name}", (2026, 1, 1, 0, 0, 0)), data)
    return buffer.getvalue()


def make_spec(tool_id: str, version: str = "1.0") -> tuple[ToolSpec, dict[str, bytes]]:
    """A spec with one small zip asset, plus the payload to serve for it."""
    files = {exe_name(n): f"fake {n} {version}".encode() for n in _EXECUTABLES[tool_id]}
    payload = _zip_bytes(files)
    url = f"https://example.invalid/{tool_id}-{version}.zip"
    asset = ToolAsset(url, hashlib.sha256(payload).hexdigest(), len(payload), "zip", tuple(files))
    return ToolSpec(tool_id, TOOL_LABELS[tool_id], version, _EXECUTABLES[tool_id], (asset,)), {url: payload}


class FakeToolServer:
    """Serves fake tool archives.

    Attributes:
        specs: The fake manifest, keyed by tool id.
        requests: URLs requested, in order.
        error: When set, every request raises it.
    """

    def __init__(self, version: str = "1.0"):
        self.specs: dict[str, ToolSpec] = {}
        self.payloads: dict[str, bytes] = {}
        self.requests: list[str] = []
        self.error: Exception | None = None
        self._open = threading.Event()
        self._open.set()
        self.set_version(version)

    def set_version(self, version: str) -> None:
        for tool_id in _EXECUTABLES:
            spec, payloads = make_spec(tool_id, version)
            self.specs[tool_id] = spec
            self.payloads.update(payloads)

    def hold(self) -> None:
        """Make downloads block until release(), to observe or cancel them mid-way."""
        self._open.clear()

    def release(self) -> None:
        self._open.set()

    @contextmanager
    def http_get(self, url: str):
        self.requests.append(url)
        if self.error:
            raise self.error
        yield _GatedReader(self.payloads[url], self._open)


class _GatedReader:
    def __init__(self, data: bytes, gate: threading.Event):
        self._data = io.BytesIO(data)
        self._gate = gate

    def read(self, size: int = -1) -> bytes:
        self._gate.wait(timeout=10)
        return self._data.read(size)


def use_fake_tools(monkeypatch, version: str = "1.0") -> FakeToolServer:
    """Replace the pinned manifest with tiny fake tools; return their server."""
    server = FakeToolServer(version)
    monkeypatch.setattr(tools, "tool_specs", lambda platform_key=None: dict(server.specs))
    return server


def install_fake_tools(tools_dir, server: FakeToolServer, tool_ids=("yt-dlp", "ffmpeg", "deno")) -> None:
    """Install fake tools for real (through the installer) before a test starts."""
    install_tools(list(tool_ids), ToolStore(tools_dir, server.specs), http_get=server.http_get)
    server.requests.clear()


def fake_path(monkeypatch, names=()) -> None:
    """Pretend exactly these tool executables are on PATH (others pass through)."""
    real_which = shutil.which

    def which(cmd, *args, **kwargs):
        if cmd in TOOL_NAMES:
            return f"/usr/bin/{cmd}" if cmd in names else None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(tools, "_deno_is_supported", lambda *args: True)
