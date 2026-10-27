"""Direct provider HTTP calls for tracklist extraction."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import requests
from pydantic import BaseModel, Field, ValidationError

from ..core.settings import AppSettings, LlmProvider
from ..core.template_parser import DEFAULT_TEMPLATE, preview_parse, validate_template
from .prompt import SYSTEM_PROMPT, build_extraction_prompt

DEFAULT_OPENAI_MODEL = "gpt-6-luna"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_VERTEX_MODEL = "gemini-3.8-flash"
DEFAULT_COMPATIBLE_MODEL = "gpt-4o-mini"

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
ANTHROPIC_VERSION = "2023-06-01"
# Reasoning models spend hidden thinking tokens from this same budget.
MAX_OUTPUT_TOKENS = 40_000
MAX_ERROR_DETAIL_CHARS = 500
REQUEST_TIMEOUT_SECONDS = 120

PostJson = Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]]


class TracklistExtraction(BaseModel):
    """Structured LLM response for tracklist analysis."""

    template: str = Field(description="Template string using Bootlegger placeholders.")
    artist_name: str = Field(description="Artist or band name for the performance.")
    album_name: str = Field(description="Album name, often derived from the video title.")


class LlmExtractionError(Exception):
    """Raised when LLM extraction fails."""


@dataclass(frozen=True)
class ChatRequest:
    """One JSON POST against a provider chat endpoint."""

    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    provider: LlmProvider


def is_llm_configured(settings: AppSettings) -> bool:
    """Return True when the active LLM provider has the required credentials."""
    provider = settings.llm_provider
    if provider == LlmProvider.CHATGPT_LITE:
        return True
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


def resolve_model(settings: AppSettings) -> str:
    """Return the provider-native model id for the active provider."""
    provider = settings.llm_provider
    if provider == LlmProvider.OPENAI:
        return settings.openai_model or DEFAULT_OPENAI_MODEL
    if provider == LlmProvider.ANTHROPIC:
        return _strip_known_prefix(
            settings.anthropic_model or DEFAULT_ANTHROPIC_MODEL,
            "anthropic/",
        )
    if provider == LlmProvider.VERTEX:
        return _strip_known_prefix(
            settings.vertex_model or DEFAULT_VERTEX_MODEL,
            "gemini/",
            "vertex_ai/",
            "models/",
        )
    return settings.compatible_model or DEFAULT_COMPATIBLE_MODEL


def extraction_json_schema() -> dict[str, Any]:
    """Return a strict object schema for TracklistExtraction."""
    schema = TracklistExtraction.model_json_schema()
    schema.pop("$schema", None)
    schema.pop("title", None)
    schema.pop("description", None)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)
        for prop in properties.values():
            if isinstance(prop, dict):
                prop.pop("title", None)
    schema["additionalProperties"] = False
    return schema


def build_chat_request(settings: AppSettings, system: str, user: str) -> ChatRequest:
    """Build the URL, auth headers, and JSON body for the active provider."""
    provider = settings.llm_provider
    model = resolve_model(settings)
    schema = extraction_json_schema()

    if provider == LlmProvider.OPENAI:
        return ChatRequest(
            url=OPENAI_CHAT_URL,
            headers=_bearer_headers(settings.openai_api_key),
            body=_openai_chat_body(
                model,
                system,
                user,
                schema,
                token_field="max_completion_tokens",
            ),
            provider=provider,
        )
    if provider == LlmProvider.ANTHROPIC:
        headers = _json_headers()
        headers["x-api-key"] = settings.anthropic_api_key.strip()
        headers["anthropic-version"] = ANTHROPIC_VERSION
        return ChatRequest(
            url=ANTHROPIC_MESSAGES_URL,
            headers=headers,
            body={
                "model": model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "output_config": {
                    "format": {"type": "json_schema", "schema": schema},
                },
            },
            provider=provider,
        )
    if provider == LlmProvider.VERTEX:
        headers = _json_headers()
        headers["x-goog-api-key"] = settings.vertex_api_key.strip()
        quoted_model = urllib.parse.quote(model, safe="")
        return ChatRequest(
            url=GEMINI_GENERATE_URL.format(model=quoted_model),
            headers=headers,
            body={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "maxOutputTokens": MAX_OUTPUT_TOKENS,
                },
            },
            provider=provider,
        )
    if provider == LlmProvider.OPENAI_COMPATIBLE:
        token = settings.compatible_bearer_token.strip()
        headers = _bearer_headers(token) if token else _json_headers()
        return ChatRequest(
            url=_compatible_chat_url(settings.compatible_base_url),
            headers=headers,
            body=_openai_chat_body(model, system, user, schema, token_field="max_tokens"),
            provider=provider,
        )
    raise LlmExtractionError("No LLM provider is configured")


def post_json(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST a JSON body and return the decoded JSON object."""
    try:
        # Redirects are refused: a POST would be replayed as a GET, and the
        # API key would be sent to wherever the redirect points.
        response = requests.post(
            url,
            json=payload,
            headers=dict(headers),
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise LlmExtractionError(f"LLM request failed: {exc}") from exc

    if response.is_redirect:
        location = response.headers.get("Location", "")
        raise LlmExtractionError(
            f"LLM request failed: HTTP {response.status_code} redirect to {location}. "
            "Check the base URL."
        )
    if not response.ok:
        detail = _error_message(response.content)
        message = f"LLM request failed: HTTP {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise LlmExtractionError(message)

    raw = response.content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LlmExtractionError("LLM returned an unexpected response shape") from exc
    if not isinstance(parsed, dict):
        raise LlmExtractionError("LLM returned an unexpected response shape")
    return parsed


def parse_extraction_response(content: str | dict[str, Any]) -> TracklistExtraction:
    """Parse and validate structured LLM output."""
    if isinstance(content, dict):
        payload = content
    elif isinstance(content, str):
        try:
            payload = json.loads(_unwrap_json_text(content))
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
    http_post: PostJson | None = None,
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

    if not is_llm_configured(settings):
        raise LlmExtractionError("LLM is not configured. Add API credentials in Settings.")

    if settings.llm_provider == LlmProvider.CHATGPT_LITE:
        raise LlmExtractionError(
            "Lite (ChatGPT) opens in your browser. Use the AI button instead of the API."
        )

    prompt = build_extraction_prompt(video_title, raw_tracklist)
    request = build_chat_request(settings, SYSTEM_PROMPT, prompt)
    send = http_post if http_post is not None else post_json

    try:
        body = send(request.url, request.headers, request.body)
    except LlmExtractionError:
        raise
    except Exception as exc:
        raise LlmExtractionError(f"LLM request failed: {exc}") from exc

    if not isinstance(body, Mapping):
        raise LlmExtractionError("LLM returned an unexpected response shape")

    content = response_text(request.provider, body)
    extraction = parse_extraction_response(content)
    return validate_extraction(extraction, raw_tracklist)


def fallback_template() -> str:
    """Return the default template when LLM output is unavailable."""
    return DEFAULT_TEMPLATE


def response_text(provider: LlmProvider, body: Mapping[str, Any]) -> str:
    """Pull the JSON text out of a provider response body."""
    error = _embedded_error(body)
    if error:
        raise LlmExtractionError(f"LLM request failed: {error}")

    if provider in (LlmProvider.OPENAI, LlmProvider.OPENAI_COMPATIBLE):
        text = _openai_text(body)
    elif provider == LlmProvider.ANTHROPIC:
        text = _anthropic_text(body)
    elif provider == LlmProvider.VERTEX:
        text = _gemini_text(body)
    else:
        raise LlmExtractionError("LLM returned an unexpected response shape")

    if text.strip() == "":
        raise LlmExtractionError("LLM returned an empty response")
    return text


def _strip_known_prefix(model: str, *prefixes: str) -> str:
    resolved = model.strip()
    for prefix in prefixes:
        if resolved.startswith(prefix):
            return resolved[len(prefix) :]
    return resolved


def _json_headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "Accept": "application/json"}


def _bearer_headers(api_key: str) -> dict[str, str]:
    headers = _json_headers()
    headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


def _openai_chat_body(
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    *,
    token_field: str,
) -> dict[str, Any]:
    # OpenAI chat now expects max_completion_tokens. Most compatible servers still want max_tokens.
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "tracklist_extraction",
                "strict": True,
                "schema": schema,
            },
        },
        token_field: MAX_OUTPUT_TOKENS,
    }


def _compatible_chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise LlmExtractionError("LLM is not configured. Add API credentials in Settings.")
    suffix = "/chat/completions"
    if base.endswith(suffix):
        return base
    return f"{base}{suffix}"


def _unwrap_json_text(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text
    newline = text.find("\n")
    if newline == -1:
        return text
    body = text[newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -3]
    return body.strip()


def _error_message(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        message = _embedded_error(payload)
        if message:
            return message
    text = raw.decode("utf-8", errors="replace").strip()
    if len(text) > MAX_ERROR_DETAIL_CHARS:
        return text[:MAX_ERROR_DETAIL_CHARS].rstrip() + "…"
    return text


def _embedded_error(body: Mapping[str, Any]) -> str | None:
    error = body.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    feedback = body.get("promptFeedback")
    if isinstance(feedback, dict):
        reason = feedback.get("blockReason")
        if isinstance(reason, str) and reason.strip():
            return f"blocked ({reason})"
    return None


def _openai_text(body: Mapping[str, Any]) -> str:
    try:
        choice = body["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmExtractionError("LLM returned an unexpected response shape") from exc
    if not isinstance(message, Mapping):
        raise LlmExtractionError("LLM returned an unexpected response shape")
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise LlmExtractionError(f"LLM request failed: {refusal.strip()}")
    _raise_if_stopped_early(choice.get("finish_reason"), ok=("stop",))
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _text_from_parts(content)
    return ""


def _anthropic_text(body: Mapping[str, Any]) -> str:
    content = body.get("content")
    if not isinstance(content, list):
        raise LlmExtractionError("LLM returned an unexpected response shape")
    _raise_if_stopped_early(body.get("stop_reason"), ok=("end_turn", "stop_sequence"))
    return _text_from_parts(content)


def _gemini_text(body: Mapping[str, Any]) -> str:
    try:
        candidate = body["candidates"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmExtractionError("LLM returned an unexpected response shape") from exc
    if not isinstance(candidate, Mapping):
        raise LlmExtractionError("LLM returned an unexpected response shape")
    # Blocked or truncated candidates often carry no content at all, so check first.
    _raise_if_stopped_early(candidate.get("finishReason"), ok=("STOP",))
    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, Mapping) else None
    if not isinstance(parts, list):
        raise LlmExtractionError("LLM returned an unexpected response shape")
    return _text_from_parts(parts)


_TRUNCATED_REASONS = frozenset({"length", "max_tokens", "MAX_TOKENS"})


def _raise_if_stopped_early(reason: Any, *, ok: tuple[str, ...]) -> None:
    """Raise when the provider reports it stopped for anything but a normal finish."""
    if not isinstance(reason, str) or not reason or reason in ok:
        return
    if reason in _TRUNCATED_REASONS:
        raise LlmExtractionError(
            f"LLM response was cut off at the output token limit ({reason})"
        )
    raise LlmExtractionError(f"LLM stopped before finishing ({reason})")


def _text_from_parts(parts: list[Any]) -> str:
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, str):
            chunks.append(part)
        elif isinstance(part, Mapping) and isinstance(part.get("text"), str):
            chunks.append(part["text"])
    return "".join(chunks)
