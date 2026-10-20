from pathlib import Path

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

