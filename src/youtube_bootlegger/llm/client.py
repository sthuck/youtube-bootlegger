"""Provider-agnostic structured-output calls to chat LLM APIs.

Nothing here knows about tracklists: callers pass a Pydantic model and get a
validated instance of it back.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .http import JsonObject, LlmError, PostJson, embedded_error, post_json

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
GEMINI_GENERATE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
ANTHROPIC_VERSION = "2023-06-01"
# Reasoning models spend hidden thinking tokens from this same budget.
MAX_OUTPUT_TOKENS = 40_000

T = TypeVar("T", bound=BaseModel)


class ApiProvider(StrEnum):
    """Wire protocol spoken by an LLM endpoint."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass(frozen=True)
class LlmEndpoint:
    """Everything needed to reach one model."""

    provider: ApiProvider
    model: str
    api_key: str = ""
    # Only used by OPENAI_COMPATIBLE; the other providers have fixed URLs.
    base_url: str = ""


@dataclass(frozen=True)
class ChatRequest:
    """One JSON POST against a provider chat endpoint."""

    url: str
    headers: dict[str, str]
    body: JsonObject


@dataclass(frozen=True)
class OutputSchema:
    """A named strict JSON schema the model must answer with."""

    name: str
    schema: JsonObject

    @classmethod
    def from_model(cls, name: str, model: type[BaseModel]) -> OutputSchema:
        return cls(name=name, schema=strict_json_schema(model))


def complete_structured(
    endpoint: LlmEndpoint,
    *,
    system: str,
    user: str,
    output: type[T],
    schema_name: str,
    http_post: PostJson = post_json,
) -> T:
    """Ask the model for JSON matching ``output`` and return it validated.

    Raises:
        LlmError: On network, provider, or parsing failures.
    """
    request = build_chat_request(
        endpoint,
        system=system,
        user=user,
        output_schema=OutputSchema.from_model(schema_name, output),
    )
    try:
        body = http_post(request.url, request.headers, request.body)
    except LlmError:
        raise
    except Exception as exc:
        raise LlmError(f"LLM request failed: {exc}") from exc

    return parse_structured(response_text(endpoint.provider, body), output)


def strict_json_schema(model: type[BaseModel]) -> JsonObject:
    """Return a strict object schema (all fields required, no extras) for ``model``.

    Nested models are inlined rather than referenced through ``$defs``, since
    providers differ in ``$ref`` support, and every object is made strict.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})
    for key in ("$schema", "title", "description"):
        schema.pop(key, None)
    return _strict_node(schema, defs)


def _strict_node(node: Any, defs: Mapping[str, Any]) -> Any:
    if isinstance(node, list):
        return [_strict_node(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        resolved = {key: value for key, value in defs[ref.removeprefix("#/$defs/")].items()
                    if key not in ("title", "description")}
        return _strict_node(resolved, defs)
    strict = {key: _strict_node(value, defs) for key, value in node.items()
              if key not in ("title", "properties")}
    properties = node.get("properties")
    if isinstance(properties, dict):
        # Keys here are field names (a field may be called "title"), not keywords.
        strict["properties"] = {name: _strict_node(prop, defs) for name, prop in properties.items()}
        strict["required"] = list(properties)
        strict["additionalProperties"] = False
    return strict


def build_chat_request(
    endpoint: LlmEndpoint,
    *,
    system: str,
    user: str,
    output_schema: OutputSchema,
) -> ChatRequest:
    """Build the URL, auth headers, and JSON body for ``endpoint``."""
    match endpoint.provider:
        case ApiProvider.OPENAI:
            return ChatRequest(
                url=OPENAI_CHAT_URL,
                headers=_bearer_headers(endpoint.api_key),
                body=_openai_chat_body(
                    endpoint.model,
                    system,
                    user,
                    output_schema,
                    token_field="max_completion_tokens",
                ),
            )
        case ApiProvider.ANTHROPIC:
            return _anthropic_request(endpoint, system, user, output_schema)
        case ApiProvider.GEMINI:
            return _gemini_request(endpoint, system, user, output_schema)
        case ApiProvider.OPENAI_COMPATIBLE:
            token = endpoint.api_key.strip()
            return ChatRequest(
                url=_compatible_chat_url(endpoint.base_url),
                headers=_bearer_headers(token) if token else _json_headers(),
                # Most compatible servers still want max_tokens.
                body=_openai_chat_body(
                    endpoint.model, system, user, output_schema, token_field="max_tokens"
                ),
            )


def response_text(provider: ApiProvider, body: Mapping[str, Any]) -> str:
    """Pull the model's text answer out of a provider response body."""
    error = embedded_error(body)
    if error:
        raise LlmError(f"LLM request failed: {error}")

    match provider:
        case ApiProvider.OPENAI | ApiProvider.OPENAI_COMPATIBLE:
            text = _openai_text(_envelope(_OpenAiResponse, body))
        case ApiProvider.ANTHROPIC:
            text = _anthropic_text(_envelope(_AnthropicResponse, body))
        case ApiProvider.GEMINI:
            text = _gemini_text(_envelope(_GeminiResponse, body))

    if text.strip() == "":
        raise LlmError("LLM returned an empty response")
    return text


def parse_structured(content: str | Mapping[str, Any], output: type[T]) -> T:
    """Decode model output (JSON text, optionally fenced, or a dict) into ``output``."""
    if isinstance(content, str):
        try:
            payload = json.loads(_unwrap_json_text(content))
        except json.JSONDecodeError as exc:
            raise LlmError(f"LLM returned invalid JSON: {exc}") from exc
    else:
        payload = content
    try:
        return output.model_validate(payload)
    except ValidationError as exc:
        raise LlmError(f"LLM response failed validation: {exc}") from exc


# --- requests -----------------------------------------------------------------


def _json_headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "Accept": "application/json"}


def _bearer_headers(api_key: str) -> dict[str, str]:
    return {**_json_headers(), "Authorization": f"Bearer {api_key.strip()}"}


def _openai_chat_body(
    model: str,
    system: str,
    user: str,
    output_schema: OutputSchema,
    *,
    token_field: str,
) -> JsonObject:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": output_schema.name,
                "strict": True,
                "schema": output_schema.schema,
            },
        },
        token_field: MAX_OUTPUT_TOKENS,
    }


def _anthropic_request(
    endpoint: LlmEndpoint, system: str, user: str, output_schema: OutputSchema
) -> ChatRequest:
    return ChatRequest(
        url=ANTHROPIC_MESSAGES_URL,
        headers={
            **_json_headers(),
            "x-api-key": endpoint.api_key.strip(),
            "anthropic-version": ANTHROPIC_VERSION,
        },
        body={
            "model": endpoint.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "format": {"type": "json_schema", "schema": output_schema.schema},
            },
        },
    )


def _gemini_request(
    endpoint: LlmEndpoint, system: str, user: str, output_schema: OutputSchema
) -> ChatRequest:
    quoted_model = urllib.parse.quote(endpoint.model, safe="")
    return ChatRequest(
        url=GEMINI_GENERATE_URL.format(model=quoted_model),
        headers={**_json_headers(), "x-goog-api-key": endpoint.api_key.strip()},
        body={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": output_schema.schema,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        },
    )


def _compatible_chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise LlmError("LLM is not configured. Add API credentials in Settings.")
    suffix = "/chat/completions"
    if base.endswith(suffix):
        return base
    return f"{base}{suffix}"


# --- responses ----------------------------------------------------------------


class _Envelope(BaseModel):
    """Lenient base for provider responses: only the fields we read are declared."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class _TextPart(_Envelope):
    text: str | None = None


class _OpenAiMessage(_Envelope):
    content: str | list[_TextPart] | None = None
    refusal: str | None = None


class _OpenAiChoice(_Envelope):
    message: _OpenAiMessage
    finish_reason: str | None = None


class _OpenAiResponse(_Envelope):
    choices: list[_OpenAiChoice] = Field(min_length=1)


class _AnthropicResponse(_Envelope):
    content: list[_TextPart]
    stop_reason: str | None = None


class _GeminiContent(_Envelope):
    parts: list[_TextPart] = Field(default_factory=list)


class _GeminiCandidate(_Envelope):
    # Blocked or truncated candidates often carry no content at all.
    content: _GeminiContent | None = None
    finish_reason: str | None = Field(default=None, alias="finishReason")


class _GeminiResponse(_Envelope):
    candidates: list[_GeminiCandidate] = Field(min_length=1)


E = TypeVar("E", bound=_Envelope)


def _envelope(model: type[E], body: Mapping[str, Any]) -> E:
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise LlmError("LLM returned an unexpected response shape") from exc


def _openai_text(response: _OpenAiResponse) -> str:
    choice = response.choices[0]
    refusal = (choice.message.refusal or "").strip()
    if refusal:
        raise LlmError(f"LLM request failed: {refusal}")
    _raise_if_stopped_early(choice.finish_reason, ok=("stop",))
    content = choice.message.content
    if isinstance(content, list):
        return _join_parts(content)
    return content or ""


def _anthropic_text(response: _AnthropicResponse) -> str:
    _raise_if_stopped_early(response.stop_reason, ok=("end_turn", "stop_sequence"))
    return _join_parts(response.content)


def _gemini_text(response: _GeminiResponse) -> str:
    candidate = response.candidates[0]
    _raise_if_stopped_early(candidate.finish_reason, ok=("STOP",))
    if candidate.content is None:
        raise LlmError("LLM returned an unexpected response shape")
    return _join_parts(candidate.content.parts)


def _join_parts(parts: list[_TextPart]) -> str:
    return "".join(part.text for part in parts if part.text is not None)


_TRUNCATED_REASONS = frozenset({"length", "max_tokens", "MAX_TOKENS"})


def _raise_if_stopped_early(reason: str | None, *, ok: tuple[str, ...]) -> None:
    """Raise when the provider reports it stopped for anything but a normal finish."""
    if not reason or reason in ok:
        return
    if reason in _TRUNCATED_REASONS:
        raise LlmError(f"LLM response was cut off at the output token limit ({reason})")
    raise LlmError(f"LLM stopped before finishing ({reason})")


def _unwrap_json_text(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text
    newline = text.find("\n")
    if newline == -1:
        return text
    body = text[newline + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()
