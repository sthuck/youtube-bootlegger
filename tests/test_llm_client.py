"""Unit tests for the provider-agnostic LLM client and HTTP transport."""

import json

import pytest
import requests
from pydantic import BaseModel

from src.youtube_bootlegger.llm.client import (
    ANTHROPIC_MESSAGES_URL,
    GEMINI_GENERATE_URL,
    MAX_OUTPUT_TOKENS,
    OPENAI_CHAT_URL,
    ApiProvider,
    LlmEndpoint,
    OutputSchema,
    build_chat_request,
    complete_structured,
    parse_structured,
    response_text,
    strict_json_schema,
)
from src.youtube_bootlegger.llm.http import (
    MAX_ERROR_DETAIL_CHARS,
    LlmError,
    error_message,
    post_json,
)


class Weather(BaseModel):
    """A non-tracklist model, to prove the client is generic."""

    city: str
    celsius: int


SCHEMA = OutputSchema.from_model("weather", Weather)


def _request(provider, **kwargs):
    endpoint = LlmEndpoint(provider, kwargs.pop("model", "m"), **kwargs)
    return build_chat_request(endpoint, system="system", user="user", output_schema=SCHEMA)


class TestStrictJsonSchema:
    def test_requires_all_fields_and_forbids_extras(self):
        schema = strict_json_schema(Weather)
        assert schema["required"] == ["city", "celsius"]
        assert schema["additionalProperties"] is False
        assert "title" not in schema
        assert "title" not in schema["properties"]["city"]

    def test_inlines_nested_models_and_makes_them_strict(self):
        class Entry(BaseModel):
            title: str
            seconds: int

        class Listing(BaseModel):
            entries: list[Entry]

        schema = strict_json_schema(Listing)
        assert "$defs" not in schema
        item = schema["properties"]["entries"]["items"]
        assert item["type"] == "object"
        # A field may be called "title"; only the keyword is dropped.
        assert list(item["properties"]) == ["title", "seconds"]
        assert item["required"] == ["title", "seconds"]
        assert item["additionalProperties"] is False
        assert "title" not in item["properties"]["title"]


class TestBuildChatRequest:
    def test_openai_request(self):
        request = _request(ApiProvider.OPENAI, model="gpt-x", api_key="sk-test")
        assert request.url == OPENAI_CHAT_URL
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert request.body["model"] == "gpt-x"
        assert request.body["max_completion_tokens"] == MAX_OUTPUT_TOKENS == 40_000
        assert "max_tokens" not in request.body
        assert request.body["messages"][0] == {"role": "system", "content": "system"}
        json_schema = request.body["response_format"]["json_schema"]
        assert json_schema["name"] == "weather"
        assert json_schema["strict"] is True
        assert json_schema["schema"] == SCHEMA.schema

    def test_anthropic_request(self):
        request = _request(ApiProvider.ANTHROPIC, model="claude-x", api_key="sk-ant")
        assert request.url == ANTHROPIC_MESSAGES_URL
        assert request.headers["x-api-key"] == "sk-ant"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert request.body["model"] == "claude-x"
        assert request.body["system"] == "system"
        assert request.body["messages"] == [{"role": "user", "content": "user"}]
        assert request.body["output_config"]["format"] == {
            "type": "json_schema",
            "schema": SCHEMA.schema,
        }
        assert request.body["max_tokens"] == MAX_OUTPUT_TOKENS

    def test_gemini_request(self):
        request = _request(ApiProvider.GEMINI, model="gemini-x", api_key="gemini-key")
        assert request.url == GEMINI_GENERATE_URL.format(model="gemini-x")
        assert request.headers["x-goog-api-key"] == "gemini-key"
        assert request.body["systemInstruction"]["parts"][0]["text"] == "system"
        assert request.body["contents"][0]["parts"][0]["text"] == "user"
        config = request.body["generationConfig"]
        assert config["responseMimeType"] == "application/json"
        assert config["responseJsonSchema"] == SCHEMA.schema
        assert config["maxOutputTokens"] == MAX_OUTPUT_TOKENS

    def test_compatible_request_includes_base_url_and_max_tokens(self):
        request = _request(
            ApiProvider.OPENAI_COMPATIBLE,
            model="local-model",
            api_key="token-123",
            base_url="https://example.com/v1/",
        )
        assert request.url == "https://example.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer token-123"
        assert request.body["model"] == "local-model"
        assert request.body["max_tokens"] == MAX_OUTPUT_TOKENS
        assert "max_completion_tokens" not in request.body

    def test_compatible_request_omits_auth_without_token(self):
        request = _request(
            ApiProvider.OPENAI_COMPATIBLE,
            base_url="https://example.com/v1/chat/completions",
        )
        assert request.url == "https://example.com/v1/chat/completions"
        assert "Authorization" not in request.headers

    def test_compatible_request_requires_base_url(self):
        with pytest.raises(LlmError, match="not configured"):
            _request(ApiProvider.OPENAI_COMPATIBLE)


class TestResponseText:
    @pytest.mark.parametrize(
        ("provider", "body"),
        [
            (ApiProvider.OPENAI, {"choices": [{"message": {"content": "{}"}}]}),
            (
                ApiProvider.OPENAI_COMPATIBLE,
                {"choices": [{"message": {"content": [{"type": "text", "text": "{}"}]}}]},
            ),
            (
                ApiProvider.ANTHROPIC,
                {
                    "content": [{"type": "thinking", "thinking": "hm"}, {"type": "text", "text": "{}"}],
                    "stop_reason": "end_turn",
                },
            ),
            (
                ApiProvider.GEMINI,
                {"candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}]},
            ),
        ],
    )
    def test_extracts_text(self, provider, body):
        assert response_text(provider, body) == "{}"

    @pytest.mark.parametrize(
        ("provider", "body"),
        [
            (
                ApiProvider.OPENAI,
                {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]},
            ),
            (
                ApiProvider.ANTHROPIC,
                {"content": [{"type": "text", "text": "{"}], "stop_reason": "max_tokens"},
            ),
            (ApiProvider.GEMINI, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
        ],
    )
    def test_reports_truncated_output(self, provider, body):
        with pytest.raises(LlmError, match="cut off at the output token limit"):
            response_text(provider, body)

    def test_reports_gemini_safety_stop_without_content(self):
        body = {"candidates": [{"finishReason": "SAFETY"}]}
        with pytest.raises(LlmError, match=r"stopped before finishing \(SAFETY\)"):
            response_text(ApiProvider.GEMINI, body)

    def test_reports_openai_content_filter(self):
        body = {"choices": [{"message": {"content": None}, "finish_reason": "content_filter"}]}
        with pytest.raises(LlmError, match="content_filter"):
            response_text(ApiProvider.OPENAI, body)

    def test_reports_openai_refusal(self):
        body = {"choices": [{"message": {"content": None, "refusal": "no thanks"}}]}
        with pytest.raises(LlmError, match="no thanks"):
            response_text(ApiProvider.OPENAI, body)

    def test_surfaces_embedded_error(self):
        with pytest.raises(LlmError, match="invalid api key"):
            response_text(ApiProvider.OPENAI, {"error": {"message": "invalid api key"}})

    @pytest.mark.parametrize(
        ("provider", "body"),
        [
            (ApiProvider.OPENAI, {"choices": []}),
            (ApiProvider.ANTHROPIC, {"content": "nope"}),
            (ApiProvider.GEMINI, {"candidates": [{"finishReason": "STOP"}]}),
        ],
    )
    def test_rejects_unexpected_shapes(self, provider, body):
        with pytest.raises(LlmError, match="unexpected response shape"):
            response_text(provider, body)

    def test_rejects_empty_text(self):
        with pytest.raises(LlmError, match="empty response"):
            response_text(ApiProvider.OPENAI, {"choices": [{"message": {"content": "  "}}]})


class TestParseStructured:
    def test_parses_json_text(self):
        result = parse_structured('{"city": "Haifa", "celsius": 24}', Weather)
        assert result == Weather(city="Haifa", celsius=24)

    def test_parses_dict(self):
        assert parse_structured({"city": "Haifa", "celsius": 24}, Weather).city == "Haifa"

    def test_parses_markdown_fenced_json(self):
        fenced = '```json\n{"city": "Haifa", "celsius": 24}\n```'
        assert parse_structured(fenced, Weather).celsius == 24

    def test_rejects_invalid_json(self):
        with pytest.raises(LlmError, match="invalid JSON"):
            parse_structured("not-json", Weather)

    def test_rejects_schema_mismatch(self):
        with pytest.raises(LlmError, match="failed validation"):
            parse_structured('{"city": "Haifa"}', Weather)


class TestCompleteStructured:
    def test_returns_typed_model(self):
        captured = {}

        def fake_post(url, headers, body):
            captured.update(url=url, headers=dict(headers), body=body)
            content = json.dumps({"city": "Haifa", "celsius": 24})
            return {"choices": [{"message": {"content": content}}]}

        result = complete_structured(
            LlmEndpoint(ApiProvider.OPENAI, "gpt-x", "sk-test"),
            system="system",
            user="user",
            output=Weather,
            schema_name="weather",
            http_post=fake_post,
        )
        assert result == Weather(city="Haifa", celsius=24)
        assert captured["url"] == OPENAI_CHAT_URL
        assert captured["body"]["response_format"]["json_schema"]["name"] == "weather"

    def test_wraps_transport_errors(self):
        def failing_post(_url, _headers, _body):
            raise RuntimeError("network down")

        with pytest.raises(LlmError, match="LLM request failed: network down"):
            complete_structured(
                LlmEndpoint(ApiProvider.ANTHROPIC, "claude-x", "key"),
                system="s",
                user="u",
                output=Weather,
                schema_name="weather",
                http_post=failing_post,
            )


class TestErrorMessage:
    def test_truncates_non_json_body(self):
        message = error_message(b"<html>" + b"x" * 5000 + b"</html>")
        assert len(message) <= MAX_ERROR_DETAIL_CHARS + 1
        assert message.endswith("…")

    def test_keeps_short_non_json_body(self):
        assert error_message(b"Bad Gateway") == "Bad Gateway"

    def test_prefers_embedded_json_error(self):
        assert error_message(b'{"error": {"message": "nope"}}') == "nope"


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
        with pytest.raises(LlmError, match="redirect to https://other/v1"):
            post_json("http://x/v1", {}, {})

    def test_reports_http_error_detail(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "post",
            lambda *_a, **_k: _fake_response(401, b'{"error": {"message": "bad key"}}'),
        )
        with pytest.raises(LlmError, match="HTTP 401: bad key"):
            post_json("https://x/v1", {}, {})

    def test_wraps_connection_errors(self, monkeypatch):
        def boom(*_a, **_k):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "post", boom)
        with pytest.raises(LlmError, match="LLM request failed: refused"):
            post_json("https://x/v1", {}, {})

    def test_rejects_non_object_json(self, monkeypatch):
        monkeypatch.setattr(requests, "post", lambda *_a, **_k: _fake_response(200, b"[]"))
        with pytest.raises(LlmError, match="unexpected response shape"):
            post_json("https://x/v1", {}, {})
