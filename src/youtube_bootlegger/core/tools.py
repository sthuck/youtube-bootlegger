"""Locate release executables without relying on the working directory.

Nuitka onefile keeps sys.argv[0] pointing at the original executable, whereas
__file__ of __main__ points into its temporary extraction directory. Windows
embeds tools there; Linux uses sidecars and macOS keeps tools inside the .app.
"""

import os
import sys
from pathlib import Path


def bundled_tools_dir() -> Path:
    """Return extracted Windows tools, Linux sidecars, or macOS Resources."""
    if sys.platform == "win32" and "__compiled__" in globals():
        main_file = getattr(sys.modules.get("__main__"), "__file__", None)
        if main_file:
            return Path(main_file).resolve().parent / "tools"
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
