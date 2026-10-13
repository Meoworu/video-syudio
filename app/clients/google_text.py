from __future__ import annotations

import json
import time
from typing import Any

from app.clients.google_vertex import build_vertex_client
from app.config import Settings


class GoogleTextError(RuntimeError):
    """Raised when Vertex AI does not return valid structured text."""


class GoogleTextClient:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = build_vertex_client(self.settings)
        return self._client

    def generate_json(self, prompt: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.settings.google_text_max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.settings.google_text_model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                value = json.loads(getattr(response, "text", "") or "")
                if not isinstance(value, dict):
                    raise GoogleTextError("Vertex AI 返回的内容不是 JSON 对象")
                return value
            except json.JSONDecodeError as error:
                last_error = GoogleTextError("Vertex AI 返回的内容不是有效 JSON")
                last_error.__cause__ = error
            except Exception as error:
                last_error = error
                if attempt >= self.settings.google_text_max_retries or not _is_transient(error):
                    raise
            if attempt < self.settings.google_text_max_retries:
                time.sleep(self.settings.retry_backoff_seconds * (2 ** attempt))
        raise GoogleTextError(f"Vertex AI 文本请求重试耗尽：{last_error}") from last_error


def _is_transient(error: Exception) -> bool:
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    if status is None:
        return isinstance(error, (TimeoutError, ConnectionError)) or error.__class__.__name__ in {"ServiceUnavailable", "ResourceExhausted", "DeadlineExceeded"}
    return int(status) in {408, 425, 429, 500, 502, 503, 504}

