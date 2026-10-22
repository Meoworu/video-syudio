from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_provider_configuration(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_VIDEO_API_KEY", "video-test-key")
    monkeypatch.setenv("GOOGLE_OMNI_MODEL", "gemini-omni-1.1-flash")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "trial-project")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    from app.config import get_settings

    get_settings.cache_clear()
    response = TestClient(app).get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "service": "video-studio",
        "googleApiKeyConfigured": True,
        "googleProjectConfigured": True,
        "googleVideoApiKeyConfigured": True,
        "googleVideoModel": "gemini-omni-1.1-flash",
        "minimaxConfigured": True,
    }
    get_settings.cache_clear()


def test_readiness_reports_missing_video_key(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_VIDEO_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_OMNI_MODEL", "gemini-omni-1.1-flash")
    from app.config import get_settings

    get_settings.cache_clear()
    response = TestClient(app).get("/v1/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["googleVideoApiKey"] is False
    assert response.json()["checks"]["googleVideoModel"] is True
    get_settings.cache_clear()

