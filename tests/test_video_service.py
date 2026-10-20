from pathlib import Path

import pytest

from app.clients.google_omni_video import GoogleOmniVideoClient
from app.config import Settings
from app.domain.models import Project, Shot, ShotVideo
from app.services.video_service import VideoService
from app.store.project_store import ProjectStore


class FakeVideoClient:
    def create_interaction(self, **kwargs):
        assert kwargs["aspect_ratio"] == "9:16"
        return "interaction-1"

    def wait_for_completion(self, job_id):
        assert job_id == "interaction-1"
        return {"status": "completed"}

    def save_video(self, interaction, output, *, cancel_check=None):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")


def test_video_service_persists_complete_result(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_test1234",
        title="测试",
        story="故事",
        aspectRatio="9:16",
        style="style",
        shots=[Shot(id="shot_001", index=0, title="开场", prompt="画面", durationSeconds=5)],
    )
    store.create(project)
    first = store.save_upload(project.projectId, "shot_001", "first", b"first")
    last = store.save_upload(project.projectId, "shot_001", "last", b"last")
    project = store.get(project.projectId)
    project.shots[0].uploads.firstFrame = str(first.relative_to(store.project_dir(project.projectId)))
    project.shots[0].uploads.lastFrame = str(last.relative_to(store.project_dir(project.projectId)))
    store.save(project)
    service = VideoService(Settings(_env_file=None), store, client=FakeVideoClient())
    service.run(project.projectId, "shot_001")
    result = store.get(project.projectId).shots[0].video
    assert result is not None
    assert result.status == "complete"
    assert result.provider == "google_agent_platform"
    assert (store.project_dir(project.projectId) / result.path).read_bytes() == b"video"


@pytest.mark.parametrize("provider", ["google_vertex", "google_gemini"])
def test_video_service_does_not_send_legacy_job_to_agent_platform(tmp_path: Path, provider: str) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_legacy1234",
        title="旧任务",
        story="故事",
        aspectRatio="9:16",
        style="style",
        shots=[Shot(id="shot_001", index=0, title="开场", prompt="画面", durationSeconds=5)],
    )
    project.shots[0].video = ShotVideo(
        model="gemini-omni-flash-preview", provider=provider,
        status="generating", remoteJobId="vertex-job-1",
    )
    store.create(project)
    fake = FakeVideoClient()
    service = VideoService(Settings(_env_file=None), store, client=fake)

    service.run(project.projectId, "shot_001")

    result = store.get(project.projectId).shots[0].video
    assert result is not None
    assert result.status == "failed"
    assert "旧服务端点" in (result.errorMessage or "")


@pytest.mark.parametrize("provider", ["google_vertex", "google_gemini"])
def test_video_service_does_not_cancel_legacy_job_with_agent_platform(tmp_path: Path, provider: str) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_legacy5678",
        title="旧任务",
        story="故事",
        aspectRatio="9:16",
        style="style",
        shots=[Shot(id="shot_001", index=0, title="开场", prompt="画面", durationSeconds=5)],
    )
    project.shots[0].video = ShotVideo(
        model="gemini-omni-flash-preview", provider=provider,
        status="generating", remoteJobId="vertex-job-1",
    )
    store.create(project)
    fake = FakeVideoClient()
    service = VideoService(Settings(_env_file=None), store, client=fake)

    try:
        service.cancel(project.projectId, "shot_001")
    except ValueError as error:
        assert "旧服务端点" in str(error)
    else:
        raise AssertionError("legacy Vertex task must not be sent to Gemini cancellation")

