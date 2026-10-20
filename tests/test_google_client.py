import pytest
import httpx
import json
from google import genai

from app.clients.google_client import GoogleClientConfigError, build_google_client, safe_google_error
from app.config import Settings
from app.clients.google_omni_video import GoogleOmniVideoClient


def test_google_client_requires_api_key() -> None:
    with pytest.raises(GoogleClientConfigError, match="GOOGLE_API_KEY"):
        build_google_client(Settings(_env_file=None))


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


def test_google_client_routes_text_and_video_to_cloud_project(monkeypatch, tmp_path) -> None:
    requests = []

    def send(client, request, **kwargs):
        requests.append(request)
        payload = {"id": "job-1", "status": "completed"} if "/interactions" in request.url.path else {
            "candidates": [{"content": {"parts": [{"text": "{}"}], "role": "model"}}]
        }
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
    monkeypatch.setattr("google.auth.default", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ADC used")))
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "false")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    settings = Settings(_env_file=None, GOOGLE_API_KEY="test-key", GOOGLE_CLOUD_PROJECT="trial-project")
    with build_google_client(settings) as client:
        client.models.generate_content(model="gemini-3.6-flash", contents="test")
        frame = tmp_path / "frame.png"
        frame.write_bytes(b"offline-image")
        job = GoogleOmniVideoClient(settings, client=client).create_interaction(
            prompt="offline", first_frame=frame, last_frame=frame, aspect_ratio="9:16", duration_seconds=5,
        )
        assert job == "job-1"
        client.interactions.get(id="job-1")
        client.interactions.cancel(id="job-1")

    assert len(requests) == 4
    for request in requests:
        assert request.url.host == "aiplatform.googleapis.com"
        assert request.url.path.startswith("/v1beta1/projects/trial-project/locations/global/")
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "key=" not in str(request.url)
    body = json.loads(requests[1].content)
    assert body["background"] is True
    assert body["response_format"] == [{
        "type": "video", "aspect_ratio": "9:16", "delivery": "inline", "duration": "5s",
    }]
