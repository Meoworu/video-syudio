from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from app.clients.google_text import GoogleTextClient
from app.clients.minimax_speech import MiniMaxSpeechClient
from app.config import Settings
from app.domain.models import NarrationSentence, NarrationTake, Project
from app.services.narration_timing import align_narration, split_manuscript
from app.services.editing import project_duration
from app.store.project_store import ProjectStore


class NarrationService:
    def __init__(self, settings: Settings, store: ProjectStore, *, text_client: Any | None = None, speech_client: Any | None = None) -> None:
        self.settings = settings
        self.store = store
        self.text_client = text_client or GoogleTextClient(settings)
        self.speech_client = speech_client or MiniMaxSpeechClient(settings)

    def generate_manuscript(self, project: Project) -> Project:
        shot_context = "\n".join(
            f"镜头 {shot.index + 1}（{shot.durationSeconds}秒）：{shot.title}；{shot.beat or shot.prompt}；"
            f"叙事作用：{shot.narrativePurpose}"
            for shot in sorted(project.shots, key=lambda item: item.index)
        )
        outline = project.directorOutline.model_dump(mode="json") if project.directorOutline else {}
        video_duration = project_duration(project)
        target = video_duration * 0.84
        prompt = (
            "你是电影旁白编剧。创作中文连续全片旁白，不要逐镜头解说，不要每句重复画面已明确表达的动作。"
            "句子按完整叙事顺序连续推进，允许一句跨越多个镜头，不允许为了镜头切换制造停顿。"
            "不得新增输入故事之外的人物、事实或因果；句子需完整并以。！？结束。"
            f"旁白自然朗读目标约 {target:.1f} 秒，视频全长 {video_duration:.1f} 秒。"
            "只返回 JSON："
            '{"voiceStyle":"声音风格","voiceDirection":"表演指导", "sentences":[{"id":"narration_000",'
            '"order":0,"text":"完整句。","narrativeFunction":"叙事功能","sourceShotIndexes":[0],'
            '"emotion":"情绪","delivery":"表达方式","paceClass":"natural","pauseAfterSeconds":0.2}]}。'
            f"\n故事：{project.story}\n导演大纲：{json.dumps(outline, ensure_ascii=False)}\n分镜：\n{shot_context}"
        )
        result = self.text_client.generate_json(prompt)
        raw_sentences = result.get("sentences")
        if not isinstance(raw_sentences, list) or not raw_sentences:
            manuscript = str(result.get("manuscript") or "").strip()
            sentences = split_manuscript(manuscript)
        else:
            sentences = [NarrationSentence.model_validate(item) for item in raw_sentences]
        if not sentences:
            raise ValueError("Google 未返回有效的连续旁白文案")
        if [item.order for item in sentences] != list(range(len(sentences))):
            raise ValueError("Google 返回的旁白句子顺序不连续")
        sentences, cues, target, estimated = align_narration(project, sentences)
        manuscript = "".join(item.text for item in sentences)
        project.narration.manuscript = manuscript
        project.narration.voiceStyle = str(result.get("voiceStyle") or "自然、克制、清晰的电影旁白")
        project.narration.voiceDirection = str(result.get("voiceDirection") or "保持连贯讲述，句间短停顿")
        project.narration.sentences = sentences
        project.narration.alignment = cues
        project.narration.targetDurationSeconds = target
        project.narration.estimatedDurationSeconds = estimated
        project.narration.status = "draft"
        project.narration.audioPath = None
        project.narration.timingWarning = None
        project.finalVideoPath = None
        self.store.save(project)
        return project

    def synthesize_audio(self, project: Project, *, speed: float = 1.0) -> Project:
        manuscript = project.narration.manuscript.strip()
        if not manuscript:
            raise ValueError("请先生成连续旁白文案")
        result = self.speech_client.synthesize(
            text=manuscript,
            voice_id=self.settings.minimax_speech_voice_id,
            speed=speed,
            model=self.settings.minimax_speech_model,
        )
        version = len(project.narration.takes) + 1
        relative = f"audio/takes/narration_{version:03d}.mp3"
        output = self.store.project_dir(project.projectId) / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_name(f"{output.stem}.part{output.suffix}")
        partial.write_bytes(result.audio_bytes)
        try:
            duration = self._audio_duration(partial)
            if duration <= 0:
                raise ValueError("MiniMax 返回了无效的旁白时长")
            video_duration = project_duration(project)
            if duration > video_duration + 1.0:
                raise ValueError(
                    f"MiniMax 音频 {duration:.1f}s 超过视频时长 {video_duration:.1f}s；请提高语速或精简文稿后重试"
                )
            partial.replace(output)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        for take in project.narration.takes:
            take.status = "ready"
        take = NarrationTake(id=f"take_{version:03d}", path=relative, durationSeconds=duration, speed=speed, status="selected")
        project.narration.takes.append(take)
        project.narration.selectedTakeId = take.id
        project.narration.audioPath = relative
        project.narration.audioDurationSeconds = duration
        project.narration.timingWarning = (
            "实际音频明显短于文稿预算，请检查旁白内容或尝试降低语速。"
            if project.narration.targetDurationSeconds and duration < project.narration.targetDurationSeconds * 0.7
            else None
        )
        project.narration.status = "audio_ready"
        project.finalVideoPath = None
        self.store.save(project)
        return project

    def update_manuscript(self, project: Project, manuscript: str) -> Project:
        manuscript = manuscript.strip()
        if not manuscript:
            raise ValueError("旁白文案不能为空")
        sentences = split_manuscript(manuscript)
        sentences, cues, target, estimated = align_narration(project, sentences)
        project.narration.manuscript = "".join(item.text for item in sentences)
        project.narration.sentences = sentences
        project.narration.alignment = cues
        project.narration.targetDurationSeconds = target
        project.narration.estimatedDurationSeconds = estimated
        project.narration.audioPath = None
        project.narration.audioDurationSeconds = None
        project.narration.timingWarning = None
        project.narration.selectedTakeId = None
        for take in project.narration.takes:
            take.status = "ready"
        project.narration.status = "draft"
        project.finalVideoPath = None
        self.store.save(project)
        return project

    def select_take(self, project: Project, take_id: str) -> Project:
        take = next((item for item in project.narration.takes if item.id == take_id), None)
        if take is None:
            raise ValueError("旁白版本不存在")
        path = self.store.project_dir(project.projectId) / take.path
        if not path.is_file():
            raise FileNotFoundError(take.path)
        for item in project.narration.takes:
            item.status = "selected" if item.id == take_id else "ready"
        project.narration.selectedTakeId = take.id
        project.narration.audioPath = take.path
        project.narration.audioDurationSeconds = take.durationSeconds
        project.narration.timingWarning = None
        project.narration.status = "audio_ready"
        project.finalVideoPath = None
        self.store.save(project)
        return project

    def _audio_duration(self, path: Path) -> float:
        result = subprocess.run(
            [self.settings.ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"无法读取 MiniMax 音频时长：{result.stderr[-500:]}")
        payload = json.loads(result.stdout)
        if not any(stream.get("codec_type") == "audio" for stream in payload.get("streams", [])):
            raise RuntimeError("MiniMax 文件中没有可读取的音频流")
        duration = float(payload["format"]["duration"])
        if duration <= 0:
            raise RuntimeError("MiniMax 音频无有效时长")
        return duration

