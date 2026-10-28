"""LLM integration for AI-assisted tracklist setup.

Layers, from generic to app-specific:
- ``http``: JSON POST transport and ``LlmError``.
- ``client``: provider-agnostic structured output (any Pydantic model).
- ``config``: maps ``AppSettings`` onto an ``LlmEndpoint``.
- ``tracklist``: the tracklist-extraction use case.
- ``track_finder``: finding a track list in a video's description, chapters, comments.
"""

from .chatgpt_lite import build_chatgpt_lite_url, launch_chatgpt_lite_assist
from .client import ApiProvider, LlmEndpoint, complete_structured
from .config import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_COMPATIBLE_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
    endpoint_from_settings,
    is_llm_configured,
    resolve_model,
)
from .http import LlmError
from .prompt import build_extraction_prompt, build_find_prompt, build_lite_prompt
from .track_finder import (
    FindOutcome,
    FoundTrack,
    TrackSource,
    TracklistFindError,
    TracklistFindResult,
    find_tracklist,
)
from .tracklist import (
    LlmExtractionError,
    TracklistExtraction,
    extract_tracklist_metadata,
    fallback_template,
    parse_extraction_response,
    validate_extraction,
)

__all__ = [
    "DEFAULT_ANTHROPIC_MODEL",
    "DEFAULT_COMPATIBLE_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_VERTEX_MODEL",
    "ApiProvider",
    "FindOutcome",
    "FoundTrack",
    "LlmEndpoint",
    "LlmError",
    "LlmExtractionError",
    "TrackSource",
    "TracklistExtraction",
    "TracklistFindError",
    "TracklistFindResult",
    "build_chatgpt_lite_url",
    "build_extraction_prompt",
    "build_find_prompt",
    "build_lite_prompt",
    "complete_structured",
    "endpoint_from_settings",
    "extract_tracklist_metadata",
    "fallback_template",
    "find_tracklist",
    "is_llm_configured",
    "launch_chatgpt_lite_assist",
    "parse_extraction_response",
    "resolve_model",
    "validate_extraction",
]
