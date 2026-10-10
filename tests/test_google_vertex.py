import pytest

from app.clients.google_vertex import GoogleVertexConfigError, load_vertex_runtime
from app.config import Settings


def test_vertex_requires_project() -> None:
    with pytest.raises(GoogleVertexConfigError, match="GOOGLE_CLOUD_PROJECT"):
        load_vertex_runtime(Settings(_env_file=None))


def test_vertex_never_accepts_api_key_configuration() -> None:
    settings = Settings(_env_file=None, GOOGLE_CLOUD_PROJECT="project")
    assert not hasattr(settings, "google_cloud_api_key")

