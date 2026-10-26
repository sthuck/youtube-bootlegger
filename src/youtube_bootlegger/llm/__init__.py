"""LLM integration for AI-assisted tracklist setup."""

from .llm_api import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_COMPATIBLE_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_VERTEX_MODEL,
    LlmExtractionError,
    TracklistExtraction,
    build_chat_request,
    extract_tracklist_metadata,
    fallback_template,
    is_llm_configured,
    parse_extraction_response,
    resolve_model,
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
    "build_chat_request",
    "build_extraction_prompt",
    "build_lite_prompt",
    "launch_chatgpt_lite_assist",
    "extract_tracklist_metadata",
    "fallback_template",
    "is_llm_configured",
    "parse_extraction_response",
    "resolve_model",
    "validate_extraction",
]
