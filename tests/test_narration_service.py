from pathlib import Path

import pytest

from app.config import Settings
from app.domain.models import Project, Shot
from app.services.narration_service import NarrationService
from app.store.project_store import ProjectStore


class FakeTextClient:
    def generate_json(self, prompt):
        assert "连续全片旁白" in prompt
        return {"manuscript": "雨停后，纸船沿着溪流继续向前。"}


class FakeSpeechClient:
    def synthesize(self, **kwargs):
        assert kwargs["voice_id"] == "male-qn-qingse"
        from app.clients.minimax_speech import SpeechResult

        return SpeechResult(audio_bytes=b"mp3", mime_type="audio/mpeg")


class FakeScienceTextClient:
    def generate_json(self, prompt):
        assert "科普旁白编剧" in prompt
        assert "不添加未提供的实验结论、数值或事实" in prompt
        return {"manuscript": "水受热后蒸发，变成水汽上升。"}


class CaptureTextClient(FakeTextClient):
    def __init__(self):
        self.prompt = ""

    def generate_json(self, prompt):
        self.prompt = prompt
        return {"manuscript": "沿着原文继续。"}


def test_narration_uses_google_text_and_minimax_audio(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_test1234",
        title="测试",
        story="纸船回家",
        aspectRatio="9:16",
        style="style",
        shots=[Shot(id="shot_001", index=0, title="溪流", prompt="纸船漂流", durationSeconds=5)],
    )
    store.create(project)
    service = NarrationService(
        Settings(_env_file=None),
        store,
        text_client=FakeTextClient(),
        speech_client=FakeSpeechClient(),
    )
    project = service.generate_manuscript(project)
    assert project.narration.status == "draft"
    service._audio_duration = lambda _path: 2.0
    project = service.synthesize_audio(project)
    assert project.narration.status == "audio_ready"
    assert project.narration.alignment[0].sentenceId == "narration_000"
    assert (store.project_dir(project.projectId) / "audio/takes/narration_001.mp3").read_bytes() == b"mp3"


def test_science_narration_uses_explanatory_grounded_rules(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = Project(
        projectId="video_science1234", title="水循環", story="解释蒸发", projectType="science",
        aspectRatio="16:9", style="scientific", shots=[Shot(id="shot_001", index=0, title="蒸发", prompt="水汽上升", durationSeconds=5)],
    )
    store.create(project)
    service = NarrationService(Settings(_env_file=None), store, text_client=FakeScienceTextClient(), speech_client=FakeSpeechClient())

    result = service.generate_manuscript(project)

    assert result.narration.manuscript == "水受热后蒸发，变成水汽上升。"


def test_source_preserving_narration_uses_script_and_never_legacy_outline(tmp_path: Path) -> None:
    from app.domain.models import ProductionScript
    from app.services.story_source import source_hash, split_source

    story = "  原文中的动作。\n"
    segment = split_source(story)[0]
    script = ProductionScript(
        sourceHash=source_hash(story), sourceSegments=[segment],
        scenes=[{"index": 0, "title": "场景", "sourceSegmentIds": [segment.id], "beats": [
            {"text": story, "sourceSegmentIds": [segment.id]},
        ]}],
    )
    client = CaptureTextClient()
    project = Project(
        projectId="video_source1234", title="标题", story=story, aspectRatio="9:16", style="style",
        directorMode="source_preserving", productionScript=script,
        directorOutline={"title": "旧大纲", "logline": "不应读取", "synopsis": "不应读取", "theme": "", "characters": [], "locations": [], "scenes": [], "styleBible": {}},
        shots=[Shot(id="shot_001", index=0, title="动作", prompt="镜头", durationSeconds=5)],
    )
    store = ProjectStore(tmp_path)
    store.create(project)
    result = NarrationService(Settings(_env_file=None), store, text_client=client, speech_client=FakeSpeechClient()).generate_manuscript(project)
    assert result.story == story
    assert "经原文引用校验的制作剧本" in client.prompt
    assert "不应读取" not in client.prompt
    assert story in client.prompt


class SequenceTextClient:
    def __init__(self, manuscripts):
        self.manuscripts = iter(manuscripts)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return {"manuscript": next(self.manuscripts)}


def narration_project():
    return Project(
        projectId="video_narration1234", title="测试", story="保持原文不变。", aspectRatio="9:16", style="style",
        shots=[Shot(id="shot_001", index=0, title="一", prompt="画面", durationSeconds=5)],
    )


def test_generated_narration_is_shortened_once_when_it_exceeds_timeline(tmp_path):
    store = ProjectStore(tmp_path)
    project = narration_project()
    store.create(project)
    client = SequenceTextClient(["毛毛虫沿着树枝移动，" * 20 + "随后停下。", "毛毛虫停下。"])

    result = NarrationService(Settings(_env_file=None), store, text_client=client).generate_manuscript(project)

    assert result.narration.manuscript == "毛毛虫停下。"
    assert result.story == "保持原文不变。"
    assert len(client.prompts) == 2
    assert "未通过本地时长校验" in client.prompts[1]
    assert result.narration.alignment[-1].endSeconds <= 5
    assert store.get(project.projectId).narration.manuscript == "毛毛虫停下。"


def test_unsuccessful_shortening_preserves_existing_narration_and_final_video(tmp_path):
    from app.services.narration_timing import NarrationDurationError

    store = ProjectStore(tmp_path)
    project = narration_project()
    project.narration.manuscript = "原有旁白。"
    project.finalVideoPath = "final/video.mp4"
    store.create(project)
    original = project.model_dump(mode="json")
    long_text = "毛毛虫沿着树枝移动，" * 20 + "随后停下。"
    client = SequenceTextClient([long_text, long_text])

    with pytest.raises(NarrationDurationError, match="旁白预计超出成片时长"):
        NarrationService(Settings(_env_file=None), store, text_client=client).generate_manuscript(project)

    assert len(client.prompts) == 2
    assert project.model_dump(mode="json") == original
    assert store.get(project.projectId).model_dump(mode="json") == original


@pytest.mark.parametrize("provider_failure", [False, True])
def test_manuscript_endpoint_returns_readable_generation_errors(tmp_path, monkeypatch, provider_failure):
    from fastapi.testclient import TestClient
    from app.api.projects import get_store
    from app.clients.google_text import GoogleTextError
    from app.main import app

    store = ProjectStore(tmp_path)
    project = narration_project()
    store.create(project)
    error = GoogleTextError("文本服务暂时不可用") if provider_failure else ValueError("旁白预计超出成片时长")

    def fail(self, project):
        raise error

    monkeypatch.setattr(NarrationService, "generate_manuscript", fail)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = TestClient(app).post(f"/v1/projects/{project.projectId}/narration/manuscript")
    finally:
        app.dependency_overrides.pop(get_store, None)

    assert response.status_code == (502 if provider_failure else 400)
    assert response.json()["detail"] == str(error)

