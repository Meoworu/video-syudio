import re
from typing import Any

from app.config import Settings


class GoogleClientConfigError(ValueError):
    """Raised when Agent Platform authentication configuration is incomplete."""


def build_google_video_client(settings: Settings, *, timeout_seconds: float | None = None, max_http_attempts: int | None = None) -> Any:
    api_key = settings.google_video_api_key_value
    if not api_key:
        raise GoogleClientConfigError("未配置 GOOGLE_VIDEO_API_KEY，请在 .env 设置 Gemini API Key（仅用于视频生成）")
    if settings.google_omni_model != "gemini-omni-1.1-flash":
        raise GoogleClientConfigError("当前视频客户端仅支持 gemini-omni-1.1-flash；请更新 GOOGLE_OMNI_MODEL")
    try:
        from google import genai
    except ImportError as error:  # pragma: no cover
        raise GoogleClientConfigError("未安装 google-genai") from error
    http_options = {"timeout": round((timeout_seconds or settings.google_http_timeout_seconds) * 1000)}
    if max_http_attempts is not None:
        http_options["retry_options"] = {"attempts": max_http_attempts}
    return genai.Client(enterprise=False, vertexai=False, api_key=api_key, http_options=http_options)


def build_google_client(settings: Settings, *, timeout_seconds: float | None = None, max_http_attempts: int | None = None) -> Any:
    api_key = settings.google_api_key_value
    if not api_key:
        raise GoogleClientConfigError("未配置 Google API Key，请在 .env 设置 GOOGLE_API_KEY")
    if not settings.google_cloud_project:
        raise GoogleClientConfigError("未配置 GOOGLE_CLOUD_PROJECT，请填写绑定 Google Cloud 试用结算账号的项目 ID")
    try:
        from google import genai
    except ImportError as error:  # pragma: no cover
        raise GoogleClientConfigError("未安装 google-genai") from error
    http_options = {"timeout": round((timeout_seconds or settings.google_http_timeout_seconds) * 1000)}
    if max_http_attempts is not None:
        http_options["retry_options"] = {"attempts": max_http_attempts}
    return genai.Client(
        enterprise=True,
        project=settings.google_cloud_project,
        location="global",
        api_key=api_key,
        http_options=http_options,
    )


def safe_google_error(error: Exception, settings: Settings) -> str:
    message = str(error)
    for value in (settings.google_api_key, settings.gemini_api_key, settings.google_cloud_api_key, settings.google_video_api_key):
        secret = value.get_secret_value().strip() if value else ""
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(x-goog-api-key|api[_-]?key|key)(\s*[=:]\s*)[^\s&,]+", r"\1\2[REDACTED]", message)
