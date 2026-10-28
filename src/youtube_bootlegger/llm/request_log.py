"""Optional debug log of AI API requests and responses.

When Settings → "Log AI requests" is on, every call made through an
``http_post`` wrapped by with_request_log is appended to the settings
folder's ai-requests.log as a readable JSON entry. Credentials are redacted.
Logging problems never affect the request itself.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.settings import AppSettings
from .http import PostJson

# Start a fresh file past this size, keeping one previous file as .1.
MAX_LOG_BYTES = 5 * 1024 * 1024
REDACTED = "<redacted>"
_SECRET_HEADER_WORDS = ("authorization", "key", "token")

_lock = threading.Lock()


def with_request_log(http_post: PostJson, settings: AppSettings) -> PostJson:
    """Return ``http_post``, logging each call if the setting is on."""
    path = settings.ai_request_log_path
    if not settings.log_ai_requests or path is None:
        return http_post

    def logged_post(
        url: str, headers: Mapping[str, str], payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        started = time.monotonic()
        try:
            body = http_post(url, headers, payload)
        except Exception as exc:
            _append(path, _entry(url, headers, payload, started, error=str(exc)))
            raise
        _append(path, _entry(url, headers, payload, started, response=body))
        return body

    return logged_post


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Copy headers, hiding any that carry credentials."""
    return {
        name: REDACTED if any(word in name.lower() for word in _SECRET_HEADER_WORDS) else value
        for name, value in headers.items()
    }


def _entry(url, headers, payload, started, *, response=None, error=None) -> dict[str, Any]:
    return {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "duration_seconds": round(time.monotonic() - started, 2),
        "url": url,
        "headers": redact_headers(headers),
        "request": payload,
        "response": response,
        "error": error,
    }


def _append(path: Path, entry: Mapping[str, Any]) -> None:
    text = json.dumps(entry, ensure_ascii=False, indent=2, default=str) + "\n\n"
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
                path.replace(path.with_name(path.name + ".1"))
            with path.open("a", encoding="utf-8") as log:
                log.write(text)
    except OSError:
        pass  # A debug log must never break the AI request.
