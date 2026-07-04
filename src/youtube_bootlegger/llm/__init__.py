"""LLM integration for AI-assisted tracklist setup."""

from .llm_api import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_COMPATIBLE_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
    LlmExtractionError,
    TracklistExtraction,
    build_litellm_kwargs,
    extract_tracklist_metadata,
    fallback_template,
    is_llm_configured,
    parse_extraction_response,
    resolve_litellm_model,
    validate_extraction,
)
from .chatgpt_lite import build_chatgpt_lite_url, launch_chatgpt_lite_assist
from .prompt import build_extraction_prompt, build_lite_prompt

__all__ = [
    "DEFAULT_ANTHROPIC_MODEL",
    "DEFAULT_COMPATIBLE_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_VERTEX_MODEL",
    "LlmExtractionError",
    "TracklistExtraction",
    "build_chatgpt_lite_url",
    "build_extraction_prompt",
    "build_lite_prompt",
    "build_litellm_kwargs",
    "launch_chatgpt_lite_assist",
    "extract_tracklist_metadata",
    "fallback_template",
    "is_llm_configured",
    "parse_extraction_response",
    "resolve_litellm_model",
    "validate_extraction",
]
