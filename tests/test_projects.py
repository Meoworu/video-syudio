from pathlib import Path

from fastapi.testclient import TestClient

from app.api.projects import get_store
from app.config import get_settings
from app.main import app


class FakeDirector:
    def create_project(self, request):
        from app.domain.models import Project, Shot

        return Project(
            projectId="video_test1234",
            title="测试项目",
            story=request.story,
            aspectRatio=request.aspectRatio,
            style=request.style,
            shots=[Shot(id="shot_001", index=0, title="开场", prompt="开场画面", durationSeconds=5)],
        )


def test_project_store_persists_uploaded_frames(tmp_path: Path) -> None:
    from app.store.project_store import ProjectStore
    from app.domain.models import Project, Shot

    store = ProjectStore(tmp_path)
    project = Project(projectId="video_test1234", title="测试", story="故事", aspectRatio="9:16", style="style", shots=[Shot(id="shot_001", index=0, title="开场", prompt="画面", durationSeconds=5)])
    store.create(project)
    path = store.save_upload(project.projectId, "shot_001", "first", b"png")
    assert path.read_bytes() == b"png"

