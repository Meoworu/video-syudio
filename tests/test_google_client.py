import pytest
import httpx
import json
import google.auth
from google.oauth2.credentials import Credentials
from google import genai

from app.clients.google_client import GoogleClientConfigError, build_google_client, build_google_video_client, safe_google_error
from app.config import Settings
from app.clients.google_omni_video import GoogleOmniVideoClient


def test_google_client_requires_api_key() -> None:
    with pytest.raises(GoogleClientConfigError, match="GOOGLE_API_KEY"):
        build_google_client(Settings(_env_file=None))


def test_google_video_client_requires_cloud_project() -> None:
    settings = Settings(_env_file=None)
    with pytest.raises(GoogleClientConfigError, match="GOOGLE_CLOUD_PROJECT"):
        build_google_video_client(settings)


def test_google_video_client_uses_adc_and_agent_platform(monkeypatch) -> None:
    captured = {}
    credentials = object()

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(genai, "Client", fake_client)
    monkeypatch.setattr("google.auth.default", lambda **kwargs: (credentials, "cloud-project"))
    settings = Settings(_env_file=None, GOOGLE_CLOUD_PROJECT="cloud-project")

    build_google_video_client(settings, max_http_attempts=1)

    assert captured == {
        "enterprise": True,
        "project": "cloud-project",
        "location": "global",
        "credentials": credentials,
        "http_options": {"timeout": 120_000, "retry_options": {"attempts": 1}},
    }


def test_google_video_client_rejects_non_agent_platform_model(monkeypatch) -> None:
    monkeypatch.setattr("google.auth.default", lambda **kwargs: (object(), "cloud-project"))
    settings = Settings(_env_file=None, GOOGLE_CLOUD_PROJECT="cloud-project", GOOGLE_OMNI_MODEL="gemini-omni-flash-preview")
    with pytest.raises(GoogleClientConfigError, match="gemini-omni-1.1-flash-preview"):
        build_google_video_client(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("GOOGLE_API_KEY", "primary"),
        ("GEMINI_API_KEY", "gemini-alias"),
        ("GOOGLE_CLOUD_API_KEY", "legacy-alias"),
    ],
)
def test_google_client_accepts_key_names_without_vertex_credentials(monkeypatch, field, value) -> None:
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(genai, "Client", fake_client)
    monkeypatch.setattr("google.auth.default", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ADC used")))
    settings = Settings(_env_file=None, GOOGLE_CLOUD_PROJECT="trial-project", **{field: value})

    build_google_client(settings)

    assert captured == {
        "enterprise": True,
        "project": "trial-project",
        "location": "global",
        "api_key": value,
        "http_options": {"timeout": 120_000},
    }


def test_google_api_key_precedence_skips_blank_values() -> None:
    settings = Settings(_env_file=None, GOOGLE_API_KEY="  ", GEMINI_API_KEY="secondary", GOOGLE_CLOUD_API_KEY="legacy")
    assert settings.google_api_key_value == "secondary"
    assert "secondary" not in repr(settings)


def test_google_api_key_is_removed_from_provider_errors() -> None:
    settings = Settings(_env_file=None, GOOGLE_API_KEY="  secret-key  ")
    message = safe_google_error(RuntimeError("request failed: key=secret-key"), settings)
    assert "secret-key" not in message
    assert "[REDACTED]" in message


def test_google_client_requires_billing_project() -> None:
    with pytest.raises(GoogleClientConfigError, match="GOOGLE_CLOUD_PROJECT"):
        build_google_client(Settings(_env_file=None, GOOGLE_API_KEY="test-key"))


def test_google_clients_route_text_and_video_to_agent_platform_with_cloud_auth(monkeypatch, tmp_path) -> None:
    requests = []

    def send(client, request, **kwargs):
        requests.append(request)
        payload = {"id": "job-1", "status": "completed"} if "/interactions" in request.url.path else {
            "candidates": [{"content": {"parts": [{"text": "{}"}], "role": "model"}}]
        }
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr("google.auth.default", lambda **kwargs: (Credentials(token="offline-token"), "trial-project"))
    settings = Settings(_env_file=None, GOOGLE_API_KEY="cloud-key", GOOGLE_CLOUD_PROJECT="trial-project")
    with build_google_client(settings) as cloud_client, build_google_video_client(settings) as video_client:
        cloud_client.models.generate_content(model="gemini-3.6-flash", contents="test")
        frame = tmp_path / "frame.png"
        frame.write_bytes(b"offline-image")
        job = GoogleOmniVideoClient(settings, client=video_client).create_interaction(
            prompt="offline", first_frame=frame, last_frame=frame, aspect_ratio="9:16", duration_seconds=5,
        )
        assert job == "job-1"
        video_client.interactions.get(id="job-1")
        video_client.interactions.cancel(id="job-1")

    assert len(requests) == 4
    assert all(request.url.host == "aiplatform.googleapis.com" for request in requests)
    assert requests[0].url.path.startswith("/v1beta1/projects/trial-project/locations/global/")
    assert requests[0].headers["x-goog-api-key"] == "cloud-key"
    for request in requests[1:]:
        assert request.url.path.startswith("/v1beta1/projects/trial-project/locations/global/interactions")
        assert request.headers["authorization"] == "Bearer offline-token"
        assert "x-goog-api-key" not in request.headers
        assert "key=" not in str(request.url)
    body = json.loads(requests[1].content)
    assert body["background"] is True
    assert body["model"] == "gemini-omni-1.1-flash-preview"
    assert body["response_format"] == [{
        "type": "video", "aspect_ratio": "9:16", "delivery": "inline", "duration": "5s",
    }]
