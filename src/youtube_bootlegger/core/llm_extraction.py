"""LLM-powered extraction of tracklist template and metadata."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .settings import AppSettings, LlmProvider
from .template_parser import DEFAULT_TEMPLATE

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_VERTEX_MODEL = "gemini-2.0-flash"
DEFAULT_COMPATIBLE_MODEL = "gpt-4o-mini"

TEMPLATE_HELP = """\
YouTube Bootlegger parses a raw track list using a template string. Each line in the \
track list must match the template. Available placeholders:
- %songname% (required): song title
- %mm% (required): minutes
- %ss% (required): seconds as two digits
- %hh% (optional): hours
- %ignore:regex% (optional): regex segment to skip, e.g. %ignore:\\d+\\.%
Default template: %songname% - %mm%:%ss%
Examples:
- Opening Number - 0:00
- 1:23:45 - Long Song with template %hh%:%mm%:%ss% - %songname%
- [12:00] Opening Act with template [%mm%:%ss%] %songname%"""


class TracklistExtraction(BaseModel):
    """Structured LLM response for tracklist analysis."""

    template: str = Field(description="Template string using Bootlegger placeholders.")
    artist_name: str = Field(description="Artist or band name for the performance.")
    album_name: str = Field(description="Album name, often derived from the video title.")


class LlmExtractionError(Exception):
    """Raised when LLM extraction fails."""


def build_extraction_prompt(video_title: str, raw_tracklist: str) -> str:
    """Build the user prompt sent to the LLM."""
    return (
        f"{TEMPLATE_HELP}\n\n"
        f"Video title: {video_title}\n\n"
        "Raw track list (one song per line):\n"
        f"{raw_tracklist.strip()}\n\n"
        "Analyze the raw track list and video title. Return:\n"
        "1. template - the best matching template string\n"
        "2. artist_name - performer or band name\n"
        "3. album_name - album or release title (often based on the video title)"
    )


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


def resolve_litellm_model(settings: AppSettings) -> str:
    """Return the litellm model identifier for the active provider."""
    provider = settings.llm_provider
    if provider == LlmProvider.OPENAI:
        return settings.openai_model or DEFAULT_OPENAI_MODEL
    if provider == LlmProvider.ANTHROPIC:
        model = settings.anthropic_model or DEFAULT_ANTHROPIC_MODEL
        return model if model.startswith("anthropic/") else f"anthropic/{model}"
    if provider == LlmProvider.VERTEX:
        model = settings.vertex_model or DEFAULT_VERTEX_MODEL
        return model if model.startswith("vertex_ai/") else f"vertex_ai/{model}"
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


def parse_extraction_response(content: str) -> TracklistExtraction:
    """Parse and validate structured LLM output."""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmExtractionError(f"LLM returned invalid JSON: {exc}") from exc

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
                {
                    "role": "system",
                    "content": (
                        "You help users configure YouTube Bootlegger, a tool that splits "
                        "live performance audio using timestamped track lists. "
                        "Respond only with JSON matching the requested schema."
                    ),
                },
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

    if not content:
        raise LlmExtractionError("LLM returned an empty response")

    return parse_extraction_response(content)


def fallback_template() -> str:
    """Return the default template when LLM output is unavailable."""
    return DEFAULT_TEMPLATE
