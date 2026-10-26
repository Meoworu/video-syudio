from __future__ import annotations

import uuid
from typing import Any

from app.clients.google_image import GoogleImageClient
from app.config import Settings
from app.domain.models import FrameJob, Project, ProjectAsset
from app.services.asset_service import build_asset_image_prompt, normalize_image, save_asset_image
from app.services.image_generation_limits import image_generation_semaphore
from app.store.project_store import ProjectStore


class AssetImageService:
    def __init__(self, settings: Settings, store: ProjectStore, *, client: Any | None = None) -> None:
        self.settings = settings
        self.store = store
        self.client = client or GoogleImageClient(settings)

    def enqueue(self, project: Project, asset: ProjectAsset, request_id: str) -> str:
        job = asset.imageJob
        if job and job.requestId == request_id:
            return job.id
        if job and job.status in {"queued", "generating"}:
            raise ValueError("此资产已有图片生成任务正在执行")
        snapshot = {
            "prompt": build_asset_image_prompt(project, asset),
            "aspectRatio": project.aspectRatio,
            "model": self.settings.google_image_model,
        }
        asset.imageJob = FrameJob(id=uuid.uuid4().hex, requestId=request_id, inputSnapshot=snapshot)
        return asset.imageJob.id

    def run(self, project_id: str, asset_id: str, job_id: str) -> bool:
        with self.store.lock(project_id):
            project = self.store.get(project_id)
            asset = next((item for item in project.assets if item.id == asset_id), None)
            if not asset or not asset.imageJob or asset.imageJob.id != job_id or asset.imageJob.status != "queued":
                return False
            asset.imageJob.status = "generating"
            snapshot = dict(asset.imageJob.inputSnapshot)
            self.store.save(project)
        try:
            with image_generation_semaphore(self.settings, self.store):
                image_bytes, image_mime = self.client.generate(snapshot["prompt"], [], snapshot["aspectRatio"])
            normalized, width, height = normalize_image(image_bytes, image_mime)
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                asset = next((item for item in project.assets if item.id == asset_id), None)
                if not asset or not asset.imageJob or asset.imageJob.id != job_id:
                    return False
                save_asset_image(self.store, project_id, asset, normalized, width, height)
                asset.imageJob.status = "complete"
                asset.imageJob.errorMessage = None
                self.store.save(project)
            return True
        except Exception as error:
            with self.store.lock(project_id):
                project = self.store.get(project_id)
                asset = next((item for item in project.assets if item.id == asset_id), None)
                if asset and asset.imageJob and asset.imageJob.id == job_id:
                    asset.imageJob.status = "failed"
                    asset.imageJob.errorMessage = str(error)[:2000]
                    self.store.save(project)
            return False
