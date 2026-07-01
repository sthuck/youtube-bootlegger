"""Persistent application settings for external tool configuration."""

from typing import Any, Protocol

from PySide6.QtCore import QSettings

_ORG_NAME = "YouTubeBootlegger"
_APP_NAME = "YouTubeBootlegger"

_USE_EXTERNAL_KEY = "ytdlp/use_external"
_YTDLP_PATH_KEY = "ytdlp/path"
_FFMPEG_PATH_KEY = "ffmpeg/path"


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
