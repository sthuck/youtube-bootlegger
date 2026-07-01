"""yt-dlp executable availability checking utilities."""

import shutil


def is_ytdlp_available(command: str = "yt-dlp") -> bool:
    """Check if a yt-dlp executable is available.

    Args:
        command: Executable name or path to check. Defaults to "yt-dlp"
            (resolved via PATH). Accepts an absolute/relative path too.

    Returns:
        True if yt-dlp is found and executable.
    """
    return shutil.which(command) is not None
