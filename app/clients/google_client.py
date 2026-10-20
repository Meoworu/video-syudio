import re
from typing import Any

from app.config import Settings


class GoogleClientConfigError(ValueError):
    """Raised when Gemini Developer API configuration is incomplete."""


def build_google_client(settings: Settings) -> Any:
    api_key = settings.google_api_key_value
    if not api_key:
        raise GoogleClientConfigError("未配置 Google API Key，请在 .env 设置 GOOGLE_API_KEY")
    try:
        from google import genai
    except ImportError as error:  # pragma: no cover
        raise GoogleClientConfigError("未安装 google-genai") from error
    return genai.Client(
        vertexai=False,
        enterprise=False,
        api_key=api_key,
        http_options={"timeout": round(settings.google_http_timeout_seconds * 1000)},
    )


def safe_google_error(error: Exception, settings: Settings) -> str:
    message = str(error)
    for value in (settings.google_api_key, settings.gemini_api_key, settings.google_cloud_api_key):
        secret = value.get_secret_value().strip() if value else ""
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(x-goog-api-key|api[_-]?key|key)(\s*[=:]\s*)[^\s&,]+", r"\1\2[REDACTED]", message)
