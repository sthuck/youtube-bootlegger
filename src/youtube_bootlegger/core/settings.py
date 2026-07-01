"""Persistent application settings for external tool configuration."""

from enum import StrEnum
from typing import Any, Protocol

from PySide6.QtCore import QSettings

_ORG_NAME = "YouTubeBootlegger"
_APP_NAME = "YouTubeBootlegger"

_USE_EXTERNAL_KEY = "ytdlp/use_external"
_YTDLP_PATH_KEY = "ytdlp/path"
_FFMPEG_PATH_KEY = "ffmpeg/path"

_LLM_PROVIDER_KEY = "llm/provider"
_OPENAI_API_KEY = "llm/openai_api_key"
_OPENAI_MODEL_KEY = "llm/openai_model"
_ANTHROPIC_API_KEY = "llm/anthropic_api_key"
_ANTHROPIC_MODEL_KEY = "llm/anthropic_model"
_VERTEX_API_KEY = "llm/vertex_api_key"
_VERTEX_MODEL_KEY = "llm/vertex_model"
_COMPATIBLE_BASE_URL_KEY = "llm/compatible_base_url"
_COMPATIBLE_BEARER_TOKEN_KEY = "llm/compatible_bearer_token"
_COMPATIBLE_MODEL_KEY = "llm/compatible_model"


class LlmProvider(StrEnum):
    """Supported LLM provider options (only one may be active)."""

    NONE = "none"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    VERTEX = "vertex"
    OPENAI_COMPATIBLE = "openai_compatible"


class SettingsBackend(Protocol):
    """Minimal interface required from a settings storage backend."""

    def value(self, key: str, default: Any = None) -> Any: ...

    def setValue(self, key: str, value: Any) -> None: ...

    def sync(self) -> None: ...


def _to_bool(value: Any) -> bool:
    """Normalize a stored value to bool (QSettings may round-trip bools as strings)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


class AppSettings:
    """Wraps a settings backend to persist user-configurable tool paths.

    Settings:
        use_external_ytdlp: When enabled, invoke the yt-dlp CLI binary via
            subprocess instead of the bundled yt-dlp Python library.
        ytdlp_path: Custom path to the yt-dlp executable. Only consulted
            when use_external_ytdlp is enabled; falls back to "yt-dlp" on
            PATH when left empty.
        ffmpeg_path: Custom path to the ffmpeg executable. Falls back to
            "ffmpeg" on PATH when left empty.
    """

    def __init__(self, backend: SettingsBackend | None = None):
        self._backend = backend or QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            _ORG_NAME,
            _APP_NAME,
        )

    @property
    def use_external_ytdlp(self) -> bool:
        return _to_bool(self._backend.value(_USE_EXTERNAL_KEY, False))

    @use_external_ytdlp.setter
    def use_external_ytdlp(self, enabled: bool) -> None:
        self._backend.setValue(_USE_EXTERNAL_KEY, bool(enabled))

    @property
    def ytdlp_path(self) -> str:
        return str(self._backend.value(_YTDLP_PATH_KEY, "") or "")

    @ytdlp_path.setter
    def ytdlp_path(self, path: str) -> None:
        self._backend.setValue(_YTDLP_PATH_KEY, (path or "").strip())

    @property
    def ffmpeg_path(self) -> str:
        return str(self._backend.value(_FFMPEG_PATH_KEY, "") or "")

    @ffmpeg_path.setter
    def ffmpeg_path(self, path: str) -> None:
        self._backend.setValue(_FFMPEG_PATH_KEY, (path or "").strip())

    def resolved_ytdlp_command(self) -> str:
        """Return the yt-dlp executable to invoke when running in external mode."""
        return self.ytdlp_path or "yt-dlp"

    def resolved_ffmpeg_command(self) -> str:
        """Return the ffmpeg executable to invoke."""
        return self.ffmpeg_path or "ffmpeg"

    @property
    def llm_provider(self) -> LlmProvider:
        raw = str(self._backend.value(_LLM_PROVIDER_KEY, LlmProvider.NONE) or LlmProvider.NONE)
        try:
            return LlmProvider(raw)
        except ValueError:
            return LlmProvider.NONE

    @llm_provider.setter
    def llm_provider(self, provider: LlmProvider | str) -> None:
        self._backend.setValue(_LLM_PROVIDER_KEY, str(provider))

    @property
    def openai_api_key(self) -> str:
        return str(self._backend.value(_OPENAI_API_KEY, "") or "")

    @openai_api_key.setter
    def openai_api_key(self, value: str) -> None:
        self._backend.setValue(_OPENAI_API_KEY, (value or "").strip())

    @property
    def openai_model(self) -> str:
        return str(self._backend.value(_OPENAI_MODEL_KEY, "") or "")

    @openai_model.setter
    def openai_model(self, value: str) -> None:
        self._backend.setValue(_OPENAI_MODEL_KEY, (value or "").strip())

    @property
    def anthropic_api_key(self) -> str:
        return str(self._backend.value(_ANTHROPIC_API_KEY, "") or "")

    @anthropic_api_key.setter
    def anthropic_api_key(self, value: str) -> None:
        self._backend.setValue(_ANTHROPIC_API_KEY, (value or "").strip())

    @property
    def anthropic_model(self) -> str:
        return str(self._backend.value(_ANTHROPIC_MODEL_KEY, "") or "")

    @anthropic_model.setter
    def anthropic_model(self, value: str) -> None:
        self._backend.setValue(_ANTHROPIC_MODEL_KEY, (value or "").strip())

    @property
    def vertex_api_key(self) -> str:
        return str(self._backend.value(_VERTEX_API_KEY, "") or "")

    @vertex_api_key.setter
    def vertex_api_key(self, value: str) -> None:
        self._backend.setValue(_VERTEX_API_KEY, (value or "").strip())

    @property
    def vertex_model(self) -> str:
        return str(self._backend.value(_VERTEX_MODEL_KEY, "") or "")

    @vertex_model.setter
    def vertex_model(self, value: str) -> None:
        self._backend.setValue(_VERTEX_MODEL_KEY, (value or "").strip())

    @property
    def compatible_base_url(self) -> str:
        return str(self._backend.value(_COMPATIBLE_BASE_URL_KEY, "") or "")

    @compatible_base_url.setter
    def compatible_base_url(self, value: str) -> None:
        self._backend.setValue(_COMPATIBLE_BASE_URL_KEY, (value or "").strip())

    @property
    def compatible_bearer_token(self) -> str:
        return str(self._backend.value(_COMPATIBLE_BEARER_TOKEN_KEY, "") or "")

    @compatible_bearer_token.setter
    def compatible_bearer_token(self, value: str) -> None:
        self._backend.setValue(_COMPATIBLE_BEARER_TOKEN_KEY, (value or "").strip())

    @property
    def compatible_model(self) -> str:
        return str(self._backend.value(_COMPATIBLE_MODEL_KEY, "") or "")

    @compatible_model.setter
    def compatible_model(self, value: str) -> None:
        self._backend.setValue(_COMPATIBLE_MODEL_KEY, (value or "").strip())

    def sync(self) -> None:
        """Flush settings to persistent storage."""
        self._backend.sync()


_settings_instance: AppSettings | None = None


def get_settings() -> AppSettings:
    """Return the process-wide AppSettings singleton, creating it on first use."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AppSettings()
    return _settings_instance


def reset_settings_cache() -> None:
    """Clear the cached singleton. Intended for use in tests."""
    global _settings_instance
    _settings_instance = None
