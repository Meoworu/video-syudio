from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.config import Settings, get_settings
from app.domain.models import CreateProjectRequest, Project
from app.services.director_service import DirectorService
from app.services.narration_service import NarrationService
from app.services.video_service import VideoService
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


@router.post("/{project_id}/narration/manuscript", response_model=Project)
def generate_narration_manuscript(
    project_id: str,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    return NarrationService(settings, store).generate_manuscript(get_project(project_id, store))


@router.post("/{project_id}/narration/audio", response_model=Project)
def generate_narration_audio(
    project_id: str,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    return NarrationService(settings, store).synthesize_audio(get_project(project_id, store))


@router.post("/{project_id}/shots/{shot_id}/generate-video", response_model=Project)
def generate_video(
    project_id: str,
    shot_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    project = get_project(project_id, store)
    shot = next((item for item in project.shots if item.id == shot_id), None)
    if shot is None:
        raise HTTPException(status_code=404, detail="镜头不存在")
    if not shot.uploads.firstFrame or not shot.uploads.lastFrame:
        raise HTTPException(status_code=400, detail="请先上传首帧和尾帧")
    VideoService(settings, store).mark_submitting(project, shot)
    background_tasks.add_task(VideoService(settings, store).run, project_id, shot_id)
    return store.get(project_id)

