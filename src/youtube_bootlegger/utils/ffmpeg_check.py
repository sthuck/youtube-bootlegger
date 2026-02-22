"""FFmpeg availability checking utilities."""

import shutil


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available in PATH.

    Returns:
        True if ffmpeg is found and executable.
    """
    return shutil.which("ffmpeg") is not None
