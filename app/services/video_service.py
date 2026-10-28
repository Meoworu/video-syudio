from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from app.clients.google_omni_video import GoogleOmniVideoCancelled, GoogleOmniVideoClient
from app.config import Settings
from app.domain.models import Project, Shot, ShotVideo
from app.services.project_type_policy import visual_constraint
from app.services.timeline_invalidation import invalidate_picture_timeline
from app.store.project_store import ProjectStore


_ACTIVE_VIDEO_JOBS: set[tuple[str, str, str]] = set()
_ACTIVE_VIDEO_JOBS_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)


class VideoService:
    def __init__(self, settings: Settings, store: ProjectStore, *, client: Any | None = None) -> None:
        self.settings = settings
        self.store = store
        self.client = client or GoogleOmniVideoClient(settings)

    def validate_configuration(self) -> None:
        if not self.settings.google_cloud_project:
            raise ValueError("未配置 GOOGLE_CLOUD_PROJECT，请填写关联 Cloud 赠金的项目 ID")
        if self.settings.google_omni_model != "gemini-omni-1.1-flash-preview":
            raise ValueError("当前视频模型只支持 gemini-omni-1.1-flash-preview，请更新 GOOGLE_OMNI_MODEL")

    def mark_submitting(self, project: Project, shot: Shot) -> None:
        self.validate_configuration()
        shot.video = ShotVideo(provider="google_agent_platform_omni_1_1", model=self.settings.google_omni_model, status="submitting")
        self.store.save(project)

    def run_batch(self, project_id: str, shot_ids: list[str]) -> None:
        for shot_id in shot_ids:
            self.run(project_id, shot_id)

    @staticmethod
    def has_active_job(store: ProjectStore, project_id: str) -> bool:
        root = str(store.root.resolve())
        with _ACTIVE_VIDEO_JOBS_LOCK:
            return any(active_root == root and active_project == project_id for active_root, active_project, _ in _ACTIVE_VIDEO_JOBS)

    def run(self, project_id: str, shot_id: str) -> None:
        active_key = (str(self.store.root.resolve()), project_id, shot_id)
        with _ACTIVE_VIDEO_JOBS_LOCK:
            if active_key in _ACTIVE_VIDEO_JOBS:
                return
            _ACTIVE_VIDEO_JOBS.add(active_key)
        try:
            self._run(project_id, shot_id)
        finally:
            with _ACTIVE_VIDEO_JOBS_LOCK:
                _ACTIVE_VIDEO_JOBS.discard(active_key)

    def _run(self, project_id: str, shot_id: str) -> None:
        job_id: str | None = None
        try:
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                shot = next(item for item in project.shots if item.id == shot_id)
                if shot.video and shot.video.status == "cancelled":
                    return
                if shot.video and shot.video.status == "complete":
                    return
                if shot.video and shot.video.provider != "google_agent_platform_omni_1_1":
                    raise ValueError("此任务属于旧服务端点，不能用 Agent Platform Omni 1.1 恢复；请在原平台处理后重新提交")
                job_id = shot.video.remoteJobId if shot.video else None
                if not job_id:
                    self.validate_configuration()
                    shot.video = ShotVideo(provider="google_agent_platform_omni_1_1", model=self.settings.google_omni_model, status="submitting")
                    project.finalVideoPath = None
                    self.store.save(project)
                first = self._path(project_id, shot.uploads.firstFrame)
                last = self._path(project_id, shot.uploads.lastFrame)
                aspect_ratio, prompt, duration = project.aspectRatio, shot.prompt, shot.durationSeconds
                prompt = f"{prompt}\n{visual_constraint(project.projectType)}".strip()
            if not job_id:
                job_id = self.client.create_interaction(
                    prompt=prompt, first_frame=first, last_frame=last,
                    aspect_ratio=aspect_ratio, duration_seconds=duration,
                )
                with self.store.lock(project_id):
                    project = self.store.get(project_id)
                    shot = next(item for item in project.shots if item.id == shot_id)
                    if shot.video and shot.video.status == "cancelled":
                        try:
                            self.client.cancel_interaction(job_id)
                        except Exception as cancel_error:
                            shot.video.remoteJobId = job_id
                            shot.video.status = "generating"
                            shot.video.errorMessage = f"远端取消失败，任务可能仍在运行，请重试取消：{cancel_error}"
                            self.store.save(project)
                        return
                    shot.video.remoteJobId = job_id
                    shot.video.status = "generating"
                    self.store.save(project)
            else:
                with self.store.lock(project_id):
                    project = self.store.get(project_id)
                    shot = next(item for item in project.shots if item.id == shot_id)
                    shot.video.status = "generating"
                    self.store.save(project)
            interaction = self.client.wait_for_completion(job_id)
            remote_status = str(getattr(interaction, "status", "") or (interaction.get("status") if isinstance(interaction, dict) else "")).lower()
            if remote_status in {"cancelled", "canceled"}:
                with self.store.lock(project_id):
                    project = self.store.get(project_id)
                    shot = next(item for item in project.shots if item.id == shot_id)
                    shot.video.status = "cancelled"
                    self.store.save(project)
                return
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                shot = next(item for item in project.shots if item.id == shot_id)
                if shot.video.status == "cancelled":
                    return
                shot.video.status = "downloading"
                self.store.save(project)
            output = self.store.project_dir(project_id) / "videos" / f"{shot_id}.mp4"
            self.client.save_video(
                interaction,
                output,
                cancel_check=lambda: self._is_cancelled(project_id, shot_id),
            )
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                shot = next(item for item in project.shots if item.id == shot_id)
                if shot.video.status == "cancelled":
                    output.unlink(missing_ok=True)
                    shot.video.path = None
                    self.store.save(project)
                    return
                shot.video.status = "complete"
                shot.video.path = str(output.relative_to(self.store.project_dir(project_id)))
                invalidate_picture_timeline(project)
                self.store.save(project)
        except GoogleOmniVideoCancelled:
            return
        except Exception as error:
            try:
                with self.store.lock(project_id):
                    project = self.store.get(project_id)
                    shot = next(item for item in project.shots if item.id == shot_id)
                    if shot.video and shot.video.status == "cancelled":
                        return
                    shot.video = shot.video or ShotVideo(provider="google_agent_platform_omni_1_1", model=self.settings.google_omni_model)
                    shot.video.status = "failed"
                    shot.video.errorMessage = str(error)
                    self.store.save(project)
            except FileNotFoundError:
                if job_id:
                    try:
                        self.client.cancel_interaction(job_id)
                    except Exception as cancel_error:
                        _LOGGER.warning(
                            "Failed to cancel orphaned video job project=%s shot=%s job=%s error=%s",
                            project_id, shot_id, job_id, cancel_error,
                        )
                return

    def _path(self, project_id: str, relative_path: str | None) -> Path:
        if not relative_path:
            raise ValueError("请先上传首帧和尾帧")
        path = (self.store.project_dir(project_id) / relative_path).resolve()
        root = self.store.project_dir(project_id).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

    def _is_cancelled(self, project_id: str, shot_id: str) -> bool:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next((item for item in project.shots if item.id == shot_id), None)
            return bool(shot and shot.video and shot.video.status == "cancelled")

    def cancel(self, project_id: str, shot_id: str) -> None:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next((item for item in project.shots if item.id == shot_id), None)
            if not shot or not shot.video:
                raise ValueError("镜头没有正在运行的视频任务")
            if shot.video.status not in {"submitting", "generating", "downloading"}:
                raise ValueError("镜头视频任务当前不可取消")
            if shot.video.provider != "google_agent_platform_omni_1_1":
                raise ValueError("此任务属于旧服务端点，不能用 Agent Platform Omni 1.1 取消；请在原服务平台处理后重新提交")
            remote_job_id = shot.video.remoteJobId
            if not remote_job_id:
                shot.video.status = "cancelled"
                self.store.save(project)
                return
        self.client.cancel_interaction(remote_job_id)
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            shot = next(item for item in project.shots if item.id == shot_id)
            shot.video.status = "cancelled"
            self.store.save(project)

