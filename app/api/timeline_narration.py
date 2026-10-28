from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.domain.models import MediaJobRequest, NarrationWindowAudioRequest, Project, SaveNarrationWindowsRequest
from app.services.media_job_service import (
    active_media_job, enqueue_media_job, run_narration_audio_job, run_preview_job, run_windows_job,
    signature, timeline_snapshot, touch_job,
)
from app.services.narration_windows_service import validate_windows
from app.store.project_store import ProjectStore


router = APIRouter(prefix="/projects", tags=["timeline-narration"])


def get_store(settings: Settings = Depends(get_settings)) -> ProjectStore:
    return ProjectStore(settings.video_studio_data_dir)


def _project(store: ProjectStore, project_id: str) -> Project:
    try:
        return store.get(project_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="项目不存在") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail="项目 ID 无效") from error


def _ensure_enabled(settings: Settings) -> None:
    if not settings.narration_time_windows_enabled:
        raise HTTPException(status_code=404, detail="画面时间窗旁白功能当前未启用")


@router.post("/{project_id}/preview", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
def create_preview(project_id: str, payload: MediaJobRequest, background_tasks: BackgroundTasks,
                   settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    _ensure_enabled(settings)
    with store.lock(project_id):
        project = _project(store, project_id)
        if not project.shots or any(not shot.video or shot.video.status != "complete" or not shot.video.path for shot in project.shots):
            raise HTTPException(status_code=409, detail="请先完成所有分镜视频生成")
        snapshot = timeline_snapshot(project)
        input_signature = signature(snapshot)
        try:
            job, created = enqueue_media_job(project, kind="preview", request_id=payload.requestId,
                                             snapshot={"project": project.model_dump(mode="json")}, input_signature=input_signature)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        store.save(project)
        if created:
            background_tasks.add_task(run_preview_job, project_id, job.id, settings, store)
        return project


@router.post("/{project_id}/narration/windows/plan", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
def plan_windows(project_id: str, payload: MediaJobRequest, background_tasks: BackgroundTasks,
                 settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    _ensure_enabled(settings)
    with store.lock(project_id):
        project = _project(store, project_id)
        if not project.preview or project.preview.status != "ready":
            raise HTTPException(status_code=409, detail="请先生成有效的无旁白剪辑预览")
        inputs = {"previewId": project.preview.id, "story": project.story,
                  "script": project.productionScript.model_dump(mode="json") if project.productionScript else None}
        try:
            job, created = enqueue_media_job(project, kind="windows", request_id=payload.requestId,
                                             snapshot={"project": project.model_dump(mode="json")}, input_signature=signature(inputs))
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        store.save(project)
        if created:
            background_tasks.add_task(run_windows_job, project_id, job.id, settings, store)
        return project


@router.put("/{project_id}/narration/windows", response_model=Project)
def save_windows(project_id: str, payload: SaveNarrationWindowsRequest,
                 settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    _ensure_enabled(settings)
    with store.lock(project_id):
        project = _project(store, project_id)
        if active_media_job(project):
            raise HTTPException(status_code=409, detail="媒体任务执行中，暂不能修改旁白时间窗")
        if not project.preview or project.preview.id != payload.previewId or project.preview.status != "ready":
            raise HTTPException(status_code=409, detail="剪辑预览已更新，请重新加载时间窗")
        if project.narration.windowRevision != payload.expectedRevision:
            raise HTTPException(status_code=409, detail="旁白时间窗已被其他操作更新，请刷新后重试")
        try:
            if not payload.windows:
                raise ValueError("至少需要创建一个旁白时间窗")
            if len({window.id for window in payload.windows}) != len(payload.windows):
                raise ValueError("旁白时间窗 ID 不能重复")
            previous = {window.id: window for window in project.narration.windows}
            for window in payload.windows:
                old = previous.get(window.id)
                if old is None or old.text != window.text:
                    window.textLocked = True
            allowed_frames = {item.get("id") for item in project.preview.evidenceFrames}
            windows = validate_windows(payload.windows, project.preview, valid_frame_ids=allowed_frames, require_ready=True)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        project.narration.windows = windows
        project.narration.mode = "windowed"
        project.narration.windowRevision += 1
        project.narration.takes = [item.model_copy(update={"status": "ready"}) if item.id == project.narration.selectedTakeId else item for item in project.narration.takes]
        project.narration.audioPath = None
        project.narration.audioDurationSeconds = None
        project.narration.selectedTakeId = None
        project.narration.status = "draft"
        if project.finalRender:
            project.finalRender.isCurrent = False
        project.finalVideoPath = None
        store.save(project)
        return project


@router.post("/{project_id}/narration/window-audio", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
def generate_window_audio(project_id: str, payload: NarrationWindowAudioRequest, background_tasks: BackgroundTasks,
                          settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    _ensure_enabled(settings)
    with store.lock(project_id):
        project = _project(store, project_id)
        prior = next((job for job in project.mediaJobs if job.kind == "audio" and job.requestId == payload.requestId), None)
        if prior:
            prior_snapshot = prior.inputSnapshot
            prior_project = prior_snapshot.get("project", {})
            prior_narration = prior_project.get("narration", {})
            prior_preview = prior_project.get("preview") or {}
            if (prior_narration.get("windowRevision") != payload.expectedRevision
                    or prior_preview.get("id") != payload.previewId
                    or prior_snapshot.get("speed") != payload.speed
                    or prior_snapshot.get("windowIds") != payload.windowIds
                    or prior_snapshot.get("forceRegenerate", False) != payload.forceRegenerate):
                raise HTTPException(status_code=409, detail="相同 requestId 已用于不同的配音请求")
            return project
        if active_media_job(project):
            raise HTTPException(status_code=409, detail="已有媒体任务执行中")
        if (project.narration.mode != "windowed" or not project.preview or project.preview.status != "ready"
                or project.preview.id != payload.previewId):
            raise HTTPException(status_code=409, detail="请先生成预览并确认旁白时间窗")
        if project.narration.windowRevision != payload.expectedRevision:
            raise HTTPException(status_code=409, detail="旁白时间窗已更新，请刷新后重新发起配音")
        allowed_window_states = {"ready", "complete", "needs_edit", "failed"}
        if not project.narration.windows or any(window.status not in allowed_window_states for window in project.narration.windows):
            raise HTTPException(status_code=409, detail="请先保存并确认全部旁白时间窗")
        window_ids = payload.windowIds
        available_window_ids = {window.id for window in project.narration.windows}
        if window_ids is not None and (len(set(window_ids)) != len(window_ids) or not set(window_ids) <= available_window_ids):
            raise HTTPException(status_code=422, detail="指定的旁白时间窗无效或重复")
        input_data = {"previewId": project.preview.id, "revision": project.narration.windowRevision,
                      "windows": [{"id": window.id, "order": window.order, "startSeconds": window.startSeconds,
                                   "endSeconds": window.endSeconds, "text": window.text,
                                   "textLocked": window.textLocked}
                                  for window in project.narration.windows],
                      "windowIds": window_ids, "forceRegenerate": payload.forceRegenerate,
                      "speed": payload.speed}
        try:
            job, created = enqueue_media_job(
                project, kind="audio", request_id=payload.requestId,
                snapshot={"project": project.model_dump(mode="json"), "speed": payload.speed,
                          "windowIds": window_ids, "forceRegenerate": payload.forceRegenerate},
                input_signature=signature(input_data),
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        store.save(project)
        if created:
            background_tasks.add_task(run_narration_audio_job, project_id, job.id, payload.speed, settings, store,
                                      window_ids=window_ids, force_regenerate=payload.forceRegenerate)
        return project


@router.post("/{project_id}/media-jobs/{job_id}/cancel", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
def cancel_media_job(project_id: str, job_id: str, store: ProjectStore = Depends(get_store)) -> Project:
    with store.lock(project_id):
        project = _project(store, project_id)
        job = next((item for item in project.mediaJobs if item.id == job_id), None)
        if not job:
            raise HTTPException(status_code=404, detail="媒体任务不存在")
        if job.status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="媒体任务已结束，无法取消")
        if job.status == "queued":
            touch_job(job, "cancelled", message="用户取消了媒体任务")
        else:
            job.progress["cancelRequested"] = True
            touch_job(job, "running", message="正在停止媒体任务；已发出的供应商请求可能仍会计费")
        store.save(project)
        return project
