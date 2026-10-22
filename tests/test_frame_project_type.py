from pathlib import Path

from app.config import Settings
from app.domain.models import AssetImage, Project, ProjectAsset, Shot
from app.services.frame_service import FrameService
from app.store.project_store import ProjectStore


def test_science_frame_snapshot_and_prompt_keep_type_constraint(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    shot = Shot(
        id="shot_001", index=0, title="海水蒸發", prompt="蒸發過程", durationSeconds=5,
        locationName="海面", firstFramePrompt="scientific ocean surface",
    )
    project = Project(
        projectId="video_science1234", title="水循環", story="解釋蒸發", projectType="science",
        aspectRatio="16:9", style="scientific visualization", shots=[shot],
        assets=[ProjectAsset(
            id="ocean", kind="location", name="海面", entityName="海面",
            image=AssetImage(imageId="image-1", path="assets/ocean/image.webp", mimeType="image/webp", size=10, width=10, height=10),
        )],
    )
    store.create(project)
    service = FrameService(Settings(_env_file=None), store, client=object())

    snapshot = service._snapshot(project, shot, "first")
    prompt = service._prompt(snapshot, "first", project.projectId, shot.id)

    assert snapshot["projectType"] == "science"
    assert "禁止出现人类" in prompt
    assert "保持参考图中的主体形态" in prompt
    assert "身份、服装" not in prompt


def test_old_frame_snapshot_defaults_to_story_prompts(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_story1234", title="故事", story="纸船", aspectRatio="9:16", style="cinematic",
        shots=[Shot(id="shot_001", index=0, title="开场", prompt="纸船", durationSeconds=5)],
    )
    store.create(project)
    service = FrameService(Settings(_env_file=None), store, client=object())

    prompt = service._prompt({"projectType": "story", "aspectRatio": "9:16", "style": "cinematic", "prompt": "boat", "references": []}, "first", project.projectId, "shot_001")

    assert "禁止出现人类" not in prompt
    assert "保持参考图中的身份、服装" in prompt
