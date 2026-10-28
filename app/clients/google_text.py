from __future__ import annotations

import json
import time
from typing import Any

from google.genai import types

from app.clients.google_client import build_google_client, safe_google_error
from app.config import Settings


class GoogleTextError(RuntimeError):
    """Raised when Gemini does not return valid structured text."""


class GoogleTextClient:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = build_google_client(self.settings)
        return self._client

    def generate_json(self, prompt: str, *, images: list[tuple[bytes, str]] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.settings.google_text_max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.settings.google_text_model,
                    contents=prompt if not images else [
                        types.Part.from_text(text=prompt),
                        *(types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images),
                    ],
                    config={"response_mime_type": "application/json"},
                )
                value = json.loads(getattr(response, "text", "") or "")
                if not isinstance(value, dict):
                    raise GoogleTextError("Gemini 返回的内容不是 JSON 对象")
                return value
            except json.JSONDecodeError as error:
                last_error = GoogleTextError("Gemini 返回的内容不是有效 JSON")
                last_error.__cause__ = error
            except Exception as error:
                last_error = error
                if attempt >= self.settings.google_text_max_retries or not _is_transient(error):
                    raise GoogleTextError(f"Agent Platform 文本请求失败：{safe_google_error(error, self.settings)}") from None
            if attempt < self.settings.google_text_max_retries:
                time.sleep(self.settings.retry_backoff_seconds * (2 ** attempt))
        raise GoogleTextError(f"Agent Platform 文本请求重试耗尽：{safe_google_error(last_error, self.settings)}") from None


def _is_transient(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    if status is None:
        return isinstance(error, (TimeoutError, ConnectionError)) or error.__class__.__name__ in {"ServiceUnavailable", "ResourceExhausted", "DeadlineExceeded"}
    return int(status) in {408, 425, 429, 500, 502, 503, 504}

