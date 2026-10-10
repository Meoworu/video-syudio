from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.domain.models import CreateProjectRequest, Project
from app.services.director_service import DirectorService
from app.store.project_store import ProjectStore


router = APIRouter(prefix="/projects", tags=["projects"])


def get_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings.video_studio_data_dir)


@router.post("", response_model=Project)
def create_project(payload: CreateProjectRequest, settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    project = DirectorService(settings).create_project(payload)
    store.create(project)
    return project


@router.get("", response_model=list[Project])
def list_projects(store: ProjectStore = Depends(get_store)) -> list[Project]:
    return store.list()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, store: ProjectStore = Depends(get_store)) -> Project:
    try:
        return store.get(project_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="项目不存在") from error


@router.post("/{project_id}/shots/{shot_id}/frames/{role}")
async def upload_frame(
    project_id: str,
    shot_id: str,
    role: str,
    request: Request,
    store: ProjectStore = Depends(get_store),
) -> dict[str, str]:
    project = get_project(project_id, store)
    if not any(shot.id == shot_id for shot in project.shots):
        raise HTTPException(status_code=404, detail="镜头不存在")
    if role not in {"first", "last"}:
        raise HTTPException(status_code=400, detail="只支持 first 或 last 帧")
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(request.headers.get("content-type", "").split(";", 1)[0].lower(), ".png")
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="只支持 PNG、JPG 或 WebP")
    path = store.save_upload(project_id, shot_id, role, await request.body(), suffix)
    shot = next(shot for shot in project.shots if shot.id == shot_id)
    setattr(shot.uploads, f"{role}Frame", str(path.relative_to(store.project_dir(project_id))))
    store.save(project)
    return {"projectId": project_id, "shotId": shot_id, "role": role, "path": str(path)}

