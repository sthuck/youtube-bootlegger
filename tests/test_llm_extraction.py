"""Unit tests for LLM tracklist extraction."""

import json

import pytest

from src.youtube_bootlegger.core.llm_extraction import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
    LlmExtractionError,
    TracklistExtraction,
    build_extraction_prompt,
    build_litellm_kwargs,
    extract_tracklist_metadata,
    is_llm_configured,
    parse_extraction_response,
    resolve_litellm_model,
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


class TestBuildExtractionPrompt:
    def test_includes_video_title_and_tracklist(self):
        prompt = build_extraction_prompt(
            "Phish - 12/31/2023",
            "Tweezer - 0:00\nHarry Hood - 12:34",
        )
        assert "Phish - 12/31/2023" in prompt
        assert "Tweezer - 0:00" in prompt
        assert "%songname%" in prompt
        assert "template" in prompt.lower()


class TestIsLlmConfigured:
    def test_none_provider_is_not_configured(self):
        settings = make_settings(llm_provider=LlmProvider.NONE, openai_api_key="sk-test")
        assert is_llm_configured(settings) is False

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


class TestResolveLitellmModel:
    def test_openai_default_model(self):
        settings = make_settings(llm_provider=LlmProvider.OPENAI)
        assert resolve_litellm_model(settings) == DEFAULT_OPENAI_MODEL

    def test_anthropic_prefixes_model(self):
        settings = make_settings(
            llm_provider=LlmProvider.ANTHROPIC,
            anthropic_model="claude-sonnet-5",
        )
        assert resolve_litellm_model(settings) == "anthropic/claude-sonnet-5"

    def test_vertex_prefixes_model(self):
        settings = make_settings(llm_provider=LlmProvider.VERTEX)
        assert resolve_litellm_model(settings) == f"vertex_ai/{DEFAULT_VERTEX_MODEL}"


class TestBuildLitellmKwargs:
    def test_openai_kwargs(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
            openai_model="gpt-5.4-mini",
        )
        kwargs = build_litellm_kwargs(settings)
        assert kwargs["model"] == "gpt-5.4-mini"
        assert kwargs["api_key"] == "sk-test"

    def test_compatible_kwargs_include_base_url(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI_COMPATIBLE,
            compatible_base_url="https://example.com/v1/",
            compatible_bearer_token="token-123",
            compatible_model="local-model",
        )
        kwargs = build_litellm_kwargs(settings)
        assert kwargs["model"] == "local-model"
        assert kwargs["api_base"] == "https://example.com/v1"
        assert kwargs["api_key"] == "token-123"


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


class TestExtractTracklistMetadata:
    def test_requires_configured_provider(self):
        settings = make_settings(llm_provider=LlmProvider.NONE)
        with pytest.raises(LlmExtractionError, match="not configured"):
            extract_tracklist_metadata(settings, "Show Title", "Song - 0:00")

    def test_requires_tracklist(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
        )
        with pytest.raises(LlmExtractionError, match="empty"):
            extract_tracklist_metadata(settings, "Show Title", "   ")

    def test_calls_completion_fn_and_parses_response(self):
        settings = make_settings(
            llm_provider=LlmProvider.OPENAI,
            openai_api_key="sk-test",
            openai_model=DEFAULT_OPENAI_MODEL,
        )

        class FakeChoice:
            def __init__(self, content):
                self.message = type("Message", (), {"content": content})()

        class FakeResponse:
            def __init__(self, content):
                self.choices = [FakeChoice(content)]

        captured = {}

        def fake_completion(**kwargs):
            captured.update(kwargs)
            content = json.dumps(
                {
                    "template": "[%mm%:%ss%] %songname%",
                    "artist_name": "The Band",
                    "album_name": "Live at Madison Square Garden",
                }
            )
            return FakeResponse(content)

        result = extract_tracklist_metadata(
            settings,
            "The Band Live at Madison Square Garden",
            "[0:00] Opener\n[5:00] Closer",
            completion_fn=fake_completion,
        )

        assert isinstance(result, TracklistExtraction)
        assert result.template == "[%mm%:%ss%] %songname%"
        assert result.artist_name == "The Band"
        assert result.album_name == "Live at Madison Square Garden"
        assert captured["model"] == DEFAULT_OPENAI_MODEL
        assert captured["api_key"] == "sk-test"
        assert captured["response_format"] is TracklistExtraction
        assert captured["messages"][1]["content"].startswith("YouTube Bootlegger")

    def test_wraps_completion_errors(self):
        settings = make_settings(
            llm_provider=LlmProvider.ANTHROPIC,
            anthropic_api_key="key",
        )

        def failing_completion(**_kwargs):
            raise RuntimeError("network down")

        with pytest.raises(LlmExtractionError, match="LLM request failed"):
            extract_tracklist_metadata(
                settings,
                "Show",
                "Song - 0:00",
                completion_fn=failing_completion,
            )
