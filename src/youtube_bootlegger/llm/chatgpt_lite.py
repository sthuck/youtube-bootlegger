"""Browser-based ChatGPT assist (no API key required)."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

from .prompt import build_lite_prompt

CHATGPT_LITE_BASE_URL = "https://chatgpt.com/"
# Stay below common browser/proxy URL length limits.
_MAX_URL_LENGTH = 2000

OpenUrl = Callable[[str], bool]
CopyText = Callable[[str], None]


def _chatgpt_url_for_prompt(prompt: str) -> str:
    return f"{CHATGPT_LITE_BASE_URL}?q={quote(prompt, safe='')}"


def _qt_open_url(url: str) -> bool:
    """Open a URL with the desktop's default handler via Qt."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    return QDesktopServices.openUrl(QUrl(url))


def _qt_copy_text(text: str) -> None:
    """Copy text to the Qt application clipboard, if one is available."""
    from PySide6.QtWidgets import QApplication

    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


def build_chatgpt_lite_url(video_title: str, raw_tracklist: str) -> str:
    """Return a ChatGPT URL with the lite assist prompt pre-filled."""
    return _chatgpt_url_for_prompt(build_lite_prompt(video_title, raw_tracklist))


def launch_chatgpt_lite_assist(
    video_title: str,
    raw_tracklist: str,
    *,
    open_url: OpenUrl | None = None,
    copy_text: CopyText | None = None,
) -> tuple[bool, str]:
    """Open ChatGPT in the user's browser with a pre-filled assist prompt.

    Args:
        video_title: Title of the video being split.
        raw_tracklist: The user's raw track list text.
        open_url: Opens a URL, returning False on failure. Defaults to Qt.
        copy_text: Copies text to the clipboard. Defaults to Qt.

    Returns:
        Tuple of (success, user-facing message). On success the message explains
        what happened; on failure it describes the error.
    """
    if not raw_tracklist.strip():
        return False, "Track list is empty."
    if not video_title.strip():
        return False, "Video title is required."

    open_url = open_url or _qt_open_url
    copy_text = copy_text or _qt_copy_text

    prompt = build_lite_prompt(video_title, raw_tracklist)
    url = _chatgpt_url_for_prompt(prompt)

    # Measure the human-readable URL (as browsers display it), not the
    # percent-encoded form, matching the limit the Qt UIs always used.
    if len(CHATGPT_LITE_BASE_URL) + len("?q=") + len(prompt) > _MAX_URL_LENGTH:
        copy_text(prompt)
        if not open_url(CHATGPT_LITE_BASE_URL):
            return False, "Could not open your web browser."
        return (
            True,
            "The track list is too long to embed in a link. The prompt was copied "
            "to your clipboard — paste it into ChatGPT, then copy the suggested "
            "template back into YouTube Bootlegger.",
        )

    if not open_url(url):
        return False, "Could not open your web browser."

    return (
        True,
        "Opened ChatGPT in your browser with a pre-filled prompt. Copy the "
        "suggested template back into YouTube Bootlegger when ChatGPT replies.",
    )
