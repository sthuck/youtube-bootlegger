"""FFmpeg availability checking utilities."""

import shutil
import subprocess


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available in PATH.

    Returns:
        True if ffmpeg is found and executable.
    """
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_version() -> str | None:
    """Get ffmpeg version string.

    Returns:
        Version string, or None if ffmpeg is not found.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            first_line = result.stdout.split("\n")[0]
            return first_line
        return None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None
