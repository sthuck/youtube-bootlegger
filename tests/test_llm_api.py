"""Unit tests for LLM API integration."""

import json

import pytest
import requests

from src.youtube_bootlegger.llm import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
    LlmExtractionError,
    TracklistExtraction,
    build_chat_request,
    extract_tracklist_metadata,
    is_llm_configured,
    parse_extraction_response,
    resolve_model,
    validate_extraction,
)
from src.youtube_bootlegger.llm.llm_api import (
    ANTHROPIC_MESSAGES_URL,
    GEMINI_GENERATE_URL,
    MAX_ERROR_DETAIL_CHARS,
    MAX_OUTPUT_TOKENS,
    OPENAI_CHAT_URL,
    _error_message,
    post_json,
    response_text,
)
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider


class FakeSettingsBackend:
    """In-memory stand-in for QSettings."""

    def __init__(self):
        self._data = {}

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, value):
        self._data[key] = value

    def sync(self):
        pass


def make_settings(**kwargs) -> AppSettings:
    backend = FakeSettingsBackend()
    settings = AppSettings(backend)
    for key, value in kwargs.items():
        setattr(settings, key, value)
    return settings


class TestIsLlmConfigured:
    def test_legacy_none_storage_is_treated_as_chatgpt_lite(self):
        settings = make_settings(llm_provider=LlmProvider.NONE, openai_api_key="sk-test")
        assert settings.llm_provider == LlmProvider.CHATGPT_LITE
        assert is_llm_configured(settings) is True

    def test_chatgpt_lite_is_configured_without_credentials(self):
        settings = make_settings(llm_provider=LlmProvider.CHATGPT_LITE)
        assert is_llm_configured(settings) is True

    def test_openai_requires_api_key(self):
        settings = make_settings(llm_provider=LlmProvider.OPENAI, openai_api_key="")
        assert is_llm_configured(settings) is False

        settings.openai_api_key = "sk-test"
        assert is_llm_configured(settings) is True

    def test_anthropic_requires_api_key(self):
        settings = make_settings(llm_provider=LlmProvider.ANTHROPIC, anthropic_api_key="key")
        assert is_llm_configured(settings) is True

    def test_vertex_requires_api_key(self):
        settings = make_settings(llm_provider=LlmProvider.VERTEX, vertex_api_key="key")
        assert is_llm_configured(settings) is True

    def test_compatible_requires_base_url(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI_COMPATIBLE,
            compatible_base_url="https://example.com/v1",
        )
        assert is_llm_configured(settings) is True


class TestResolveModel:
    def test_openai_default_model(self):
        settings = make_settings(llm_provider=LlmProvider.OPENAI)
        assert resolve_model(settings) == DEFAULT_OPENAI_MODEL

    def test_anthropic_uses_bare_model_id(self):
        settings = make_settings(
            llm_provider=LlmProvider.ANTHROPIC,
            anthropic_model="anthropic/claude-sonnet-5",
        )
        assert resolve_model(settings) == "claude-sonnet-5"

    def test_vertex_uses_bare_gemini_model(self):
        settings = make_settings(llm_provider=LlmProvider.VERTEX)
        assert resolve_model(settings) == DEFAULT_VERTEX_MODEL

    def test_vertex_strips_legacy_prefixes(self):
        settings = make_settings(
            llm_provider=LlmProvider.VERTEX,
            vertex_model="vertex_ai/gemini-2.0-flash",
        )
        assert resolve_model(settings) == "gemini-2.0-flash"


def _extraction_json() -> str:
    return json.dumps(
        {
            "template": "[%mm%:%ss%] %songname%",
            "artist_name": "The Band",
            "album_name": "Live at Madison Square Garden",
        }
    )


class TestBuildChatRequest:
    def test_openai_request(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
            openai_model=DEFAULT_OPENAI_MODEL,
        )
        request = build_chat_request(settings, "system", "user")
        assert request.url == OPENAI_CHAT_URL
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert request.body["model"] == DEFAULT_OPENAI_MODEL
        assert request.body["max_completion_tokens"] == MAX_OUTPUT_TOKENS
        assert "max_tokens" not in request.body
        assert request.body["messages"][0] == {"role": "system", "content": "system"}
        schema = request.body["response_format"]["json_schema"]
        assert schema["name"] == "tracklist_extraction"
        assert schema["strict"] is True
        assert schema["schema"]["additionalProperties"] is False
        assert set(schema["schema"]["required"]) == {
            "template",
            "artist_name",
            "album_name",
        }

    def test_anthropic_request(self):
        settings = make_settings(
            llm_provider=LlmProvider.ANTHROPIC,
            anthropic_api_key="sk-ant",
            anthropic_model=DEFAULT_ANTHROPIC_MODEL,
        )
        request = build_chat_request(settings, "system", "user")
        assert request.url == ANTHROPIC_MESSAGES_URL
        assert request.headers["x-api-key"] == "sk-ant"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert request.body["model"] == DEFAULT_ANTHROPIC_MODEL
        assert request.body["system"] == "system"
        assert request.body["messages"] == [{"role": "user", "content": "user"}]
        assert request.body["output_config"]["format"]["type"] == "json_schema"
        assert request.body["max_tokens"] == MAX_OUTPUT_TOKENS

    def test_gemini_request(self):
        settings = make_settings(
            llm_provider=LlmProvider.VERTEX,
            vertex_api_key="gemini-key",
            vertex_model="gemini/gemini-2.0-flash",
        )
        request = build_chat_request(settings, "system", "user")
        assert request.url == GEMINI_GENERATE_URL.format(model="gemini-2.0-flash")
        assert request.headers["x-goog-api-key"] == "gemini-key"
        assert request.body["systemInstruction"]["parts"][0]["text"] == "system"
        assert request.body["contents"][0]["parts"][0]["text"] == "user"
        config = request.body["generationConfig"]
        assert config["responseMimeType"] == "application/json"
        assert config["responseJsonSchema"]["additionalProperties"] is False

    def test_compatible_request_includes_base_url_and_max_tokens(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI_COMPATIBLE,
            compatible_base_url="https://example.com/v1/",
            compatible_bearer_token="token-123",
            compatible_model="local-model",
        )
        request = build_chat_request(settings, "system", "user")
        assert request.url == "https://example.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer token-123"
        assert request.body["model"] == "local-model"
        assert request.body["max_tokens"] == MAX_OUTPUT_TOKENS
        assert "max_completion_tokens" not in request.body

    def test_compatible_request_omits_auth_without_token(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI_COMPATIBLE,
            compatible_base_url="https://example.com/v1/chat/completions",
        )
        request = build_chat_request(settings, "system", "user")
        assert request.url == "https://example.com/v1/chat/completions"
        assert "Authorization" not in request.headers


class TestParseExtractionResponse:
    def test_parses_valid_json(self):
        payload = json.dumps(
            {
                "template": "%songname% - %mm%:%ss%",
                "artist_name": "Phish",
                "album_name": "NYE 2023",
            }
        )
        result = parse_extraction_response(payload)
        assert result.template == "%songname% - %mm%:%ss%"
        assert result.artist_name == "Phish"
        assert result.album_name == "NYE 2023"

    def test_parses_dict_payload(self):
        payload = {
            "template": "%songname% - %mm%:%ss%",
            "artist_name": "Phish",
            "album_name": "NYE 2023",
        }
        result = parse_extraction_response(payload)
        assert result.template == "%songname% - %mm%:%ss%"

    def test_rejects_invalid_json(self):
        with pytest.raises(LlmExtractionError, match="invalid JSON"):
            parse_extraction_response("not-json")

    def test_rejects_empty_template(self):
        payload = json.dumps(
            {
                "template": "   ",
                "artist_name": "Phish",
                "album_name": "NYE 2023",
            }
        )
        with pytest.raises(LlmExtractionError, match="empty template"):
            parse_extraction_response(payload)

    def test_parses_markdown_fenced_json(self):
        payload = "```json\n" + json.dumps(
            {
                "template": "%songname% - %mm%:%ss%",
                "artist_name": "Phish",
                "album_name": "NYE 2023",
            }
        ) + "\n```"
        result = parse_extraction_response(payload)
        assert result.artist_name == "Phish"


class TestValidateExtraction:
    def test_accepts_matching_template(self):
        extraction = TracklistExtraction(
            template="%songname% - %mm%:%ss%",
            artist_name="Phish",
            album_name="NYE 2023",
        )
        result = validate_extraction(
            extraction,
            "Tweezer - 0:00\nHarry Hood - 12:34",
        )
        assert result.template == "%songname% - %mm%:%ss%"

    def test_rejects_invalid_template_syntax(self):
        extraction = TracklistExtraction(
            template="%songname%",
            artist_name="Phish",
            album_name="NYE 2023",
        )
        with pytest.raises(LlmExtractionError, match="invalid template"):
            validate_extraction(extraction, "Tweezer - 0:00")

    def test_rejects_template_that_does_not_match_tracklist(self):
        extraction = TracklistExtraction(
            template="[%mm%:%ss%] %songname%",
            artist_name="Phish",
            album_name="NYE 2023",
        )
        with pytest.raises(LlmExtractionError, match="does not match the track list"):
            validate_extraction(extraction, "Tweezer - 0:00\nHarry Hood - 12:34")


class TestExtractTracklistMetadata:
    def test_requires_configured_api_provider(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="",
        )
        with pytest.raises(LlmExtractionError, match="not configured"):
            extract_tracklist_metadata(settings, "Show Title", "Song - 0:00")

    def test_rejects_chatgpt_lite_provider(self):
        settings = make_settings(llm_provider=LlmProvider.CHATGPT_LITE)
        with pytest.raises(LlmExtractionError, match="browser"):
            extract_tracklist_metadata(settings, "Show Title", "Song - 0:00")

    def test_requires_tracklist(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
        )
        with pytest.raises(LlmExtractionError, match="empty"):
            extract_tracklist_metadata(settings, "Show Title", "   ")

    def test_requires_video_title(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
        )
        with pytest.raises(LlmExtractionError, match="Video title is required"):
            extract_tracklist_metadata(settings, "   ", "Song - 0:00")

    def test_calls_provider_and_parses_response(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
            openai_model=DEFAULT_OPENAI_MODEL,
        )
        captured = {}

        def fake_post(url, headers, body):
            captured["url"] = url
            captured["headers"] = dict(headers)
            captured["body"] = body
            return {"choices": [{"message": {"content": _extraction_json()}}]}

        result = extract_tracklist_metadata(
            settings,
            "The Band Live at Madison Square Garden",
            "[0:00] Opener\n[5:00] Closer",
            http_post=fake_post,
        )

        assert isinstance(result, TracklistExtraction)
        assert result.template == "[%mm%:%ss%] %songname%"
        assert result.artist_name == "The Band"
        assert result.album_name == "Live at Madison Square Garden"
        assert captured["url"] == OPENAI_CHAT_URL
        assert captured["headers"]["Authorization"] == "Bearer sk-test"
        assert captured["body"]["model"] == DEFAULT_OPENAI_MODEL
        assert captured["body"]["messages"][1]["content"].startswith("YouTube Bootlegger")

    def test_parses_anthropic_and_gemini_envelopes(self):
        content = _extraction_json()
        cases = [
            (
                make_settings(
                    llm_provider=LlmProvider.ANTHROPIC,
                    anthropic_api_key="key",
                ),
                {"content": [{"type": "text", "text": content}]},
            ),
            (
                make_settings(
                    llm_provider=LlmProvider.VERTEX,
                    vertex_api_key="key",
                ),
                {"candidates": [{"content": {"parts": [{"text": content}]}}]},
            ),
        ]
        for settings, envelope in cases:
            result = extract_tracklist_metadata(
                settings,
                "The Band Live",
                "[0:00] Opener\n[5:00] Closer",
                http_post=lambda _url, _headers, _body, envelope=envelope: envelope,
            )
            assert result.template == "[%mm%:%ss%] %songname%"

    def test_rejects_llm_template_that_does_not_parse_tracklist(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
        )

        def fake_post(_url, _headers, _body):
            content = json.dumps(
                {
                    "template": "%songname% - %mm%:%ss%",
                    "artist_name": "The Band",
                    "album_name": "Live",
                }
            )
            return {"choices": [{"message": {"content": content}}]}

        with pytest.raises(LlmExtractionError, match="does not match the track list"):
            extract_tracklist_metadata(
                settings,
                "Show",
                "[0:00] Opener\n[5:00] Closer",
                http_post=fake_post,
            )

    def test_wraps_transport_errors(self):
        settings = make_settings(
            llm_provider=LlmProvider.ANTHROPIC,
            anthropic_api_key="key",
        )

        def failing_post(_url, _headers, _body):
            raise RuntimeError("network down")

        with pytest.raises(LlmExtractionError, match="LLM request failed"):
            extract_tracklist_metadata(
                settings,
                "Show",
                "Song - 0:00",
                http_post=failing_post,
            )

    def test_surfaces_provider_error_payload(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
        )

        def fake_post(_url, _headers, _body):
            return {"error": {"message": "invalid api key"}}

        with pytest.raises(LlmExtractionError, match="invalid api key"):
            extract_tracklist_metadata(
                settings,
                "Show",
                "Song - 0:00",
                http_post=fake_post,
            )


class TestResponseText:
    @pytest.mark.parametrize(
        ("provider", "body"),
        [
            (
                LlmProvider.OPENAI,
                {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            ),
            (
                LlmProvider.ANTHROPIC,
                {"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens"},
            ),
            (LlmProvider.VERTEX, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
        ],
    )
    def test_reports_truncated_output(self, provider, body):
        with pytest.raises(LlmExtractionError, match="cut off at the output token limit"):
            response_text(provider, body)

    def test_reports_gemini_safety_stop_without_content(self):
        body = {"candidates": [{"finishReason": "SAFETY"}]}
        with pytest.raises(LlmExtractionError, match=r"stopped before finishing \(SAFETY\)"):
            response_text(LlmProvider.VERTEX, body)

    def test_reports_openai_content_filter(self):
        body = {
            "choices": [{"message": {"content": None}, "finish_reason": "content_filter"}]
        }
        with pytest.raises(LlmExtractionError, match="content_filter"):
            response_text(LlmProvider.OPENAI, body)

    def test_accepts_normal_finish(self):
        body = {"candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}]}
        assert response_text(LlmProvider.VERTEX, body) == "{}"


class TestErrorMessage:
    def test_truncates_non_json_body(self):
        html = b"<html>" + b"x" * 5000 + b"</html>"
        message = _error_message(html)
        assert len(message) <= MAX_ERROR_DETAIL_CHARS + 1
        assert message.endswith("\u2026")

    def test_keeps_short_non_json_body(self):
        assert _error_message(b"Bad Gateway") == "Bad Gateway"

    def test_prefers_embedded_json_error(self):
        assert _error_message(b'{"error": {"message": "nope"}}') == "nope"


def test_openai_request_uses_large_token_budget():
    settings = make_settings(llm_provider=LlmProvider.OPENAI, openai_api_key="sk-test")
    request = build_chat_request(settings, "system", "user")
    assert request.body["max_completion_tokens"] == MAX_OUTPUT_TOKENS == 40_000


def _fake_response(status: int, content: bytes, headers: dict | None = None):
    response = requests.Response()
    response.status_code = status
    response._content = content
    response.headers.update(headers or {})
    return response


class TestPostJson:
    def test_sends_json_without_following_redirects(self, monkeypatch):
        calls = {}

        def fake_post(url, **kwargs):
            calls["url"] = url
            calls.update(kwargs)
            return _fake_response(200, b'{"ok": true}')

        monkeypatch.setattr(requests, "post", fake_post)
        assert post_json("https://x/v1", {"A": "b"}, {"k": 1}) == {"ok": True}
        assert calls["url"] == "https://x/v1"
        assert calls["json"] == {"k": 1}
        assert calls["headers"] == {"A": "b"}
        assert calls["allow_redirects"] is False

    def test_rejects_redirect(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "post",
            lambda *_a, **_k: _fake_response(301, b"", {"Location": "https://other/v1"}),
        )
        with pytest.raises(LlmExtractionError, match="redirect to https://other/v1"):
            post_json("http://x/v1", {}, {})

    def test_reports_http_error_detail(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "post",
            lambda *_a, **_k: _fake_response(401, b'{"error": {"message": "bad key"}}'),
        )
        with pytest.raises(LlmExtractionError, match="HTTP 401: bad key"):
            post_json("https://x/v1", {}, {})

    def test_wraps_connection_errors(self, monkeypatch):
        def boom(*_a, **_k):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "post", boom)
        with pytest.raises(LlmExtractionError, match="LLM request failed: refused"):
            post_json("https://x/v1", {}, {})

    def test_rejects_non_object_json(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *_a, **_k: _fake_response(200, b"[]"))
        with pytest.raises(LlmExtractionError, match="unexpected response shape"):
            post_json("https://x/v1", {}, {})
