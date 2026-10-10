from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_provider_configuration(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()
    response = TestClient(app).get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "video-studio",
        "googleProjectConfigured": True,
        "minimaxConfigured": True,
    }
    get_settings.cache_clear()

