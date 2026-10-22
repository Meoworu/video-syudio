from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.api.projects import get_store
from app.domain.models import CreateProjectRequest, FrameJob, Project, Shot, ShotVideo
from app.main import app
from app.store.project_store import ProjectStore


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
    store = ProjectStore(tmp_path)
    project = Project(projectId="video_test1234", title="测试", story="故事", aspectRatio="9:16", style="style", shots=[Shot(id="shot_001", index=0, title="开场", prompt="画面", durationSeconds=5)])
    store.create(project)
    path = store.save_upload(project.projectId, "shot_001", "first", b"png")
    assert path.read_bytes() == b"png"


def test_delete_project_removes_project_and_all_media(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(projectId="video_test1234", title="测试", story="故事", aspectRatio="9:16", style="style")
    store.create(project)
    media = store.project_dir(project.projectId) / "videos" / "shot_001.mp4"
    media.parent.mkdir()
    media.write_bytes(b"video")
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete(f"/v1/projects/{project.projectId}")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 200
    assert response.json() == {"projectId": project.projectId, "deleted": True}
    assert not store.project_dir(project.projectId).exists()


def test_delete_project_returns_not_found_without_touching_other_projects(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    existing = Project(projectId="video_existing123", title="保留", story="故事", aspectRatio="9:16", style="style")
    store.create(existing)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete("/v1/projects/video_missing123")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 404
    assert store.project_dir(existing.projectId).is_dir()


@pytest.mark.parametrize("project_id", ["../outside", "video_../outside", "video_INVALID!"])
def test_delete_project_rejects_invalid_ids(project_id: str, tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete(f"/v1/projects/{project_id}")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code in {400, 404}
    assert list(tmp_path.iterdir()) == []


def test_delete_project_refuses_active_generation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_running123", title="处理中", story="故事", aspectRatio="9:16", style="style",
        status="generating", shots=[Shot(id="shot_001", index=0, title="镜头", prompt="画面", durationSeconds=5)],
    )
    store.create(project)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete(f"/v1/projects/{project.projectId}")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 409
    assert store.project_dir(project.projectId).is_dir()


def test_delete_project_refuses_active_video_job(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_videojob123", title="视频处理中", story="故事", aspectRatio="9:16", style="style",
        shots=[Shot(
            id="shot_001", index=0, title="镜头", prompt="画面", durationSeconds=5,
            video=ShotVideo(model="test-model", status="downloading"),
        )],
    )
    store.create(project)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete(f"/v1/projects/{project.projectId}")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 409
    assert store.project_dir(project.projectId).is_dir()


def test_delete_project_refuses_active_frame_job(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_framejob123", title="首尾帧处理中", story="故事", aspectRatio="9:16", style="style",
        shots=[Shot(id="shot_001", index=0, title="镜头", prompt="画面", durationSeconds=5)],
    )
    project.shots[0].frames["first"].job = FrameJob(id="frame-job", requestId="frame-request", status="generating")
    store.create(project)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete(f"/v1/projects/{project.projectId}")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 409
    assert store.project_dir(project.projectId).is_dir()


def test_delete_project_rejects_symlink_and_preserves_target(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    target_store = ProjectStore(tmp_path / "external")
    target = Project(projectId="video_external123", title="外部项目", story="故事", aspectRatio="9:16", style="style")
    target_store.create(target)
    target_media = target_store.project_dir(target.projectId) / "keep.mp4"
    target_media.write_bytes(b"keep")
    store.project_dir(target.projectId).symlink_to(target_store.project_dir(target.projectId), target_is_directory=True)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).delete(f"/v1/projects/{target.projectId}")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == 400
    assert target_media.read_bytes() == b"keep"


def test_director_retry_refuses_to_migrate_legacy_project_with_existing_shot(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    request = CreateProjectRequest(story="原文故事。", sceneCount=1)
    project = Project(
        projectId="video_legacyretry12", title="旧项目", story=request.story,
        aspectRatio=request.aspectRatio, style=request.style, status="failed",
        directorRequest=request.model_dump(mode="json"),
        shots=[Shot(id="shot_001", index=0, title="用户制作的镜头", prompt="保留", durationSeconds=5)],
    )
    store.create(project)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).post(f"/v1/projects/{project.projectId}/director/retry")
    finally:
        app.dependency_overrides.pop(get_store, None)
    assert response.status_code == 409
    assert store.get(project.projectId).shots[0].title == "用户制作的镜头"

