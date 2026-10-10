from __future__ import annotations

from pathlib import Path
from typing import Any

from app.clients.google_text import GoogleTextClient
from app.clients.minimax_speech import MiniMaxSpeechClient
from app.config import Settings
from app.domain.models import Project
from app.store.project_store import ProjectStore


class NarrationService:
    def __init__(self, settings: Settings, store: ProjectStore, *, text_client: Any | None = None, speech_client: Any | None = None) -> None:
        self.settings = settings
        self.store = store
        self.text_client = text_client or GoogleTextClient(settings)
        self.speech_client = speech_client or MiniMaxSpeechClient(settings)

    def generate_manuscript(self, project: Project) -> Project:
        shot_context = "\n".join(f"镜头 {shot.index + 1}：{shot.title}；{shot.prompt}；{shot.durationSeconds} 秒" for shot in project.shots)
        result = self.text_client.generate_json(
            "为以下短视频生成一篇连贯的中文全片旁白。只返回 JSON："
            '{"manuscript":"..."}。不要逐镜头写成独立开头，不添加故事外事实。'
            f"\n故事：{project.story}\n镜头：\n{shot_context}"
        )
        manuscript = str(result.get("manuscript") or "").strip()
        if not manuscript:
            raise ValueError("Google 未返回有效的连续旁白文案")
        project.narration.manuscript = manuscript
        project.narration.status = "draft"
        self.store.save(project)
        return project

    def synthesize_audio(self, project: Project) -> Project:
        manuscript = project.narration.manuscript.strip()
        if not manuscript:
            raise ValueError("请先生成连续旁白文案")
        result = self.speech_client.synthesize(
            text=manuscript,
            voice_id=self.settings.minimax_speech_voice_id,
            model=self.settings.minimax_speech_model,
        )
        output = self.store.project_dir(project.projectId) / "audio" / "narration.mp3"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(result.audio_bytes)
        project.narration.audioPath = str(output.relative_to(self.store.project_dir(project.projectId)))
        project.narration.status = "audio_ready"
        self.store.save(project)
        return project

