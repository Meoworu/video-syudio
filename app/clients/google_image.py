from __future__ import annotations

from typing import Any

from app.clients.google_client import build_google_client, safe_google_error
from app.config import Settings


class GoogleImageError(RuntimeError):
    """Raised when Agent Platform does not return a usable image."""


class GoogleImageClient:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = build_google_client(self.settings, timeout_seconds=self.settings.google_image_timeout_seconds, max_http_attempts=1)
        return self._client

    def generate(self, prompt: str, references: list[tuple[bytes, str, str]], aspect_ratio: str) -> tuple[bytes, str]:
        try:
            from google.genai import types

            contents = [types.Part.from_text(text=prompt)]
            for data, mime_type, label in references:
                contents.append(types.Part.from_text(text=f"Reference image: {label}"))
                contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))
            response = self.client.models.generate_content(
                model=self.settings.google_image_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=[types.Modality.TEXT, types.Modality.IMAGE],
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size=self.settings.google_image_resolution),
                ),
            )
            for candidate in getattr(response, "candidates", None) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None) if inline else None
                    if data:
                        return bytes(data), getattr(inline, "mime_type", "image/png") or "image/png"
            raise GoogleImageError("图片模型没有返回可用图片")
        except GoogleImageError:
            raise
        except Exception as error:
            raise GoogleImageError(f"Agent Platform 图片请求失败：{safe_google_error(error, self.settings)}") from None
