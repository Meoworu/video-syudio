import pytest
from google import genai

from app.clients.google_client import GoogleClientConfigError, build_google_client, safe_google_error
from app.config import Settings


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
    settings = Settings(_env_file=None, **{field: value})

    build_google_client(settings)

    assert captured == {
        "vertexai": False,
        "enterprise": False,
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
