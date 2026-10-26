import re
from typing import Any

from app.config import Settings


class GoogleClientConfigError(ValueError):
    """Raised when Agent Platform authentication configuration is incomplete."""


def google_video_oauth_available() -> bool:
    try:
        import google.auth
        _credentials, _project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except Exception:
        return False
    return True


def build_google_video_client(settings: Settings, *, timeout_seconds: float | None = None, max_http_attempts: int | None = None) -> Any:
    if not settings.google_cloud_project:
        raise GoogleClientConfigError("未配置 GOOGLE_CLOUD_PROJECT，请填写关联 Cloud 赠金的项目 ID")
    if settings.google_omni_model != "gemini-omni-1.1-flash-preview":
        raise GoogleClientConfigError("当前视频客户端仅支持 gemini-omni-1.1-flash-preview；请更新 GOOGLE_OMNI_MODEL")
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError
        from google import genai
    except ImportError as error:  # pragma: no cover
        raise GoogleClientConfigError("未安装 Google Gen AI SDK 或 google-auth") from error
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except DefaultCredentialsError as error:
        raise GoogleClientConfigError(
            "未找到 Google Cloud OAuth 凭据；本机请先执行 gcloud auth application-default login"
        ) from error
    http_options = {"timeout": round((timeout_seconds or settings.google_http_timeout_seconds) * 1000)}
    if max_http_attempts is not None:
        http_options["retry_options"] = {"attempts": max_http_attempts}
    return genai.Client(
        enterprise=True,
        project=settings.google_cloud_project,
        location="global",
        credentials=credentials,
        http_options=http_options,
    )


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
    for value in (settings.google_api_key, settings.gemini_api_key, settings.google_cloud_api_key):
        secret = value.get_secret_value().strip() if value else ""
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return re.sub(r"(?i)(x-goog-api-key|api[_-]?key|key)(\s*[=:]\s*)[^\s&,]+", r"\1\2[REDACTED]", message)
