"""Side effects that leave the terminal: opening a browser, fetching images."""

import io
import os
import shutil
import subprocess
import sys
import urllib.request

from PIL import Image as PILImage

THUMBNAIL_TIMEOUT_SECONDS = 10


def has_graphical_session() -> bool:
    """Return True when a GUI browser can plausibly be launched."""
    if sys.platform in ("darwin", "win32"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _opener_command() -> list[str] | None:
    if sys.platform == "darwin":
        return ["open"]
    opener = shutil.which("xdg-open")
    return [opener] if opener else None


def open_url_in_browser(url: str) -> bool:
    """Open a URL in a GUI browser without touching the terminal.

    Python's ``webbrowser`` may fall back to a console browser (lynx, w3m)
    or let a launcher write to the terminal, either of which corrupts a
    running TUI. This only launches a detached GUI opener with its output
    discarded, and reports failure otherwise so callers can fall back to
    the clipboard.
    """
    if not has_graphical_session():
        return False
    if sys.platform == "win32":
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
    command = _opener_command()
    if command is None:
        return False
    try:
        subprocess.Popen(
            [*command, url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


def fetch_thumbnail(url: str) -> PILImage.Image:
    """Download and decode a thumbnail image (blocking).

    Raises:
        OSError: On network or decode failure.
    """
    with urllib.request.urlopen(url, timeout=THUMBNAIL_TIMEOUT_SECONDS) as response:
        data = response.read()
    image = PILImage.open(io.BytesIO(data))
    image.load()
    return image
