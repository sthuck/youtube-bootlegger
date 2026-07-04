"""Unit tests for browser-based ChatGPT lite assist."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from urllib.parse import unquote, urlparse

import pytest
from PySide6.QtWidgets import QApplication

from src.youtube_bootlegger.llm import (
    build_chatgpt_lite_url,
    build_lite_prompt,
    launch_chatgpt_lite_assist,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestBuildLitePrompt:
    def test_includes_template_rules_tracklist_and_video_title(self):
        prompt = build_lite_prompt(
            "Phish - 12/31/2023",
            "Tweezer - 0:00\nHarry Hood - 12:34",
        )
        assert "Phish - 12/31/2023" in prompt
        assert "Tweezer - 0:00" in prompt
        assert "%songname%" in prompt
        assert "template field" in prompt.lower()


class TestBuildChatgptLiteUrl:
    def test_builds_chatgpt_query_url(self):
        url = build_chatgpt_lite_url("Show Title", "Song - 0:00")
        parsed = urlparse(url)
        assert parsed.netloc == "chatgpt.com"
        query = unquote(parsed.query)
        assert query.startswith("q=")
        assert "Show Title" in query
        assert "Song - 0:00" in query


class TestLaunchChatgptLiteAssist:
    def test_rejects_empty_tracklist(self, qapp):
        ok, message = launch_chatgpt_lite_assist("Show", "   ")
        assert ok is False
        assert "empty" in message.lower()

    def test_rejects_empty_video_title(self, qapp):
        ok, message = launch_chatgpt_lite_assist("   ", "Song - 0:00")
        assert ok is False
        assert "title" in message.lower()

    def test_opens_browser_with_prefilled_prompt(self, qapp, monkeypatch):
        opened = []

        def fake_open_url(url):
            opened.append(url.toString())
            return True

        monkeypatch.setattr(
            "src.youtube_bootlegger.llm.chatgpt_lite.QDesktopServices.openUrl",
            fake_open_url,
        )

        ok, message = launch_chatgpt_lite_assist("Show", "Song - 0:00")
        assert ok is True
        assert len(opened) == 1
        parsed = urlparse(opened[0])
        assert parsed.netloc == "chatgpt.com"
        assert "q=" in unquote(parsed.query)
        assert "Show" in unquote(parsed.query)
        assert "copy" in message.lower()

    def test_long_prompt_copies_to_clipboard_and_opens_chatgpt(self, qapp, monkeypatch):
        opened = []

        def fake_open_url(url):
            opened.append(url.toString())
            return True

        monkeypatch.setattr(
            "src.youtube_bootlegger.llm.chatgpt_lite.QDesktopServices.openUrl",
            fake_open_url,
        )

        long_tracklist = "\n".join(f"Song {i} - 0:{i:02d}" for i in range(200))
        ok, message = launch_chatgpt_lite_assist("Show", long_tracklist)
        assert ok is True
        assert len(opened) == 1
        assert opened[0] == "https://chatgpt.com/"
        assert qapp.clipboard().text().startswith("YouTube Bootlegger")
        assert "clipboard" in message.lower()
