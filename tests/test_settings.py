"""Unit tests for persistent application settings."""

from src.youtube_bootlegger.core.llm_extraction import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
)
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider


class FakeSettingsBackend:
    """In-memory stand-in for QSettings, avoiding disk I/O in tests."""

    def __init__(self):
        self._data = {}
        self.sync_calls = 0

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, value):
        self._data[key] = value

    def sync(self):
        self.sync_calls += 1


class TestAppSettingsDefaults:
    """Tests for AppSettings default values."""

    def test_use_external_ytdlp_defaults_to_false(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.use_external_ytdlp is False

    def test_ytdlp_path_defaults_to_empty(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.ytdlp_path == ""

    def test_ffmpeg_path_defaults_to_empty(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.ffmpeg_path == ""


class TestAppSettingsRoundTrip:
    """Tests for setting and reading back values."""

    def test_use_external_ytdlp_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.use_external_ytdlp = True
        assert settings.use_external_ytdlp is True

    def test_use_external_ytdlp_accepts_string_bool_from_backend(self):
        """QSettings on some platforms round-trips bools through strings."""
        backend = FakeSettingsBackend()
        backend.setValue("ytdlp/use_external", "true")
        settings = AppSettings(backend)
        assert settings.use_external_ytdlp is True

    def test_ytdlp_path_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.ytdlp_path = "/usr/local/bin/yt-dlp"
        assert settings.ytdlp_path == "/usr/local/bin/yt-dlp"

    def test_ytdlp_path_strips_whitespace(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.ytdlp_path = "  /usr/local/bin/yt-dlp  "
        assert settings.ytdlp_path == "/usr/local/bin/yt-dlp"

    def test_ffmpeg_path_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.ffmpeg_path = "/opt/ffmpeg/bin/ffmpeg"
        assert settings.ffmpeg_path == "/opt/ffmpeg/bin/ffmpeg"

    def test_sync_delegates_to_backend(self):
        backend = FakeSettingsBackend()
        settings = AppSettings(backend)
        settings.sync()
        assert backend.sync_calls == 1


class TestResolvedCommands:
    """Tests for resolved_ytdlp_command / resolved_ffmpeg_command."""

    def test_resolved_ytdlp_command_defaults_to_path_lookup(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.resolved_ytdlp_command() == "yt-dlp"

    def test_resolved_ytdlp_command_uses_custom_path_when_set(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.ytdlp_path = "/custom/yt-dlp"
        assert settings.resolved_ytdlp_command() == "/custom/yt-dlp"

    def test_resolved_ffmpeg_command_defaults_to_path_lookup(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.resolved_ffmpeg_command() == "ffmpeg"

    def test_resolved_ffmpeg_command_uses_custom_path_when_set(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.ffmpeg_path = "/custom/ffmpeg"
        assert settings.resolved_ffmpeg_command() == "/custom/ffmpeg"

    def test_resolved_ffmpeg_command_ignores_blank_path(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.ffmpeg_path = "   "
        assert settings.resolved_ffmpeg_command() == "ffmpeg"


class TestLlmSettingsDefaults:
    def test_llm_provider_defaults_to_none(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.llm_provider == LlmProvider.NONE

    def test_llm_api_fields_default_to_empty(self):
        settings = AppSettings(FakeSettingsBackend())
        assert settings.openai_api_key == ""
        assert settings.openai_model == ""
        assert settings.anthropic_api_key == ""
        assert settings.anthropic_model == ""
        assert settings.vertex_api_key == ""
        assert settings.vertex_model == ""
        assert settings.compatible_base_url == ""
        assert settings.compatible_bearer_token == ""
        assert settings.compatible_model == ""


class TestLlmSettingsRoundTrip:
    def test_llm_provider_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.llm_provider = LlmProvider.OPENAI
        assert settings.llm_provider == LlmProvider.OPENAI

    def test_openai_settings_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.openai_api_key = "sk-test"
        settings.openai_model = DEFAULT_OPENAI_MODEL
        assert settings.openai_api_key == "sk-test"
        assert settings.openai_model == DEFAULT_OPENAI_MODEL

    def test_anthropic_settings_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.anthropic_api_key = "ant-test"
        settings.anthropic_model = DEFAULT_ANTHROPIC_MODEL
        assert settings.anthropic_api_key == "ant-test"
        assert settings.anthropic_model == DEFAULT_ANTHROPIC_MODEL

    def test_vertex_settings_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.vertex_api_key = "vertex-test"
        settings.vertex_model = DEFAULT_VERTEX_MODEL
        assert settings.vertex_api_key == "vertex-test"
        assert settings.vertex_model == DEFAULT_VERTEX_MODEL

    def test_compatible_settings_round_trip(self):
        settings = AppSettings(FakeSettingsBackend())
        settings.compatible_base_url = "https://example.com/v1"
        settings.compatible_bearer_token = "token"
        settings.compatible_model = "local-model"
        assert settings.compatible_base_url == "https://example.com/v1"
        assert settings.compatible_bearer_token == "token"
        assert settings.compatible_model == "local-model"

    def test_invalid_provider_value_falls_back_to_none(self):
        backend = FakeSettingsBackend()
        backend.setValue("llm/provider", "not-a-provider")
        settings = AppSettings(backend)
        assert settings.llm_provider == LlmProvider.NONE
