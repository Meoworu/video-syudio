from __future__ import annotations

import mimetypes
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.domain.models import CreateProjectRequest, FrameVersion, Project, ShotVideo, UpdateShotRequest
from app.services.director_service import DirectorService
from app.services.assembly_service import AssemblyService
from app.services.editing import rebuild_edit_plan
from app.services.narration_service import NarrationService
from app.services.video_service import VideoService
from app.store.project_store import ProjectStore


router = APIRouter(prefix="/projects", tags=["projects"])


def get_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings.video_studio_data_dir)


@router.post("", response_model=Project)
def create_project(
    payload: CreateProjectRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    service = DirectorService(settings)
    project = service.start_project(payload, store)
    background_tasks.add_task(service.run_project, project.projectId, store)
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
    except ValueError as error:
        raise HTTPException(status_code=400, detail="项目 ID 无效") from error


@router.delete("/{project_id}")
def delete_project(project_id: str, store: ProjectStore = Depends(get_store)) -> dict[str, object]:
    try:
        store.project_dir(project_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="项目 ID 无效") from error

    with store.lock(project_id):
        directory = store.project_dir(project_id)
        if directory.is_symlink() or directory.resolve().parent != store.root.resolve():
            raise HTTPException(status_code=400, detail="项目目录无效，拒绝删除")
        project = get_project(project_id, store)
        active_video_statuses = {"submitting", "generating", "downloading"}
        if VideoService.has_active_job(store, project_id) or project.status == "generating" or any(
            shot.video and shot.video.status in active_video_statuses or any(
                shot.frames[role].job and shot.frames[role].job.status in {"queued", "generating"} for role in ("first", "last")
            ) for shot in project.shots
        ):
            raise HTTPException(status_code=409, detail="项目仍有运行中的任务，请完成或取消任务后再删除")
        try:
            store.delete_project(project_id)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="项目不存在") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail="项目目录无效，拒绝删除") from error
    return {"projectId": project_id, "deleted": True}


@router.post("/{project_id}/director/retry", response_model=Project)
def retry_director(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        if not project.directorRequest or project.status == "generating":
            raise HTTPException(status_code=409, detail="项目没有可恢复的导演任务")
        project.status = "generating"
        project.directorStage = "shot_design" if project.directorOutline else "outline"
        project.errorMessage = None
        store.save(project)
        background_tasks.add_task(DirectorService(settings).run_project, project_id, store)
        return project


@router.get("/{project_id}/files/{relative_path:path}")
def get_project_file(project_id: str, relative_path: str, store: ProjectStore = Depends(get_store)) -> FileResponse:
    try:
        root = store.project_dir(project_id).resolve()
    except ValueError as error:
        raise HTTPException(status_code=400, detail="项目 ID 无效") from error
    if relative_path.split("/", 1)[0] not in {"assets", "frames", "videos", "audio", "final"}:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


@router.post("/{project_id}/shots/{shot_id}/frames/{role}")
async def upload_frame(
    project_id: str,
    shot_id: str,
    role: str,
    request: Request,
    store: ProjectStore = Depends(get_store),
) -> dict[str, str]:
    if role not in {"first", "last"}:
        raise HTTPException(status_code=400, detail="只支持 first 或 last 帧")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    suffix = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(content_type)
    if not suffix:
        raise HTTPException(status_code=400, detail="只支持 PNG、JPG 或 WebP")
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > 6_000_000:
        raise HTTPException(status_code=413, detail="图片不能为空且不能超过 6 MB")
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 6_000_000:
            raise HTTPException(status_code=413, detail="图片不能为空且不能超过 6 MB")
    content = bytes(chunks)
    if not content:
        raise HTTPException(status_code=400, detail="图片不能为空且不能超过 6 MB")
    signatures = {".png": b"\x89PNG\r\n\x1a\n", ".jpg": b"\xff\xd8\xff", ".webp": b"RIFF"}
    if not content.startswith(signatures[suffix]) or (suffix == ".webp" and content[8:12] != b"WEBP"):
        raise HTTPException(status_code=400, detail="图片内容与文件类型不匹配")
    from app.services.asset_service import InvalidImageError, normalize_image
    try:
        normalized, _, _ = await run_in_threadpool(normalize_image, content, content_type)
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    def persist_frame() -> dict[str, str]:
        with store.lock(project_id):
            project = get_project(project_id, store)
            shot = next((item for item in project.shots if item.id == shot_id), None)
            if not shot:
                raise HTTPException(status_code=404, detail="镜头不存在")
            if shot.video and shot.video.status in {"submitting", "generating", "downloading"}:
                raise HTTPException(status_code=409, detail="视频任务执行中，暂不能替换首尾帧")
            if shot.frames[role].job and shot.frames[role].job.status in {"queued", "generating"}:
                raise HTTPException(status_code=409, detail="图片正在生成，暂不能替换首尾帧")
            version_id = uuid.uuid4().hex
            relative_path = f"frames/{shot_id}/{role}/{version_id}.webp"
            store.save_media(project_id, relative_path, normalized)
            slot = shot.frames[role]
            slot.versions.append(FrameVersion(id=version_id, path=relative_path, source="upload", model="manual", promptSnapshot=getattr(shot, f"{role}FramePrompt")))
            slot.selectedVersionId = version_id
            setattr(shot.uploads, f"{role}Frame", relative_path)
            shot.video = None
            project.finalVideoPath = None
            store.save(project)
            return {"projectId": project_id, "shotId": shot_id, "role": role, "path": relative_path}

    return await run_in_threadpool(persist_frame)


@router.post("/{project_id}/narration/manuscript", response_model=Project)
def generate_narration_manuscript(
    project_id: str,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        return NarrationService(settings, store).generate_manuscript(get_project(project_id, store))


@router.post("/{project_id}/narration/audio", response_model=Project)
def generate_narration_audio(
    project_id: str,
    speed: float = Query(default=1.0, ge=0.5, le=2.0),
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        return NarrationService(settings, store).synthesize_audio(get_project(project_id, store), speed=speed)


@router.post("/{project_id}/narration/takes/{take_id}/select", response_model=Project)
def select_narration_take(
    project_id: str,
    take_id: str,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        try:
            return NarrationService(settings, store).select_take(project, take_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="旁白文件不存在") from error


@router.put("/{project_id}/narration/manuscript", response_model=Project)
def update_narration_manuscript(
    project_id: str,
    manuscript: str = Body(..., embed=True, min_length=1),
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        try:
            return NarrationService(settings, store).update_manuscript(project, manuscript)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/{project_id}/shots/{shot_id}/generate-video", response_model=Project)
def generate_video(
    project_id: str,
    shot_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if shot is None:
            raise HTTPException(status_code=404, detail="镜头不存在")
        if not shot.uploads.firstFrame or not shot.uploads.lastFrame:
            raise HTTPException(status_code=400, detail="请先上传首帧和尾帧")
        if shot.video and shot.video.status in {"submitting", "generating", "downloading"}:
            return project
        if any(shot.frames[role].job and shot.frames[role].job.status in {"queued", "generating"} for role in ("first", "last")):
            raise HTTPException(status_code=409, detail="首尾帧生成期间不能提交视频任务")
        VideoService(settings, store).mark_submitting(project, shot)
        background_tasks.add_task(VideoService(settings, store).run, project_id, shot_id)
        return store.get(project_id)


@router.put("/{project_id}/shots/{shot_id}", response_model=Project)
def update_shot(
    project_id: str,
    shot_id: str,
    payload: UpdateShotRequest,
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if not shot:
            raise HTTPException(status_code=404, detail="镜头不存在")
        if shot.video and shot.video.status in {"submitting", "generating", "downloading"}:
            raise HTTPException(status_code=409, detail="视频任务执行中，暂不能修改镜头")
        if any(shot.frames[role].job and shot.frames[role].job.status in {"queued", "generating"} for role in ("first", "last")):
            raise HTTPException(status_code=409, detail="首尾帧生成期间不能修改镜头")
        changes = payload.model_dump(exclude_unset=True)
        if not changes:
            return project
        for key, value in changes.items():
            setattr(shot, key, value)
        shot.video = None
        project.finalVideoPath = None
        rebuild_edit_plan(project)
        if project.narration.sentences:
            from app.services.narration_timing import align_narration
            try:
                aligned, cues, target, estimated = align_narration(project, project.narration.sentences)
            except ValueError as error:
                raise HTTPException(status_code=409, detail=f"镜头时长变更后旁白需重新审核：{error}") from error
            project.narration.sentences = aligned
            project.narration.alignment = cues
            project.narration.targetDurationSeconds = target
            project.narration.estimatedDurationSeconds = estimated
            project.narration.audioPath = None
            project.narration.audioDurationSeconds = None
            project.narration.selectedTakeId = None
            project.narration.status = "draft"
        store.save(project)
        return project


@router.post("/{project_id}/generate-videos", response_model=Project)
def generate_all_videos(
    project_id: str,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        pending = []
        for shot in project.shots:
            if not shot.uploads.firstFrame or not shot.uploads.lastFrame:
                continue
            if shot.video and shot.video.status in {"submitting", "generating", "downloading", "complete"}:
                continue
            if any(shot.frames[role].job and shot.frames[role].job.status in {"queued", "generating"} for role in ("first", "last")):
                continue
            shot.video = ShotVideo(model=settings.google_omni_model, status="submitting")
            pending.append(shot.id)
        if not pending:
            raise HTTPException(status_code=409, detail="没有可提交的视频镜头；请检查首尾帧和任务状态")
        project.finalVideoPath = None
        store.save(project)
        background_tasks.add_task(VideoService(settings, store).run_batch, project_id, pending)
        return project


@router.post("/{project_id}/shots/{shot_id}/cancel-video", response_model=Project)
def cancel_video(
    project_id: str,
    shot_id: str,
    settings: Settings = Depends(get_settings),
    store: ProjectStore = Depends(get_store),
) -> Project:
    try:
        VideoService(settings, store).cancel(project_id, shot_id)
        return get_project(project_id, store)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{project_id}/shots/{shot_id}/video", response_model=Project)
def delete_failed_video(
    project_id: str,
    shot_id: str,
    store: ProjectStore = Depends(get_store),
) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if shot is None:
            raise HTTPException(status_code=404, detail="镜头不存在")
        if not shot.video or shot.video.status != "failed":
            raise HTTPException(status_code=409, detail="只能删除生成失败的任务")
        if shot.video.path:
            root = store.project_dir(project_id).resolve()
            relative_path = shot.video.path
            candidate = root / relative_path
            if relative_path.split("/", 1)[0] != "videos" or candidate.is_symlink():
                raise HTTPException(status_code=400, detail="视频路径无效，拒绝删除")
            video_path = candidate.resolve()
            if root not in video_path.parents:
                raise HTTPException(status_code=400, detail="视频路径无效，拒绝删除")
            if video_path.is_file():
                video_path.unlink()
        shot.video = None
        store.save(project)
        return project


@router.get("/videos/jobs")
def list_videos(store: ProjectStore = Depends(get_store)) -> list[dict[str, object]]:
    return [
        {"projectId": project.projectId, "projectTitle": project.title, "shotId": shot.id,
         "shotTitle": shot.title, "status": shot.video.status, "path": shot.video.path,
         "errorMessage": shot.video.errorMessage}
        for project in store.list() for shot in project.shots if shot.video
    ]


@router.post("/{project_id}/assemble", response_model=Project)
def assemble_project(project_id: str, settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    with store.lock(project_id):
        project = get_project(project_id, store)
        try:
            return AssemblyService(settings, store).assemble(project)
        except (ValueError, RuntimeError, FileNotFoundError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

