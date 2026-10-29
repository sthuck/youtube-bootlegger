"""Pinned runtime tools the app downloads on first run.

Each tool lists the exact upstream release files for every supported platform,
with their SHA-256. Bumping a version means updating url, sha256 and size here;
the app then downloads only the tools whose pins changed.
"""

import hashlib
import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolAsset:
    """One upstream download and the executables taken from it."""

    url: str
    sha256: str
    size: int
    archive: str  # "raw" (the file is the executable) or "zip"
    files: tuple[str, ...]


@dataclass(frozen=True)
class ToolSpec:
    """A tool pinned for one platform.

    Attributes:
        tool_id: "yt-dlp", "ffmpeg" or "deno".
        label: Name shown to users.
        version: Upstream version, for display.
        executables: Names (without .exe) the tool provides.
        assets: Downloads that together provide the executables.
    """

    tool_id: str
    label: str
    version: str
    executables: tuple[str, ...]
    assets: tuple[ToolAsset, ...]

    @property
    def install_key(self) -> str:
        """Folder name for this pin; changes whenever any pinned file changes."""
        digest = hashlib.sha256("".join(a.sha256 for a in self.assets).encode()).hexdigest()
        return f"{self.version}-{digest[:8]}"

    @property
    def download_size(self) -> int:
        return sum(asset.size for asset in self.assets)


_YTDLP = "https://github.com/yt-dlp/yt-dlp/releases/download/2026.10.26"
_DENO = "https://github.com/denoland/deno/releases/download/v2.9.8"
_RIEDL = "https://ffmpeg.martin-riedl.de/download"
_GYAN = "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2"

TOOL_LABELS = {"yt-dlp": "yt-dlp", "ffmpeg": "FFmpeg", "deno": "Deno"}
_EXECUTABLES = {"yt-dlp": ("yt-dlp",), "ffmpeg": ("ffmpeg", "ffprobe"), "deno": ("deno",)}
_VERSIONS = {"yt-dlp": "2026.10.26", "ffmpeg": "9.0.2", "deno": "2.9.8"}

_ASSETS: dict[str, dict[str, tuple[ToolAsset, ...]]] = {
    "linux-x64": {
        "yt-dlp": (ToolAsset(
            f"{_YTDLP}/yt-dlp_linux",
            "767ba9dce7052aa196f8b12652f433d76de128ba168966fa84b6394d5e6c6795",
            41166968, "raw", ("yt-dlp",),
        ),),
        "ffmpeg": (
            ToolAsset(
                f"{_RIEDL}/linux/amd64/1789931100_9.0.2/ffmpeg.zip",
                "fa8ecf4abbd290d98f7d188b8649cc6b391ae209a98452be955a15aab1909d7f",
                33326445, "zip", ("ffmpeg",),
            ),
            ToolAsset(
                f"{_RIEDL}/linux/amd64/1789931100_9.0.2/ffprobe.zip",
                "3f428c49070be3d24ec338602b76d412e401ffcb8a5641ef0e729181a232fc32",
                33223234, "zip", ("ffprobe",),
            ),
        ),
        "deno": (ToolAsset(
            f"{_DENO}/deno-x86_64-unknown-linux-gnu.zip",
            "e890975bc2549807bbcc0b584ffafda72cc7c93349dd99c80483dd784f6c4609",
            41963064, "zip", ("deno",),
        ),),
    },
    "windows-x64": {
        "yt-dlp": (ToolAsset(
            f"{_YTDLP}/yt-dlp.exe",
            "f5389d3698ecde4ef06f4e6b1ce0294fe9ac1396228c8990b8d3416d6d177a7d",
            23575744, "raw", ("yt-dlp.exe",),
        ),),
        "ffmpeg": (ToolAsset(
            f"{_GYAN}/ffmpeg-9.0.2-essentials_build.zip",
            "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
            114768076, "zip", ("ffmpeg.exe", "ffprobe.exe"),
        ),),
        "deno": (ToolAsset(
            f"{_DENO}/deno-x86_64-pc-windows-msvc.zip",
            "cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf",
            42917472, "zip", ("deno.exe",),
        ),),
    },
    "macos-arm64": {
        "yt-dlp": (ToolAsset(
            f"{_YTDLP}/yt-dlp_macos",
            "0f922c15ccc0b83eefa1c8bc9104e434318c4bf16e408e1ee93b7745a6efe0aa",
            37466304, "raw", ("yt-dlp",),
        ),),
        "ffmpeg": (
            ToolAsset(
                f"{_RIEDL}/macos/arm64/1789931890_9.0.2/ffmpeg.zip",
                "c8ed4c4e6978a03c485edbfe4e0a5dc2380f8a30bba5150531b31b094492d924",
                28395699, "zip", ("ffmpeg",),
            ),
            ToolAsset(
                f"{_RIEDL}/macos/arm64/1789931890_9.0.2/ffprobe.zip",
                "fcbe839537485eaee7a7a8bc5cbc0f90d53617e80943e8a5b2e31cb851197ea6",
                28317701, "zip", ("ffprobe",),
            ),
        ),
        "deno": (ToolAsset(
            f"{_DENO}/deno-aarch64-apple-darwin.zip",
            "9f0bf660393da2eaff044cdc7444cb08c73f235849b61d224d825a194ce7c98e",
            38770795, "zip", ("deno",),
        ),),
    },
}

TOOL_IDS: tuple[str, ...] = ("yt-dlp", "ffmpeg", "deno")


def current_platform() -> str | None:
    """Return this machine's manifest key, or None if no downloads exist for it."""
    machine = platform.machine().lower()
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "linux-x64"
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    if sys.platform == "darwin" and machine == "arm64":
        return "macos-arm64"
    return None


def tool_specs(platform_key: str | None = None) -> dict[str, ToolSpec]:
    """Return the pinned tools for a platform (default: this one), keyed by tool id."""
    key = platform_key or current_platform()
    assets = _ASSETS.get(key or "", {})
    return {
        tool_id: ToolSpec(
            tool_id, TOOL_LABELS[tool_id], _VERSIONS[tool_id], _EXECUTABLES[tool_id], assets[tool_id]
        )
        for tool_id in TOOL_IDS
        if tool_id in assets
    }


def platform_keys() -> tuple[str, ...]:
    return tuple(_ASSETS)
