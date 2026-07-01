"""LLM API integration via litellm for tracklist extraction."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..core.settings import AppSettings, LlmProvider
from ..core.template_parser import DEFAULT_TEMPLATE, preview_parse, validate_template
from .prompt import SYSTEM_PROMPT, build_extraction_prompt

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_VERTEX_MODEL = "gemini-2.0-flash"
DEFAULT_COMPATIBLE_MODEL = "gpt-4o-mini"


class TracklistExtraction(BaseModel):
    """Structured LLM response for tracklist analysis."""

    template: str = Field(description="Template string using Bootlegger placeholders.")
    artist_name: str = Field(description="Artist or band name for the performance.")
    album_name: str = Field(description="Album name, often derived from the video title.")


class LlmExtractionError(Exception):
    """Raised when LLM extraction fails."""


def is_llm_configured(settings: AppSettings) -> bool:
    """Return True when the active LLM provider has the required credentials."""
    provider = settings.llm_provider
    if provider == LlmProvider.NONE:
        return False
    if provider == LlmProvider.OPENAI:
        return bool(settings.openai_api_key.strip())
    if provider == LlmProvider.ANTHROPIC:
        return bool(settings.anthropic_api_key.strip())
    if provider == LlmProvider.VERTEX:
        return bool(settings.vertex_api_key.strip())
    if provider == LlmProvider.OPENAI_COMPATIBLE:
        return bool(settings.compatible_base_url.strip())
    return False


def _resolve_gemini_model(model: str) -> str:
    """Return a litellm model id for Google AI Studio (API key) Gemini models."""
    resolved = model or DEFAULT_VERTEX_MODEL
    if resolved.startswith("gemini/"):
        return resolved
    if resolved.startswith("vertex_ai/"):
        resolved = resolved.split("/", 1)[1]
    return f"gemini/{resolved}"


def resolve_litellm_model(settings: AppSettings) -> str:
    """Return the litellm model identifier for the active provider."""
    provider = settings.llm_provider
    if provider == LlmProvider.OPENAI:
        return settings.openai_model or DEFAULT_OPENAI_MODEL
    if provider == LlmProvider.ANTHROPIC:
        model = settings.anthropic_model or DEFAULT_ANTHROPIC_MODEL
        return model if model.startswith("anthropic/") else f"anthropic/{model}"
    if provider == LlmProvider.VERTEX:
        return _resolve_gemini_model(settings.vertex_model)
    return settings.compatible_model or DEFAULT_COMPATIBLE_MODEL


def build_litellm_kwargs(settings: AppSettings) -> dict[str, Any]:
    """Build keyword arguments for litellm.completion from app settings."""
    provider = settings.llm_provider
    kwargs: dict[str, Any] = {"model": resolve_litellm_model(settings)}

    if provider == LlmProvider.OPENAI:
        kwargs["api_key"] = settings.openai_api_key.strip()
    elif provider == LlmProvider.ANTHROPIC:
        kwargs["api_key"] = settings.anthropic_api_key.strip()
    elif provider == LlmProvider.VERTEX:
        kwargs["api_key"] = settings.vertex_api_key.strip()
    elif provider == LlmProvider.OPENAI_COMPATIBLE:
        kwargs["api_base"] = settings.compatible_base_url.strip().rstrip("/")
        token = settings.compatible_bearer_token.strip()
        if token:
            kwargs["api_key"] = token
    else:
        raise LlmExtractionError("No LLM provider is configured")

    return kwargs


def parse_extraction_response(content: str | dict[str, Any]) -> TracklistExtraction:
    """Parse and validate structured LLM output."""
    if isinstance(content, dict):
        payload = content
    elif isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LlmExtractionError(f"LLM returned invalid JSON: {exc}") from exc
    else:
        raise LlmExtractionError(
            f"LLM returned unexpected response type: {type(content).__name__}"
        )

    try:
        result = TracklistExtraction.model_validate(payload)
    except ValidationError as exc:
        raise LlmExtractionError(f"LLM response failed validation: {exc}") from exc

    template = result.template.strip()
    if not template:
        raise LlmExtractionError("LLM returned an empty template")

    return TracklistExtraction(
        template=template,
        artist_name=result.artist_name.strip(),
        album_name=result.album_name.strip(),
    )


def validate_extraction(
    extraction: TracklistExtraction,
    raw_tracklist: str,
) -> TracklistExtraction:
    """Ensure the LLM template is valid and parses the user's track list."""
    template_validation = validate_template(extraction.template)
    if not template_validation.is_valid:
        raise LlmExtractionError(
            f"LLM returned invalid template: {template_validation.error}"
        )

    preview = preview_parse(raw_tracklist, extraction.template)
    if preview.total_lines == 0:
        raise LlmExtractionError("Track list has no parseable lines")

    if preview.error_count > 0:
        raise LlmExtractionError(
            "LLM template does not match the track list "
            f"({preview.error_count} of {preview.total_lines} lines failed to parse)"
        )

    return extraction


def extract_tracklist_metadata(
    settings: AppSettings,
    video_title: str,
    raw_tracklist: str,
    *,
    completion_fn=None,
) -> TracklistExtraction:
    """Call the configured LLM to extract template and metadata.

    Args:
        settings: Application settings with LLM provider configuration.
        video_title: Title of the YouTube video.
        raw_tracklist: User-entered raw track list text.
        completion_fn: Optional override for litellm.completion (for tests).

    Returns:
        Parsed extraction result.

    Raises:
        LlmExtractionError: On configuration, network, or parsing failures.
    """
    if not raw_tracklist.strip():
        raise LlmExtractionError("Track list is empty")
    if not video_title.strip():
        raise LlmExtractionError("Video title is required")

    if not is_llm_configured(settings):
        raise LlmExtractionError("LLM is not configured. Add API credentials in Settings.")

    if completion_fn is None:
        from litellm import completion

        completion_fn = completion

    prompt = build_extraction_prompt(video_title, raw_tracklist)
    kwargs = build_litellm_kwargs(settings)

    try:
        response = completion_fn(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format=TracklistExtraction,
            **kwargs,
        )
    except Exception as exc:
        raise LlmExtractionError(f"LLM request failed: {exc}") from exc

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise LlmExtractionError("LLM returned an unexpected response shape") from exc

    if content is None or content == "":
        raise LlmExtractionError("LLM returned an empty response")

    extraction = parse_extraction_response(content)
    return validate_extraction(extraction, raw_tracklist)


def fallback_template() -> str:
    """Return the default template when LLM output is unavailable."""
    return DEFAULT_TEMPLATE
