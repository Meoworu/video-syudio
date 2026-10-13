from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings


class GoogleVertexConfigError(ValueError):
    """Raised when ADC-based Vertex AI configuration is incomplete."""


@dataclass(frozen=True)
class GoogleVertexRuntime:
    project: str
    location: str
    credentials: Any


def load_vertex_runtime(settings: Settings) -> GoogleVertexRuntime:
    if not settings.google_cloud_project:
        raise GoogleVertexConfigError("未配置 GOOGLE_CLOUD_PROJECT")
    try:
        import google.auth
        from google.auth.exceptions import DefaultCredentialsError, GoogleAuthError

        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        if settings.google_application_credentials:
            credentials, _ = google.auth.load_credentials_from_file(
                str(settings.google_application_credentials), scopes=scopes
            )
        else:
            credentials, _ = google.auth.default(scopes=scopes)
    except (DefaultCredentialsError, GoogleAuthError, OSError, ValueError) as error:
        raise GoogleVertexConfigError(
            "未配置 Google ADC，请执行 `gcloud auth application-default login`，"
            "或设置 GOOGLE_APPLICATION_CREDENTIALS。"
        ) from error
    return GoogleVertexRuntime(
        project=settings.google_cloud_project,
        location=settings.google_cloud_location or "global",
        credentials=credentials,
    )


def build_vertex_client(settings: Settings, runtime: GoogleVertexRuntime | None = None) -> Any:
    runtime = runtime or load_vertex_runtime(settings)
    try:
        from google import genai
    except ImportError as error:  # pragma: no cover
        raise GoogleVertexConfigError("未安装 google-genai") from error
    return genai.Client(
        vertexai=True,
        credentials=runtime.credentials,
        project=runtime.project,
        location=runtime.location,
    )

