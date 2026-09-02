"""Unit tests for the declarative settings schema."""

import pytest

from src.youtube_bootlegger.controller.settings_schema import (
    SETTING_FIELDS,
    SETTING_FIELDS_BY_NAME,
    _snake_to_camel,
)
from src.youtube_bootlegger.core.settings import AppSettings, LlmProvider

# The QML in SettingsPanel.qml binds to these names, so drifting from them
# silently breaks the UI. Keep this list in sync with the .qml bindings.
EXPECTED_QML_NAMES = {
    "use_external_ytdlp": "useExternalYtdlp",
    "ytdlp_path": "ytdlpPath",
    "ffmpeg_path": "ffmpegPath",
    "llm_provider": "llmProvider",
    "openai_api_key": "openaiApiKey",
    "openai_model": "openaiModel",
    "anthropic_api_key": "anthropicApiKey",
    "anthropic_model": "anthropicModel",
    "vertex_api_key": "vertexApiKey",
    "vertex_model": "vertexModel",
    "compatible_base_url": "compatibleBaseUrl",
    "compatible_bearer_token": "compatibleBearerToken",
    "compatible_model": "compatibleModel",
}


class TestNameDerivation:
    """Naming rules that the QML API depends on."""

    def test_snake_to_camel(self):
        assert _snake_to_camel("openai_api_key") == "openaiApiKey"
        assert _snake_to_camel("ytdlp_path") == "ytdlpPath"
        assert _snake_to_camel("single") == "single"

    def test_schema_covers_exactly_the_expected_settings(self):
        assert set(SETTING_FIELDS_BY_NAME) == set(EXPECTED_QML_NAMES)

    @pytest.mark.parametrize("name,qml_name", sorted(EXPECTED_QML_NAMES.items()))
    def test_qml_names_match_the_ui_contract(self, name, qml_name):
        field = SETTING_FIELDS_BY_NAME[name]
        assert field.qml_name == qml_name
        assert field.signal_name == f"{qml_name}Changed"
        assert field.slot_name == f"set{qml_name[0].upper()}{qml_name[1:]}"


class TestFieldAccess:
    """Reading and writing settings through the schema."""

    @pytest.mark.parametrize("field", SETTING_FIELDS, ids=lambda f: f.name)
    def test_every_field_maps_to_a_real_setting(self, field, settings):
        assert hasattr(AppSettings, field.name)
        assert field.read_from(settings) is not None

    def test_round_trips_a_string_value(self, settings):
        field = SETTING_FIELDS_BY_NAME["openai_api_key"]
        field.write_to(settings, "  sk-test  ")
        assert field.read_from(settings) == "sk-test"

    def test_round_trips_a_bool_value(self, settings):
        field = SETTING_FIELDS_BY_NAME["use_external_ytdlp"]
        field.write_to(settings, True)
        assert field.read_from(settings) is True

    def test_secret_fields_are_flagged(self):
        secrets = {f.name for f in SETTING_FIELDS if f.secret}
        assert secrets == {
            "openai_api_key",
            "anthropic_api_key",
            "vertex_api_key",
            "compatible_bearer_token",
        }


class TestLlmProviderCoercion:
    """The provider field normalizes legacy and invalid values."""

    def test_reads_as_plain_string(self, settings):
        field = SETTING_FIELDS_BY_NAME["llm_provider"]
        assert field.read_from(settings) == LlmProvider.CHATGPT_LITE.value

    def test_accepts_a_valid_provider(self, settings):
        field = SETTING_FIELDS_BY_NAME["llm_provider"]
        field.write_to(settings, "anthropic")
        assert field.read_from(settings) == "anthropic"

    def test_maps_legacy_none_to_lite(self, settings):
        field = SETTING_FIELDS_BY_NAME["llm_provider"]
        field.write_to(settings, "none")
        assert field.read_from(settings) == LlmProvider.CHATGPT_LITE.value

    def test_falls_back_on_unknown_provider(self, settings):
        field = SETTING_FIELDS_BY_NAME["llm_provider"]
        field.write_to(settings, "not-a-provider")
        assert field.read_from(settings) == LlmProvider.CHATGPT_LITE.value
