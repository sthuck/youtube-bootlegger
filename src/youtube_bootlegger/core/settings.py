"""Persistent application settings for external tool configuration."""

from enum import StrEnum
from pathlib import Path
import sys
from typing import Any, Protocol

from PySide6.QtCore import QSettings

_ORG_NAME = "YouTubeBootlegger"
_APP_NAME = "YouTubeBootlegger"

_USE_EXTERNAL_KEY = "ytdlp/use_external"
_YTDLP_PATH_KEY = "ytdlp/path"
_COOKIES_FROM_BROWSER_KEY = "ytdlp/cookies_from_browser"
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
_AUTO_FIND_TRACKLIST_KEY = "llm/auto_find_tracklist"
_LOG_AI_REQUESTS_KEY = "llm/log_requests"
AI_REQUEST_LOG_NAME = "ai-requests.log"


class CookieBrowser(StrEnum):
    """Supported browsers for yt-dlp --cookies-from-browser."""

    NONE = ""
    FIREFOX = "firefox"
    CHROME = "chrome"
    BRAVE = "brave"
    EDGE = "edge"
    SAFARI = "safari"
    CHROMIUM = "chromium"
    OPERA = "opera"
    VIVALDI = "vivaldi"


_ALL_COOKIE_BROWSER_OPTIONS: tuple[tuple[str, CookieBrowser], ...] = (
    ("None (disabled)", CookieBrowser.NONE),
    ("Firefox", CookieBrowser.FIREFOX),
    ("Chrome", CookieBrowser.CHROME),
    ("Brave", CookieBrowser.BRAVE),
    ("Edge", CookieBrowser.EDGE),
    ("Safari", CookieBrowser.SAFARI),
    ("Chromium", CookieBrowser.CHROMIUM),
    ("Opera", CookieBrowser.OPERA),
    ("Vivaldi", CookieBrowser.VIVALDI),
)

COOKIE_BROWSER_OPTIONS: tuple[tuple[str, CookieBrowser], ...] = tuple(
    (label, browser)
    for label, browser in _ALL_COOKIE_BROWSER_OPTIONS
    if browser != CookieBrowser.SAFARI or sys.platform == "darwin"
)

COOKIE_BROWSER_LABELS: dict[CookieBrowser, str] = {
    browser: label for label, browser in _ALL_COOKIE_BROWSER_OPTIONS
}

COOKIE_BROWSER_TOOLTIP = (
    "Reads YouTube login cookies from the selected browser to access "
    "age-restricted videos. Note: on Windows, Chrome, Edge, and Brave lock "
    "their cookie database while running — close the browser first or use Firefox."
)


def _parse_cookie_browser(value: CookieBrowser | str | None) -> CookieBrowser:
    """Parse a stored or user-supplied cookie browser value."""
    raw = str(value or "").strip().lower()
    if not raw or raw == "none":
        return CookieBrowser.NONE
    try:
        return CookieBrowser(raw)
    except ValueError:
        return CookieBrowser.NONE


class LlmProvider(StrEnum):
    """Supported LLM provider options (only one may be active)."""

    NONE = "none"  # legacy; treated as CHATGPT_LITE when read from storage
    CHATGPT_LITE = "chatgpt_lite"
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
    def cookies_from_browser(self) -> CookieBrowser:
        return _parse_cookie_browser(self._backend.value(_COOKIES_FROM_BROWSER_KEY, ""))

    @cookies_from_browser.setter
    def cookies_from_browser(self, browser: CookieBrowser | str) -> None:
        self._backend.setValue(
            _COOKIES_FROM_BROWSER_KEY,
            _parse_cookie_browser(browser).value,
        )

    def ytdlp_cookie_options(self) -> dict[str, Any]:
        """Return yt-dlp Python API option dict for browser cookie extraction."""
        browser = self.cookies_from_browser
        if browser != CookieBrowser.NONE:
            return {"cookiesfrombrowser": (browser.value,)}
        return {}

    def ytdlp_cookie_cli_args(self) -> list[str]:
        """Return yt-dlp CLI arguments for browser cookie extraction."""
        browser = self.cookies_from_browser
        if browser != CookieBrowser.NONE:
            return ["--cookies-from-browser", browser.value]
        return []

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
        raw = str(
            self._backend.value(_LLM_PROVIDER_KEY, LlmProvider.CHATGPT_LITE)
            or LlmProvider.CHATGPT_LITE
        )
        if raw == LlmProvider.NONE:
            raw = LlmProvider.CHATGPT_LITE
        try:
            return LlmProvider(raw)
        except ValueError:
            return LlmProvider.CHATGPT_LITE

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

    @property
    def auto_find_tracklist(self) -> bool:
        """Run the AI track-list finder automatically when a video loads.

        Defaults to True. Only takes effect with an API model (not ChatGPT
        Lite); the "Find with AI" button works regardless of this setting.
        """
        return _to_bool(self._backend.value(_AUTO_FIND_TRACKLIST_KEY, True))

    @auto_find_tracklist.setter
    def auto_find_tracklist(self, enabled: bool) -> None:
        self._backend.setValue(_AUTO_FIND_TRACKLIST_KEY, bool(enabled))

    @property
    def log_ai_requests(self) -> bool:
        """Write each AI API request and response to ai_request_log_path.

        A debugging aid; defaults to False. API keys are never written.
        """
        return _to_bool(self._backend.value(_LOG_AI_REQUESTS_KEY, False))

    @log_ai_requests.setter
    def log_ai_requests(self, enabled: bool) -> None:
        self._backend.setValue(_LOG_AI_REQUESTS_KEY, bool(enabled))

    @property
    def ai_request_log_path(self) -> Path | None:
        """The AI request log, next to the settings file.

        None when the settings aren't stored in a file (e.g. in tests).
        """
        file_name = getattr(self._backend, "fileName", None)
        if not callable(file_name) or not file_name():
            return None
        return Path(file_name()).parent / AI_REQUEST_LOG_NAME

    def sync(self) -> None:
        """Flush settings to persistent storage."""
        self._backend.sync()


def _is_cookie_lock_line(line: str) -> bool:
    """Return True if a single output/error line indicates a locked cookie database."""
    if "extracted" in line and "cookies from" in line:
        return False
    return (
        ("could not copy" in line and "cookie" in line)
        or ("cookie" in line and "database is locked" in line)
        or ("cookie" in line and "permission" in line)
        or ("failed to decrypt" in line and "cookie" in line)
    )


def format_ytdlp_age_or_cookie_error(
    error_text: str,
    settings: AppSettings,
) -> str | None:
    """Return a user-friendly message for yt-dlp age-restriction or cookie lock errors."""
    lowered = (error_text or "").lower()
    browser = settings.cookies_from_browser
    browser_label = COOKIE_BROWSER_LABELS.get(browser, browser.value.title())

    if browser == CookieBrowser.SAFARI and "unsupported platform" in lowered:
        return (
            "Safari cookies are only supported on macOS. Select a different browser "
            "in Settings."
        )

    if browser != CookieBrowser.NONE and any(
        _is_cookie_lock_line(line) for line in lowered.splitlines()
    ):
        return (
            f"Could not read cookies from {browser_label} (the browser may be locking "
            "its cookie database). Close the browser and try again, or switch to Firefox "
            "in Settings."
        )

    if (
        "confirm your age" in lowered
        or "age-restricted" in lowered
        or "inappropriate for some users" in lowered
    ):
        if browser == CookieBrowser.NONE:
            return (
                "This video is age-restricted. Select a browser for cookies in Settings "
                "to access it."
            )
        return (
            f"This video is age-restricted. Make sure you are signed into YouTube in "
            f"{browser_label} (or choose a different browser in Settings)."
        )

    return None


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
