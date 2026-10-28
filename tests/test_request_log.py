"""Tests for the optional AI request debug log; no network calls."""

import json

import pytest

from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider
from src.youtube_bootlegger.core.video_info import VideoComment
from src.youtube_bootlegger.llm import request_log
from src.youtube_bootlegger.llm.http import LlmError
from src.youtube_bootlegger.llm.request_log import REDACTED, redact_headers, with_request_log
from src.youtube_bootlegger.llm.track_finder import find_tracklist
from src.youtube_bootlegger.llm.tracklist import extract_tracklist_metadata
from tests.test_llm_tracklist import FakeSettingsBackend
from tests.test_track_finder import COMMENT, ENTRIES, discovery, make_video, openai_reply


class FileBackend(FakeSettingsBackend):
    """In-memory settings that claim to live in a file, like QSettings."""

    def __init__(self, path):
        super().__init__()
        self._path = path

    def fileName(self):
        return str(self._path)


@pytest.fixture
def settings(tmp_path):
    settings = AppSettings(FileBackend(tmp_path / "config" / "YouTubeBootlegger.ini"))
    settings.llm_provider = LlmProvider.OPENAI
    settings.openai_api_key = "sk-secret"
    settings.log_ai_requests = True
    return settings


def read_entries(settings):
    text = settings.ai_request_log_path.read_text(encoding="utf-8")
    return [json.loads(chunk) for chunk in text.split("\n\n") if chunk.strip()]


def reply(body):
    return lambda url, headers, payload: body


def test_setting_defaults_off_and_path_sits_next_to_settings_file(tmp_path):
    settings = AppSettings(FileBackend(tmp_path / "YouTubeBootlegger.ini"))
    assert settings.log_ai_requests is False
    assert settings.ai_request_log_path == tmp_path / "ai-requests.log"


def test_no_path_without_a_settings_file():
    assert AppSettings(FakeSettingsBackend()).ai_request_log_path is None


def test_off_returns_the_same_post(settings):
    settings.log_ai_requests = False
    post = reply({})
    assert with_request_log(post, settings) is post


def test_logs_request_and_response_without_credentials(settings):
    post = with_request_log(reply({"ok": True}), settings)
    headers = {"Authorization": "Bearer sk-secret", "Content-Type": "application/json"}

    assert post("https://api.example/v1", headers, {"messages": ["hi"]}) == {"ok": True}

    (entry,) = read_entries(settings)
    assert entry["url"] == "https://api.example/v1"
    assert entry["headers"] == {"Authorization": REDACTED, "Content-Type": "application/json"}
    assert entry["request"] == {"messages": ["hi"]}
    assert entry["response"] == {"ok": True}
    assert entry["error"] is None
    assert "sk-secret" not in settings.ai_request_log_path.read_text()


def test_logs_failures_and_reraises(settings):
    def failing(url, headers, payload):
        raise LlmError("HTTP 429")

    with pytest.raises(LlmError, match="429"):
        with_request_log(failing, settings)("u", {}, {})
    (entry,) = read_entries(settings)
    assert entry["error"] == "HTTP 429" and entry["response"] is None


@pytest.mark.parametrize("name", ["Authorization", "x-api-key", "x-goog-api-key", "X-Token"])
def test_redacts_credential_headers(name):
    assert redact_headers({name: "secret"}) == {name: REDACTED}


def test_unwritable_log_does_not_break_the_request(settings, monkeypatch):
    def broken(*args, **kwargs):
        raise PermissionError("read-only")

    monkeypatch.setattr(request_log.Path, "open", broken)
    assert with_request_log(reply({"ok": 1}), settings)("u", {}, {}) == {"ok": 1}


def test_rotates_large_log(settings, monkeypatch):
    monkeypatch.setattr(request_log, "MAX_LOG_BYTES", 10)
    post = with_request_log(reply({}), settings)
    post("first", {}, {})
    post("second", {}, {})
    assert [e["url"] for e in read_entries(settings)] == ["second"]
    rotated = settings.ai_request_log_path.with_name("ai-requests.log.1")
    assert '"first"' in rotated.read_text()


def test_find_and_detect_format_are_both_logged(settings):
    info = make_video(duration=4000, comments=(VideoComment("x", COMMENT.text),))
    find_tracklist(settings, info, http_post=openai_reply(
        discovery("comment:1", ENTRIES).model_dump()))
    extract_tracklist_metadata(settings, "Band Live", "0:00 Opener", http_post=openai_reply({
        "template": "%mm%:%ss% %songname%", "artist_name": "", "album_name": "",
    }))
    first, second = read_entries(settings)
    assert "0:00 1. Opener" in json.dumps(first["request"], ensure_ascii=False)
    assert "0:00 Opener" in json.dumps(second["request"], ensure_ascii=False)
    assert first["headers"]["Authorization"] == REDACTED
