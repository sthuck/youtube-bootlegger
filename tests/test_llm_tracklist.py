"""Unit tests for LLM settings mapping and tracklist extraction."""

import json

import pytest

from src.youtube_bootlegger.llm import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
    ApiProvider,
    LlmEndpoint,
    LlmError,
    LlmExtractionError,
    TracklistExtraction,
    endpoint_from_settings,
    extract_tracklist_metadata,
    is_llm_configured,
    parse_extraction_response,
    resolve_model,
    validate_extraction,
)
from src.youtube_bootlegger.llm.client import OPENAI_CHAT_URL
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


class TestEndpointFromSettings:
    def test_maps_each_api_provider(self):
        cases = [
            (
                make_settings(llm_provider=LlmProvider.OPENAI, openai_api_key="sk"),
                LlmEndpoint(ApiProvider.OPENAI, DEFAULT_OPENAI_MODEL, "sk"),
            ),
            (
                make_settings(llm_provider=LlmProvider.ANTHROPIC, anthropic_api_key="ant"),
                LlmEndpoint(ApiProvider.ANTHROPIC, DEFAULT_ANTHROPIC_MODEL, "ant"),
            ),
            (
                make_settings(llm_provider=LlmProvider.VERTEX, vertex_api_key="g"),
                LlmEndpoint(ApiProvider.GEMINI, DEFAULT_VERTEX_MODEL, "g"),
            ),
            (
                make_settings(
                    llm_provider=LlmProvider.OPENAI_COMPATIBLE,
                    compatible_base_url="http://localhost:11434/v1",
                    compatible_bearer_token="tok",
                    compatible_model="llama3",
                ),
                LlmEndpoint(
                    ApiProvider.OPENAI_COMPATIBLE,
                    "llama3",
                    "tok",
                    base_url="http://localhost:11434/v1",
                ),
            ),
        ]
        for settings, expected in cases:
            assert endpoint_from_settings(settings) == expected

    def test_rejects_missing_credentials(self):
        settings = make_settings(llm_provider=LlmProvider.OPENAI)
        with pytest.raises(LlmError, match="not configured"):
            endpoint_from_settings(settings)

    def test_rejects_chatgpt_lite(self):
        settings = make_settings(llm_provider=LlmProvider.CHATGPT_LITE)
        with pytest.raises(LlmError, match="browser"):
            endpoint_from_settings(settings)


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
        json_schema = captured["body"]["response_format"]["json_schema"]
        assert json_schema["name"] == "tracklist_extraction"
        assert set(json_schema["schema"]["required"]) == {
            "template",
            "artist_name",
            "album_name",
        }

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

