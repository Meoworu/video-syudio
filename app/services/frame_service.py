from __future__ import annotations

import hashlib
import json
import mimetypes
import threading
import uuid
from pathlib import Path
from typing import Any

from app.clients.google_image import GoogleImageClient
from app.config import Settings
from app.domain.models import FrameJob, FrameVersion, Project, Shot
from app.services.asset_service import normalize_image, resolve_asset_references
from app.services.project_type_policy import is_science, visual_constraint
from app.store.project_store import ProjectStore


_SEMAPHORE_LOCK = threading.Lock()
_SEMAPHORES: dict[tuple[str, int], threading.BoundedSemaphore] = {}
_ACTIVE_GROUPS_LOCK = threading.Lock()
_ACTIVE_GROUPS: set[tuple[str, str]] = set()


class FrameService:
    def __init__(self, settings: Settings, store: ProjectStore, *, client: Any | None = None) -> None:
        self.settings = settings
        self.store = store
        self.client = client or GoogleImageClient(settings)

    def enqueue(self, project: Project, shot: Shot, role: str, request_id: str) -> str:
        slot = shot.frames[role]
        if slot.job and slot.job.requestId == request_id:
            return slot.job.id
        if slot.job and slot.job.status in {"queued", "generating"}:
            raise ValueError("此帧已有生成任务正在执行")
        if shot.video and shot.video.status in {"submitting", "generating", "downloading"}:
            raise ValueError("视频生成期间不能生成首尾帧")
        snapshot = self._snapshot(project, shot, role)
        job = FrameJob(id=uuid.uuid4().hex, requestId=request_id, inputSnapshot=snapshot)
        slot.job = job
        return job.id

    def enqueue_pair(self, project: Project, shot: Shot, request_id: str) -> tuple[str, str, str, bool]:
        first_existing, last_existing = shot.frames["first"].job, shot.frames["last"].job
        if (
            first_existing and last_existing
            and first_existing.requestId == f"{request_id}:first"
            and last_existing.requestId == f"{request_id}:last"
            and first_existing.groupId == last_existing.groupId
        ):
            return first_existing.groupId or "", first_existing.id, last_existing.id, False
        group_id = uuid.uuid4().hex
        ids = []
        for role in ("first", "last"):
            slot = shot.frames[role]
            if slot.job and slot.job.status in {"queued", "generating"}:
                raise ValueError("此镜头已有图片生成任务正在执行")
            if shot.video and shot.video.status in {"submitting", "generating", "downloading"}:
                raise ValueError("视频生成期间不能生成首尾帧")
            snapshot = self._snapshot(project, shot, role)
            job = FrameJob(id=uuid.uuid4().hex, requestId=f"{request_id}:{role}", groupId=group_id, inputSnapshot=snapshot)
            slot.job = job
            ids.append(job.id)
        return group_id, ids[0], ids[1], True

    def run(self, project_id: str, shot_id: str, role: str, job_id: str, first_frame: tuple[bytes, str, str] | None = None) -> bool:
        with self._semaphore():
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                shot = next(item for item in project.shots if item.id == shot_id)
                slot = shot.frames[role]
                job = slot.job
                if not job or job.id != job_id or job.status != "queued":
                    return False
                job.status = "generating"
                snapshot = dict(job.inputSnapshot)
                self.store.save(project)
            try:
                refs = []
                for reference in snapshot["references"]:
                    refs.append((self._read(project_id, reference["path"]), reference["mimeType"], reference["name"]))
                first_frame_id = None
                if first_frame:
                    refs.append((first_frame[0], first_frame[1], "generated first frame for continuity"))
                    first_frame_id = first_frame[2]
                elif snapshot.get("firstFramePath"):
                    mime_type = mimetypes.guess_type(snapshot["firstFramePath"])[0] or "image/webp"
                    refs.append((self._read(project_id, snapshot["firstFramePath"]), mime_type, "current first frame for continuity"))
                    first_frame_id = snapshot["firstFrameVersionId"]
                prompt = self._prompt(snapshot, role, project_id, shot_id)
                image_bytes, image_mime = self.client.generate(prompt, refs, snapshot["aspectRatio"])
                normalized, width, height = normalize_image(image_bytes, image_mime)
                version_id = uuid.uuid4().hex
                relative_path = f"frames/{shot_id}/{role}/{version_id}.webp"
                self.store.save_media(project_id, relative_path, normalized)
                self._complete(project_id, shot_id, role, job_id, snapshot, version_id, relative_path, first_frame_id)
                return True
            except Exception as error:
                self._fail(project_id, shot_id, role, job_id, str(error))
                return False

    def run_pair(self, project_id: str, shot_id: str, group_id: str, first_job_id: str, last_job_id: str) -> None:
        active_key = (project_id, group_id)
        with _ACTIVE_GROUPS_LOCK:
            if active_key in _ACTIVE_GROUPS:
                return
            _ACTIVE_GROUPS.add(active_key)
        try:
            self._run_pair(project_id, shot_id, group_id, first_job_id, last_job_id)
        finally:
            with _ACTIVE_GROUPS_LOCK:
                _ACTIVE_GROUPS.discard(active_key)

    def _run_pair(self, project_id: str, shot_id: str, group_id: str, first_job_id: str, last_job_id: str) -> None:
        first_completed = self.run(project_id, shot_id, "first", first_job_id)
        if not first_completed:
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                shot = next(item for item in project.shots if item.id == shot_id)
                first_job = shot.frames["first"].job
                last_job = shot.frames["last"].job
                if first_job and first_job.id == first_job_id and first_job.status == "complete":
                    first = self._selected(shot, "first")
                else:
                    first = None
                if not first and last_job and last_job.id == last_job_id and last_job.groupId == group_id:
                    last_job.status = "failed"
                    last_job.errorMessage = first_job.errorMessage if first_job else "首帧生成失败，未调用尾帧模型"
                    self.store.save(project)
                    return
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next(item for item in project.shots if item.id == shot_id)
            first = self._selected(shot, "first")
            last_job = shot.frames["last"].job
            if not first or not last_job or last_job.id != last_job_id or last_job.groupId != group_id:
                return
            if last_job.status != "queued":
                return
            last_job.inputSnapshot["firstFrameVersionId"] = first.id
            last_job.inputSnapshot["firstFramePath"] = first.path
            self.store.save(project)
        first_bytes = self._read(project_id, first.path)
        self.run(project_id, shot_id, "last", last_job_id, (first_bytes, "image/webp", first.id))

    def select_version(self, project: Project, shot: Shot, role: str, version_id: str) -> None:
        slot = shot.frames[role]
        version = next((item for item in slot.versions if item.id == version_id), None)
        if not version or not self._safe_path(project.projectId, version.path).is_file():
            raise ValueError("图片版本不存在")
        if slot.selectedVersionId == version.id:
            return
        slot.selectedVersionId = version.id
        setattr(shot.uploads, "firstFrame" if role == "first" else "lastFrame", version.path)
        shot.video = None
        project.finalVideoPath = None

    def _snapshot(self, project: Project, shot: Shot, role: str) -> dict[str, Any]:
        slot = shot.frames[role]
        references, missing = resolve_asset_references(project, shot, slot.referenceMode, slot.assetIds)
        if missing:
            raise ValueError(f"请先上传参考资产：{'、'.join(missing)}")
        if not references:
            raise ValueError("请先上传此镜头需要的角色或场景参考图")
        if len(references) > 13:
            raise ValueError("参考图片最多选择 13 张")
        prompt = getattr(shot, f"{role}FramePrompt").strip()
        if not prompt:
            raise ValueError("请先填写首尾帧生成提示词")
        snapshot = {
            "prompt": prompt,
            "projectType": project.projectType,
            "aspectRatio": project.aspectRatio,
            "style": project.style,
            "model": self.settings.google_image_model,
            "references": [{"assetId": asset.id, "imageId": asset.image.imageId, "path": asset.image.path, "mimeType": asset.image.mimeType, "name": asset.name} for asset in references if asset.image],
        }
        if role == "last":
            first = self._selected(shot, "first")
            if first:
                snapshot["firstFrameVersionId"] = first.id
                snapshot["firstFramePath"] = first.path
        return snapshot

    def _prompt(self, snapshot: dict[str, Any], role: str, project_id: str, shot_id: str) -> str:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next(item for item in project.shots if item.id == shot_id)
            description = shot.firstFrameDescription if role == "first" else shot.lastFrameDescription
            continuity = shot.continuityNotes
        labels = "；".join(reference["name"] for reference in snapshot["references"])
        frame_position = "视频开始瞬间" if role == "first" else "视频结束瞬间"
        reference_continuity = (
            "保持参考图中的主体形态、比例和场景特征。"
            if is_science(snapshot.get("projectType", "story"))
            else "保持参考图中的身份、服装、场景视觉特征。"
        )
        return (
            f"生成一张 {snapshot['aspectRatio']} 画幅的电影分镜静帧，表现{frame_position}。整体风格：{snapshot['style']}。"
            f"镜头状态：{description}。用户提示词：{snapshot['prompt']}。连续性要求：{continuity}。"
            f"参考图主体或场景标签：{labels}。{reference_continuity}画面中不要生成文字、字幕或水印。"
            f"{visual_constraint(snapshot.get('projectType', 'story'))}"
        )

    def _complete(self, project_id: str, shot_id: str, role: str, job_id: str, snapshot: dict[str, Any], version_id: str, path: str, first_frame_id: str | None) -> None:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next(item for item in project.shots if item.id == shot_id)
            slot = shot.frames[role]
            if not slot.job or slot.job.id != job_id:
                self._safe_path(project_id, path).unlink(missing_ok=True)
                return
            signature = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
            version = FrameVersion(
                id=version_id, path=path, model=snapshot["model"], promptSnapshot=snapshot["prompt"],
                inputSignature=signature, referenceSnapshots=[f"{item['assetId']}:{item['imageId']}" for item in snapshot["references"]],
                firstFrameVersionId=first_frame_id,
            )
            slot.versions.append(version)
            slot.selectedVersionId = version.id
            slot.job.status = "complete"
            slot.job.errorMessage = None
            setattr(shot.uploads, "firstFrame" if role == "first" else "lastFrame", path)
            shot.video = None
            project.finalVideoPath = None
            self.store.save(project)

    def _fail(self, project_id: str, shot_id: str, role: str, job_id: str, message: str) -> None:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next(item for item in project.shots if item.id == shot_id)
            job = shot.frames[role].job
            if job and job.id == job_id:
                job.status = "failed"
                job.errorMessage = message[:2000]
                self.store.save(project)

    def _selected(self, shot: Shot, role: str) -> FrameVersion | None:
        slot = shot.frames[role]
        return next((item for item in slot.versions if item.id == slot.selectedVersionId), None)

    def _read(self, project_id: str, relative_path: str) -> bytes:
        return self._safe_path(project_id, relative_path).read_bytes()

    def _safe_path(self, project_id: str, relative_path: str) -> Path:
        root = self.store.project_dir(project_id).resolve()
        path = (root / relative_path).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError("图片文件不存在")
        return path

    def _semaphore(self) -> threading.BoundedSemaphore:
        key = (str(self.store.root.resolve()), self.settings.google_image_max_concurrency)
        with _SEMAPHORE_LOCK:
            return _SEMAPHORES.setdefault(key, threading.BoundedSemaphore(key[1]))
