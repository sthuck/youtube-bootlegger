"""Locate release sidecar executables without relying on the working directory.

Nuitka onefile keeps sys.argv[0] pointing at the original executable, whereas
__file__ points into its temporary extraction directory. Tools intentionally
live outside that temporary directory and are never compiled as Python modules.
"""

import os
import sys
from pathlib import Path


def bundled_tools_dir() -> Path:
    """Return tools beside the executable, or inside a macOS app's Resources."""
    executable_dir = Path(sys.argv[0]).resolve().parent
    if executable_dir.name == "MacOS" and executable_dir.parent.name == "Contents":
        return executable_dir.parent / "Resources" / "tools"
    return executable_dir / "tools"


def bundled_tool(name: str) -> Path | None:
    suffix = ".exe" if sys.platform == "win32" else ""
    candidate = bundled_tools_dir() / f"{name}{suffix}"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def resolve_tool(name: str, override: str = "") -> str:
    """Prefer a user override, then a bundled executable, then PATH lookup."""
    if override:
        return override
    return str(bundled_tool(name) or name)
