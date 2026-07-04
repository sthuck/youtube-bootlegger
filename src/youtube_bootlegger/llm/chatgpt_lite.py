"""Browser-based ChatGPT assist (no API key required)."""

from __future__ import annotations

from PySide6.QtCore import QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from .prompt import build_lite_prompt

CHATGPT_LITE_BASE_URL = "https://chatgpt.com/"
# Stay below common browser/proxy URL length limits.
_MAX_URL_LENGTH = 2000


def _chatgpt_url_for_prompt(prompt: str) -> QUrl:
    url = QUrl(CHATGPT_LITE_BASE_URL)
    query = QUrlQuery()
    query.addQueryItem("q", prompt)
    url.setQuery(query)
    return url


def build_chatgpt_lite_url(video_title: str, raw_tracklist: str) -> str:
    """Return a ChatGPT URL with the lite assist prompt pre-filled."""
    prompt = build_lite_prompt(video_title, raw_tracklist)
    return _chatgpt_url_for_prompt(prompt).toString()


def launch_chatgpt_lite_assist(video_title: str, raw_tracklist: str) -> tuple[bool, str]:
    """Open ChatGPT in the user's browser with a pre-filled assist prompt.

    Returns:
        Tuple of (success, user-facing message). On success the message explains
        what happened; on failure it describes the error.
    """
    if not raw_tracklist.strip():
        return False, "Track list is empty."
    if not video_title.strip():
        return False, "Video title is required."

    prompt = build_lite_prompt(video_title, raw_tracklist)
    url = _chatgpt_url_for_prompt(prompt)
    url_string = url.toString()

    if len(url_string) > _MAX_URL_LENGTH:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(prompt)
        opened = QDesktopServices.openUrl(QUrl(CHATGPT_LITE_BASE_URL))
        if not opened:
            return False, "Could not open your web browser."
        return (
            True,
            "The track list is too long to embed in a link. The prompt was copied "
            "to your clipboard — paste it into ChatGPT, then copy the suggested "
            "template back into YouTube Bootlegger.",
        )

    if not QDesktopServices.openUrl(url):
        return False, "Could not open your web browser."

    return (
        True,
        "Opened ChatGPT in your browser with a pre-filled prompt. Copy the "
        "suggested template back into YouTube Bootlegger when ChatGPT replies.",
    )
