"""JSON-over-HTTPS transport shared by all LLM providers."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

import requests

REQUEST_TIMEOUT_SECONDS = 120
MAX_ERROR_DETAIL_CHARS = 500

JsonObject = dict[str, Any]
PostJson = Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]]


class LlmError(Exception):
    """Raised when an LLM request fails or returns something unusable."""


def post_json(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> JsonObject:
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
        raise LlmError(f"LLM request failed: {exc}") from exc

    if response.is_redirect:
        location = response.headers.get("Location", "")
        raise LlmError(
            f"LLM request failed: HTTP {response.status_code} redirect to {location}. "
            "Check the base URL."
        )
    if not response.ok:
        detail = error_message(response.content)
        message = f"LLM request failed: HTTP {response.status_code}"
        if detail:
            message = f"{message}: {detail}"
        raise LlmError(message)

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise LlmError("LLM returned an unexpected response shape") from exc
    if not isinstance(parsed, dict):
        raise LlmError("LLM returned an unexpected response shape")
    return parsed


def error_message(raw: bytes) -> str:
    """Return a short, human-readable message from an error response body."""
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        message = embedded_error(payload)
        if message:
            return message
    text = raw.decode("utf-8", errors="replace").strip()
    if len(text) > MAX_ERROR_DETAIL_CHARS:
        return text[:MAX_ERROR_DETAIL_CHARS].rstrip() + "…"
    return text


def embedded_error(body: Mapping[str, Any]) -> str | None:
    """Return the error a provider reported inside a JSON body, if any."""
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
