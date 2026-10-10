from __future__ import annotations

from pathlib import Path
from typing import Any

from app.clients.google_omni_video import GoogleOmniVideoClient
from app.config import Settings
from app.domain.models import Project, Shot, ShotVideo
from app.store.project_store import ProjectStore


class VideoService:
    def __init__(self, settings: Settings, store: ProjectStore, *, client: Any | None = None) -> None:
        self.settings = settings
        self.store = store
        self.client = client or GoogleOmniVideoClient(settings)

    def mark_submitting(self, project: Project, shot: Shot) -> None:
        shot.video = ShotVideo(model=self.settings.google_omni_model, status="submitting")
        self.store.save(project)

    def run(self, project_id: str, shot_id: str) -> None:
        project = self.store.get(project_id)
        shot = next(item for item in project.shots if item.id == shot_id)
        try:
            shot.video = ShotVideo(model=self.settings.google_omni_model, status="submitting")
            self.store.save(project)
            first = self._path(project_id, shot.uploads.firstFrame)
            last = self._path(project_id, shot.uploads.lastFrame)
            job_id = self.client.create_interaction(
                prompt=shot.prompt,
                first_frame=first,
                last_frame=last,
                aspect_ratio=project.aspectRatio,
                duration_seconds=shot.durationSeconds,
            )
            shot.video.remoteJobId = job_id
            shot.video.status = "generating"
            self.store.save(project)
            output = self.store.project_dir(project_id) / "videos" / f"{shot_id}.mp4"
            interaction = self.client.wait_for_completion(job_id)
            shot.video.status = "downloading"
            self.store.save(project)
            self.client.save_video(interaction, output)
            shot.video.status = "complete"
            shot.video.path = str(output.relative_to(self.store.project_dir(project_id)))
            self.store.save(project)
        except Exception as error:
            project = self.store.get(project_id)
            shot = next(item for item in project.shots if item.id == shot_id)
            shot.video = shot.video or ShotVideo(model=self.settings.google_omni_model)
            shot.video.status = "failed"
            shot.video.errorMessage = str(error)
            self.store.save(project)

    def _path(self, project_id: str, relative_path: str | None) -> Path:
        if not relative_path:
            raise ValueError("请先上传首帧和尾帧")
        path = (self.store.project_dir(project_id) / relative_path).resolve()
        root = self.store.project_dir(project_id).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

