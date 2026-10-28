from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import uuid
import wave
from pathlib import Path

import httpx

from app.clients.google_text import GoogleTextClient
from app.clients.minimax_speech import MiniMaxSpeechClient
from app.config import Settings
from app.domain.models import NarrationTake, NarrationWindow, Project, SegmentAudio
from app.services.audio_timeline_service import SAMPLE_RATE, assemble_pcm_timeline
from app.services.media_job_service import cancel_requested, touch_job
from app.services.narration_windows_service import validate_windows
from app.store.project_store import ProjectStore


_TTS_LOCK = threading.Lock()
_POLICY_VERSION = "windowed-tts-v1"


class NarrationJobCancelled(RuntimeError):
    """Raised before a queued provider call when the user cancelled the job."""


class NarrationAudioService:
    def __init__(self, settings: Settings, store: ProjectStore, *, speech=None, google=None) -> None:
        self.settings = settings
        self.store = store
        self.speech = speech or MiniMaxSpeechClient(settings)
        self.google = google or GoogleTextClient(settings)

    def run(self, project_id: str, job_id: str, *, speed: float = 1.0,
            window_ids: list[str] | None = None, force_regenerate: bool = False) -> None:
        with self.store.lock(project_id):
            initial = self.store.get(project_id)
            job = next((item for item in initial.mediaJobs if item.id == job_id), None)
            if not job or job.status != "queued":
                return
            project_snapshot = Project.model_validate(job.inputSnapshot["project"])
            touch_job(job, "running")
            self.store.save(initial)
        try:
            windows = project_snapshot.narration.windows
            preview = project_snapshot.preview
            if project_snapshot.narration.mode != "windowed" or not preview or preview.status != "ready":
                raise ValueError("请先保存并确认时间窗，且确保剪辑预览有效")
            if not windows:
                raise ValueError("至少需要创建一个旁白时间窗")
            windows = validate_windows(windows, preview, require_ready=True)
            selected_window_ids = set(window_ids or ())
            available_window_ids = {window.id for window in windows}
            if selected_window_ids and not selected_window_ids <= available_window_ids:
                raise ValueError("配音任务指定了无效的旁白时间窗")
            force_window_ids = selected_window_ids or (available_window_ids if force_regenerate else set())
            selected_take = next(
                (take for take in project_snapshot.narration.takes
                 if take.id == project_snapshot.narration.selectedTakeId
                 and take.mode == "windowed"
                 and take.status != "stale"
                 and take.previewId == preview.id
                 and take.windowRevision == project_snapshot.narration.windowRevision),
                None,
            )
            selected_manifest: dict[str, SegmentAudio] = {}
            if selected_take:
                for item in selected_take.segmentManifest:
                    try:
                        segment = SegmentAudio.model_validate(item)
                    except Exception:
                        continue
                    selected_manifest.setdefault(segment.windowId, segment)
            voice = {
                "model": self.settings.minimax_speech_model,
                "voiceId": self.settings.minimax_speech_voice_id,
                "speed": speed,
                "emotion": "neutral",
                "sampleRate": SAMPLE_RATE,
                "policy": _POLICY_VERSION,
            }
            completed: dict[str, tuple[SegmentAudio, bytes]] = {}
            for window in windows:
                if self._cancelled(project_id, job_id):
                    self._mark_cancelled(project_id, job_id)
                    return
                width = window.endSeconds - window.startSeconds
                margin = min(0.15, width * 0.1) + min(0.2, width * 0.1)
                speech_budget = width - margin
                if speech_budget <= 0:
                    raise ValueError(f"时间窗 {window.order + 1} 太短，无法容纳旁白")
                window_signature = self._signature(window.text, width, preview.inputSignature, voice)
                cached = None
                if window.id not in force_window_ids:
                    # A partial redo starts from the currently selected full take.
                    # The generic cache contains newer versions too, so consulting
                    # it first can silently replace untouched windows after a user
                    # switches back to an older take.
                    # Preserve the selected take only for a targeted redo. A
                    # full-track request must honor the requested voice settings
                    # and reuse only cache entries with the matching signature.
                    baseline = selected_manifest.get(window.id) if selected_window_ids else None
                    if baseline:
                        cached = self._load_cached_segment(
                            project_id, window, baseline, speech_budget,
                        )
                    else:
                        cached = self._find_cache(
                            project_id, project_snapshot, window.id, window_signature, speech_budget,
                        )
                if cached:
                    completed[window.id] = cached
                    continue
                text = window.text.strip()
                result = self._synthesize(text, voice, cancel_check=lambda: self._cancelled(project_id, job_id))
                raw_path, pcm_path, pcm = self._save_and_decode(project_id, window.id, window_signature, result.audio_bytes)
                measured = len(pcm) / 2 / SAMPLE_RATE
                raw_measured = measured
                if measured > speech_budget and not window.textLocked and not self._cancelled(project_id, job_id):
                    original = (text, window_signature, result, raw_path, pcm_path, pcm, measured)
                    try:
                        shorter = self._shorten(project_snapshot, window.text, speech_budget)
                        if shorter and shorter.strip() != text and len(shorter.strip()) < len(text) and not self._cancelled(project_id, job_id):
                            candidate_text = shorter.strip()
                            candidate_signature = self._signature(candidate_text, width, preview.inputSignature, voice)
                            candidate_result = self._synthesize(candidate_text, voice, cancel_check=lambda: self._cancelled(project_id, job_id))
                            candidate_raw, candidate_pcm_path, candidate_pcm = self._save_and_decode(
                                project_id, window.id, candidate_signature, candidate_result.audio_bytes,
                            )
                            text, window_signature, result = candidate_text, candidate_signature, candidate_result
                            raw_path, pcm_path, pcm = candidate_raw, candidate_pcm_path, candidate_pcm
                            measured = len(pcm) / 2 / SAMPLE_RATE
                            raw_measured = measured
                    except Exception:
                        # Keep the successful first take if the bounded correction fails.
                        text, window_signature, result, raw_path, pcm_path, pcm, measured = original
                        raw_measured = measured
                tempo = 1.0
                if measured > speech_budget:
                    tempo = measured / speech_budget
                    if tempo > min(self.settings.narration_max_audio_tempo, 1.08):
                        self._mark_window(project_id, window.id, "needs_edit", estimated=measured)
                        raise ValueError(f"时间窗 {window.order + 1} 配音仍超时，请精简文案或调整时间窗")
                    pcm_path = self._apply_tempo(pcm_path, tempo)
                    pcm = self._read_wav_pcm(pcm_path)
                    measured = len(pcm) / 2 / SAMPLE_RATE
                    if measured > speech_budget + 1 / SAMPLE_RATE:
                        self._mark_window(project_id, window.id, "needs_edit", estimated=measured)
                        raise ValueError(f"时间窗 {window.order + 1} 校准后仍超时")
                placed_start = window.startSeconds + min(0.15, width * 0.1)
                audio = SegmentAudio(
                    id=f"segment_{uuid.uuid4().hex[:16]}", windowId=window.id,
                    inputSignature=window_signature, rawPath=raw_path,
                    calibratedPath=str(pcm_path.relative_to(self.store.project_dir(project_id))),
                    measuredDurationSeconds=max(0.001, raw_measured),
                    calibratedDurationSeconds=max(0.001, measured), placedStartSeconds=placed_start,
                    placedEndSeconds=placed_start + measured, tempoFactor=tempo,
                    providerTraceId=result.provider_request_id,
                )
                completed[window.id] = (audio, pcm)
                self._save_segment(project_id, job_id, window.id, audio, len(completed), len(windows), text=text)
            if len(completed) != len(windows):
                return
            if self._cancelled(project_id, job_id):
                self._mark_cancelled(project_id, job_id)
                return
            current = self.store.get(project_id)
            if not current.preview or current.preview.id != preview.id or current.narration.windowRevision != project_snapshot.narration.windowRevision:
                raise ValueError("时间窗或剪辑预览已更新，取消本次合成")
            root = self.store.project_dir(project_id)
            take_number = max((int(take.id.split("_")[-1]) for take in current.narration.takes if take.id.startswith("take_")), default=0) + 1
            timeline_path = root / "audio" / "takes" / f"take_{take_number:03d}" / "narration.wav"
            assemble_pcm_timeline(current.narration.windows, completed, preview.durationSeconds, timeline_path)
            relative = str(timeline_path.relative_to(root))
            audition_path = root / "audio" / "takes" / f"take_{take_number:03d}" / "audition.mp4"
            audition_relative = self._mux_audition(project_id, preview.path, relative, audition_path, preview.durationSeconds)
            with self.store.lock(project_id):
                current = self.store.get(project_id)
                job = next((item for item in current.mediaJobs if item.id == job_id), None)
                if not job or cancel_requested(job):
                    timeline_path.unlink(missing_ok=True)
                    audition_path.unlink(missing_ok=True)
                    if job:
                        touch_job(job, "cancelled", message="分段配音任务已取消")
                        self.store.save(current)
                    return
                if not current.preview or current.preview.id != preview.id or current.narration.windowRevision != project_snapshot.narration.windowRevision:
                    timeline_path.unlink(missing_ok=True)
                    audition_path.unlink(missing_ok=True)
                    raise ValueError("时间窗或剪辑预览已更新，未发布旁白版本")
                manifest = [audio.model_dump(mode="json") for audio, _ in completed.values()]
                take = NarrationTake(
                    id=f"take_{take_number:03d}", path=relative, durationSeconds=preview.durationSeconds,
                    speed=speed, status="selected", mode="windowed", previewId=preview.id,
                    windowRevision=current.narration.windowRevision,
                    inputSignature=self._signature(manifest, preview.durationSeconds, preview.inputSignature, voice),
                    segmentManifest=manifest, voiceSnapshot=voice, auditionPath=audition_relative,
                )
                current.narration.takes = [item.model_copy(update={"status": "ready"}) if item.status == "selected" else item for item in current.narration.takes]
                current.narration.takes.append(take)
                current.narration.selectedTakeId = take.id
                current.narration.audioPath = relative
                current.narration.audioDurationSeconds = preview.durationSeconds
                current.narration.status = "audio_ready"
                if current.finalRender:
                    current.finalRender.isCurrent = False
                for window in current.narration.windows:
                    window.status = "complete"
                touch_job(job, "complete")
                job.progress = {"completed": len(windows), "total": len(windows)}
                self.store.save(current)
        except Exception as error:
            with self.store.lock(project_id):
                current = self.store.get(project_id)
                job = next((item for item in current.mediaJobs if item.id == job_id), None)
                if job and cancel_requested(job):
                    touch_job(job, "cancelled", message="分段配音任务已取消")
                    self.store.save(current)
                elif job:
                    unknown_outcome = isinstance(error, httpx.TransportError) or (
                        isinstance(error, httpx.HTTPStatusError) and error.response.status_code >= 500
                    )
                    message = str(error)
                    if unknown_outcome:
                        message = f"MiniMax 请求结果未知，未自动重试；再次生成可能产生重复费用。{message}"
                    touch_job(job, "failed", code="NARRATION_AUDIO_FAILED", message=message[:1200])
                    self.store.save(current)

    def _synthesize(self, text: str, voice: dict, *, cancel_check=None):
        with _TTS_LOCK:
            if cancel_check and cancel_check():
                raise NarrationJobCancelled("分段配音任务已取消")
            return self.speech.synthesize(
                text=text, voice_id=voice["voiceId"], emotion=voice["emotion"],
                speed=voice["speed"], model=voice["model"], retry_transient_errors=False,
            )

    def _shorten(self, project: Project, text: str, budget: float) -> str | None:
        basis = project.productionScript.model_dump(mode="json") if project.productionScript else project.story
        result = self.google.generate_json(
            "请只精简给定旁白，保留句子完整、原文事实和关键语义，不添加新事实。"
            "返回 JSON {\"text\":\"...\"}。\n"
            f"最长目标口播时长约 {budget:.2f} 秒。原始内容：{json.dumps(basis, ensure_ascii=False)}\n旁白：{text}"
        )
        candidate = result.get("text")
        return candidate if isinstance(candidate, str) and candidate.strip() else None

    def _save_and_decode(self, project_id: str, window_id: str, signature: str, audio: bytes) -> tuple[str, Path, bytes]:
        # Every provider response gets an immutable path. Identical prompts in
        # different windows must never overwrite audio already referenced by a take.
        root = self.store.project_dir(project_id)
        digest = hashlib.sha256(window_id.encode()).hexdigest()[:12]
        generation_id = uuid.uuid4().hex
        relative = f"audio/segments/{digest}_{signature[:16]}_{generation_id}.mp3"
        raw_path = self.store.save_media(project_id, relative, audio)
        pcm_path = root / "audio" / "segments" / f"{digest}_{signature[:16]}_{generation_id}.wav"
        self._convert_to_wav(raw_path, pcm_path)
        return relative, pcm_path, self._read_wav_pcm(pcm_path)

    def _convert_to_wav(self, source: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [self.settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(output)],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if result.returncode:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"旁白音频解码失败：{result.stderr[-800:]}")

    def _apply_tempo(self, source: Path, tempo: float) -> Path:
        output = source.with_name(f"{source.stem}.atempo.wav")
        result = subprocess.run(
            [self.settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
             "-filter:a", f"atempo={tempo:.6f}", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(output)],
            capture_output=True, text=True, check=False, timeout=120,
        )
        if result.returncode:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"旁白时长校准失败：{result.stderr[-800:]}")
        return output

    def _mux_audition(self, project_id: str, preview_path: str, audio_path: str, output: Path, duration: float) -> str:
        root = self.store.project_dir(project_id).resolve()
        preview = (root / preview_path).resolve()
        audio = (root / audio_path).resolve()
        if root not in preview.parents or root not in audio.parents or not preview.is_file() or not audio.is_file():
            raise ValueError("试听文件路径无效")
        output.parent.mkdir(parents=True, exist_ok=True)
        partial = output.with_name(".audition.part.mp4")
        result = subprocess.run(
            [self.settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-i", str(preview), "-i", str(audio),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-t", f"{duration:.6f}", "-movflags", "+faststart", "-f", "mp4", str(partial)],
            capture_output=True, text=True, check=False, timeout=self.settings.preview_render_timeout_seconds,
        )
        if result.returncode:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"生成同步试听文件失败：{result.stderr[-800:]}")
        partial.replace(output)
        return str(output.relative_to(root))

    @staticmethod
    def _read_wav_pcm(path: Path) -> bytes:
        with wave.open(str(path), "rb") as audio:
            if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getframerate() != SAMPLE_RATE:
                raise ValueError("配音片段未转换为 48 kHz 单声道 PCM")
            return audio.readframes(audio.getnframes())

    def _find_cache(self, project_id: str, project: Project, window_id: str, signature: str,
                    speech_budget: float) -> tuple[SegmentAudio, bytes] | None:
        segment = next((item for item in project.narration.segmentAudios if item.windowId == window_id and item.inputSignature == signature), None)
        if not segment or not segment.calibratedPath:
            return None
        window = next((item for item in project.narration.windows if item.id == window_id), None)
        if not window:
            return None
        return self._load_cached_segment(project_id, window, segment, speech_budget)

    def _load_cached_segment(self, project_id: str, window: NarrationWindow, segment: SegmentAudio,
                             speech_budget: float) -> tuple[SegmentAudio, bytes] | None:
        if not segment.calibratedPath:
            return None
        root = self.store.project_dir(project_id).resolve()
        calibrated = (root / segment.calibratedPath).resolve()
        raw = (root / segment.rawPath).resolve()
        if root not in calibrated.parents or root not in raw.parents or not calibrated.is_file() or not raw.is_file():
            return None
        start = window.startSeconds + min(0.15, (window.endSeconds - window.startSeconds) * 0.1)
        try:
            pcm = self._read_wav_pcm(calibrated)
        except (OSError, EOFError, wave.Error, ValueError):
            return None
        duration = len(pcm) / 2 / SAMPLE_RATE
        if duration > speech_budget + 1 / SAMPLE_RATE:
            return None
        return segment.model_copy(update={"placedStartSeconds": start, "placedEndSeconds": start + duration}), pcm

    def _save_segment(self, project_id: str, job_id: str, window_id: str, audio: SegmentAudio, completed: int, total: int, *, text: str) -> None:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            job = next((item for item in project.mediaJobs if item.id == job_id), None)
            if not job:
                return
            project.narration.segmentAudios = [item for item in project.narration.segmentAudios if not (item.windowId == window_id and item.inputSignature == audio.inputSignature)]
            project.narration.segmentAudios.append(audio)
            window = next(item for item in project.narration.windows if item.id == window_id)
            window.text = text
            window.status = "complete"
            window.estimatedDurationSeconds = audio.calibratedDurationSeconds
            progress = {"completed": completed, "total": total}
            if job.progress.get("cancelRequested"):
                progress["cancelRequested"] = True
            job.progress = progress
            self.store.save(project)

    def _mark_window(self, project_id: str, window_id: str, status: str, *, estimated: float) -> None:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            window = next((item for item in project.narration.windows if item.id == window_id), None)
            if window:
                window.status = status
                window.estimatedDurationSeconds = estimated
                self.store.save(project)

    def _cancelled(self, project_id: str, job_id: str) -> bool:
        try:
            project = self.store.get(project_id)
        except FileNotFoundError:
            return True
        job = next((item for item in project.mediaJobs if item.id == job_id), None)
        return not job or cancel_requested(job)

    def _mark_cancelled(self, project_id: str, job_id: str) -> None:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            job = next((item for item in project.mediaJobs if item.id == job_id), None)
            if job and cancel_requested(job):
                touch_job(job, "cancelled", message="分段配音任务已取消；已完成片段已保留")
                self.store.save(project)

    @staticmethod
    def _signature(text: str | object, duration: float, preview_signature: str, voice: dict) -> str:
        payload = json.dumps({"text": text, "duration": round(duration, 6), "preview": preview_signature,
                              "voice": voice}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()
