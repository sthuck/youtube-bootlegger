"""Map the app's LLM settings onto a generic :class:`LlmEndpoint`."""

from __future__ import annotations

from ..core.settings import AppSettings, LlmProvider
from .client import ApiProvider, LlmEndpoint
from .http import LlmError

DEFAULT_OPENAI_MODEL = "gpt-6-luna"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_VERTEX_MODEL = "gemini-3.8-flash"
DEFAULT_COMPATIBLE_MODEL = "gpt-4o-mini"

NOT_CONFIGURED_MESSAGE = "LLM is not configured. Add API credentials in Settings."


def is_llm_configured(settings: AppSettings) -> bool:
    """Return True when the active LLM provider has the required credentials."""
    match settings.llm_provider:
        case LlmProvider.CHATGPT_LITE:
            return True
        case LlmProvider.OPENAI:
            return bool(settings.openai_api_key.strip())
        case LlmProvider.ANTHROPIC:
            return bool(settings.anthropic_api_key.strip())
        case LlmProvider.VERTEX:
            return bool(settings.vertex_api_key.strip())
        case LlmProvider.OPENAI_COMPATIBLE:
            return bool(settings.compatible_base_url.strip())
        case _:
            return False


def resolve_model(settings: AppSettings) -> str:
    """Return the provider-native model id for the active provider."""
    match settings.llm_provider:
        case LlmProvider.OPENAI:
            return settings.openai_model or DEFAULT_OPENAI_MODEL
        case LlmProvider.ANTHROPIC:
            return _strip_known_prefix(
                settings.anthropic_model or DEFAULT_ANTHROPIC_MODEL,
                "anthropic/",
            )
        case LlmProvider.VERTEX:
            return _strip_known_prefix(
                settings.vertex_model or DEFAULT_VERTEX_MODEL,
                "gemini/",
                "vertex_ai/",
                "models/",
            )
        case _:
            return settings.compatible_model or DEFAULT_COMPATIBLE_MODEL


def endpoint_from_settings(settings: AppSettings) -> LlmEndpoint:
    """Return the API endpoint for the active provider.

    Raises:
        LlmError: When no API provider is configured (including ChatGPT Lite,
            which runs in the browser rather than through an API).
    """
    if not is_llm_configured(settings):
        raise LlmError(NOT_CONFIGURED_MESSAGE)

    model = resolve_model(settings)
    match settings.llm_provider:
        case LlmProvider.OPENAI:
            return LlmEndpoint(ApiProvider.OPENAI, model, settings.openai_api_key)
        case LlmProvider.ANTHROPIC:
            return LlmEndpoint(ApiProvider.ANTHROPIC, model, settings.anthropic_api_key)
        case LlmProvider.VERTEX:
            return LlmEndpoint(ApiProvider.GEMINI, model, settings.vertex_api_key)
        case LlmProvider.OPENAI_COMPATIBLE:
            return LlmEndpoint(
                ApiProvider.OPENAI_COMPATIBLE,
                model,
                settings.compatible_bearer_token,
                base_url=settings.compatible_base_url,
            )
        case LlmProvider.CHATGPT_LITE:
            raise LlmError(
                "Lite (ChatGPT) opens in your browser. Use the AI button instead of the API."
            )
        case _:
            raise LlmError(NOT_CONFIGURED_MESSAGE)


def _strip_known_prefix(model: str, *prefixes: str) -> str:
    resolved = model.strip()
    for prefix in prefixes:
        if resolved.startswith(prefix):
            return resolved[len(prefix) :]
    return resolved
