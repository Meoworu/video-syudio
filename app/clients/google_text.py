from __future__ import annotations

import json
from typing import Any

from app.clients.google_vertex import build_vertex_client
from app.config import Settings


class GoogleTextError(RuntimeError):
    """Raised when Vertex AI does not return valid structured text."""


class GoogleTextClient:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client or build_vertex_client(settings)

    def generate_json(self, prompt: str) -> dict[str, Any]:
        response = self.client.models.generate_content(
            model=self.settings.google_text_model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        try:
            value = json.loads(getattr(response, "text", "") or "")
        except json.JSONDecodeError as error:
            raise GoogleTextError("Vertex AI 返回的内容不是有效 JSON") from error
        if not isinstance(value, dict):
            raise GoogleTextError("Vertex AI 返回的内容不是 JSON 对象")
        return value

