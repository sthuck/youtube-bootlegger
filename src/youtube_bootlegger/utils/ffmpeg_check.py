"""FFmpeg availability checking utilities."""

import shutil


def is_ffmpeg_available(command: str = "ffmpeg") -> bool:
    """Check if an ffmpeg executable is available.

    Args:
        command: Executable name or path to check. Defaults to "ffmpeg"
            (resolved via PATH). Accepts an absolute/relative path too.

    Returns:
        True if ffmpeg is found and executable.
    """
    return shutil.which(command) is not None
