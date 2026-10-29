"""AI-assisted tracklist setup: ask the configured LLM for a parsing template."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from ..core.settings import AppSettings
from ..core.template_parser import DEFAULT_TEMPLATE, preview_parse, validate_template
from .client import complete_structured, parse_structured
from .config import endpoint_from_settings
from .http import LlmError, PostJson, post_json
from .prompt import SYSTEM_PROMPT, build_extraction_prompt
from .request_log import with_request_log

SCHEMA_NAME = "tracklist_extraction"


class TracklistExtraction(BaseModel):
    """Structured LLM response for tracklist analysis."""

    template: str = Field(description="Template string using Bootlegger placeholders.")
    artist_name: str = Field(description="Artist or band name for the performance.")
    album_name: str = Field(description="Album name, often derived from the video title.")


class LlmExtractionError(LlmError):
    """Raised when tracklist extraction fails."""


def extract_tracklist_metadata(
    settings: AppSettings,
    video_title: str,
    raw_tracklist: str,
    *,
    http_post: PostJson = post_json,
) -> TracklistExtraction:
    """Call the configured LLM to extract template and metadata.

    Args:
        settings: Application settings with LLM provider configuration.
        video_title: Title of the YouTube video.
        raw_tracklist: User-entered raw track list text.
        http_post: Optional override for the HTTP POST (for tests).

    Returns:
        Parsed extraction result.

    Raises:
        LlmExtractionError: On configuration, network, or parsing failures.
    """
    if not raw_tracklist.strip():
        raise LlmExtractionError("Track list is empty")
    if not video_title.strip():
        raise LlmExtractionError("Video title is required")

    try:
        result = complete_structured(
            endpoint_from_settings(settings),
            system=SYSTEM_PROMPT,
            user=build_extraction_prompt(video_title, raw_tracklist),
            output=TracklistExtraction,
            schema_name=SCHEMA_NAME,
            http_post=with_request_log(http_post, settings),
        )
    except LlmExtractionError:
        raise
    except LlmError as exc:
        raise LlmExtractionError(str(exc)) from exc

    return validate_extraction(_normalized(result), raw_tracklist)


def parse_extraction_response(content: str | Mapping[str, Any]) -> TracklistExtraction:
    """Parse and validate structured LLM output."""
    try:
        result = parse_structured(content, TracklistExtraction)
    except LlmError as exc:
        raise LlmExtractionError(str(exc)) from exc
    return _normalized(result)


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


def fallback_template() -> str:
    """Return the default template when LLM output is unavailable."""
    return DEFAULT_TEMPLATE


def _normalized(result: TracklistExtraction) -> TracklistExtraction:
    template = result.template.strip()
    if not template:
        raise LlmExtractionError("LLM returned an empty template")
    return TracklistExtraction(
        template=template,
        artist_name=result.artist_name.strip(),
        album_name=result.album_name.strip(),
    )
