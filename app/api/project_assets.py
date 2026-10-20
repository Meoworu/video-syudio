from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.projects import get_store
from app.config import Settings, get_settings
from app.domain.models import CreateAssetRequest, GenerateFrameRequest, Project, ProjectAsset, UpdateFrameConfigRequest
from app.services.asset_service import InvalidImageError, normalize_image, save_asset_image
from app.services.frame_service import FrameService
from app.store.project_store import ProjectStore


router = APIRouter(prefix="/projects", tags=["assets and frames"])


def _project(store: ProjectStore, project_id: str) -> Project:
    try:
        return store.get(project_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="项目不存在") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail="项目 ID 无效") from error


def _asset(project: Project, asset_id: str) -> ProjectAsset:
    asset = next((item for item in project.assets if item.id == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return asset


def _asset_in_use(project: Project, asset_id: str) -> bool:
    return any(
        (job := shot.frames[role].job) is not None
        and job.status in {"queued", "generating"}
        and any(item.get("assetId") == asset_id for item in job.inputSnapshot.get("references", []))
        for shot in project.shots for role in ("first", "last")
    )


@router.post("/{project_id}/assets", response_model=Project, status_code=status.HTTP_201_CREATED)
def create_asset(project_id: str, payload: CreateAssetRequest, store: ProjectStore = Depends(get_store)) -> Project:
    project = _project(store, project_id)
    if project.status != "ready":
        raise HTTPException(status_code=409, detail="导演规划完成后才能管理资产")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="资产名称不能为空")
    shot_ids = {shot.id for shot in project.shots}
    if not payload.scopeShotIds or any(shot_id not in shot_ids for shot_id in payload.scopeShotIds):
        raise HTTPException(status_code=422, detail="请指定有效的关联镜头")
    with store.lock(project_id):
        project = _project(store, project_id)
        project.assets.append(ProjectAsset(
            id=uuid.uuid4().hex, kind="reference", name=name,
            description=payload.description.strip(), scopeShotIds=list(dict.fromkeys(payload.scopeShotIds)),
        ))
        store.save(project)
        return project


@router.put("/{project_id}/assets/{asset_id}", response_model=Project)
def update_asset(project_id: str, asset_id: str, payload: CreateAssetRequest, store: ProjectStore = Depends(get_store)) -> Project:
    with store.lock(project_id):
        project = _project(store, project_id)
        asset = _asset(project, asset_id)
        if asset.kind != "reference":
            raise HTTPException(status_code=409, detail="角色和场景资产名称由导演规划维护")
        if _asset_in_use(project, asset_id):
            raise HTTPException(status_code=409, detail="此资产正在用于图片生成")
        shot_ids = {shot.id for shot in project.shots}
        if not payload.name.strip() or not payload.scopeShotIds or any(item not in shot_ids for item in payload.scopeShotIds):
            raise HTTPException(status_code=422, detail="请填写名称并指定有效的关联镜头")
        asset.name = payload.name.strip()
        asset.description = payload.description.strip()
        asset.scopeShotIds = list(dict.fromkeys(payload.scopeShotIds))
        store.save(project)
        return project


@router.post("/{project_id}/assets/{asset_id}/image", response_model=Project)
async def upload_asset_image(project_id: str, asset_id: str, request: Request, store: ProjectStore = Depends(get_store)) -> Project:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 6_000_000:
            raise HTTPException(status_code=413, detail="图片不能超过 6 MB")
    try:
        normalized, width, height = await run_in_threadpool(normalize_image, bytes(chunks), content_type)
    except InvalidImageError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    def persist_image() -> Project:
        with store.lock(project_id):
            project = _project(store, project_id)
            asset = _asset(project, asset_id)
            if _asset_in_use(project, asset_id):
                raise HTTPException(status_code=409, detail="此资产正在用于图片生成")
            save_asset_image(store, project_id, asset, normalized, width, height)
            store.save(project)
            return project

    return await run_in_threadpool(persist_image)


@router.delete("/{project_id}/assets/{asset_id}", response_model=Project)
def delete_asset(project_id: str, asset_id: str, store: ProjectStore = Depends(get_store)) -> Project:
    with store.lock(project_id):
        project = _project(store, project_id)
        asset = _asset(project, asset_id)
        if _asset_in_use(project, asset_id):
            raise HTTPException(status_code=409, detail="此资产正在用于图片生成")
        if asset.kind == "reference":
            project.assets.remove(asset)
        else:
            asset.image = None
            asset.revision += 1
        store.save(project)
        return project


@router.put("/{project_id}/shots/{shot_id}/frames/{role}/config", response_model=Project)
def update_frame_config(project_id: str, shot_id: str, role: str, payload: UpdateFrameConfigRequest, store: ProjectStore = Depends(get_store)) -> Project:
    if role not in {"first", "last"}:
        raise HTTPException(status_code=400, detail="只支持 first 或 last 帧")
    with store.lock(project_id):
        project = _project(store, project_id)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if not shot:
            raise HTTPException(status_code=404, detail="镜头不存在")
        slot = shot.frames[role]
        if slot.job and slot.job.status in {"queued", "generating"}:
            raise HTTPException(status_code=409, detail="图片正在生成，暂不能修改提示词或参考")
        if payload.referenceMode == "manual":
            valid_ids = {asset.id for asset in project.assets if asset.image}
            if not payload.assetIds or any(asset_id not in valid_ids for asset_id in payload.assetIds):
                raise HTTPException(status_code=422, detail="手动参考必须选择已上传图片的资产")
            slot.assetIds = list(dict.fromkeys(payload.assetIds))
        else:
            slot.assetIds = []
        slot.referenceMode = payload.referenceMode
        setattr(shot, f"{role}FramePrompt", getattr(shot, f"director{role.title()}FramePrompt") if payload.restoreDefaultPrompt else payload.prompt.strip())
        store.save(project)
        return project


@router.post("/{project_id}/shots/{shot_id}/frames/{role}/generate", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
def generate_frame(project_id: str, shot_id: str, role: str, payload: GenerateFrameRequest, background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    if role not in {"first", "last"}:
        raise HTTPException(status_code=400, detail="只支持 first 或 last 帧")
    with store.lock(project_id):
        project = _project(store, project_id)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if not shot:
            raise HTTPException(status_code=404, detail="镜头不存在")
        try:
            job_id = FrameService(settings, store).enqueue(project, shot, role, payload.requestId)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        background_tasks.add_task(FrameService(settings, store).run, project_id, shot_id, role, job_id)
        store.save(project)
        return project


@router.post("/{project_id}/shots/{shot_id}/generate-frames", response_model=Project, status_code=status.HTTP_202_ACCEPTED)
def generate_frames(project_id: str, shot_id: str, payload: GenerateFrameRequest, background_tasks: BackgroundTasks, settings: Settings = Depends(get_settings), store: ProjectStore = Depends(get_store)) -> Project:
    with store.lock(project_id):
        project = _project(store, project_id)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if not shot:
            raise HTTPException(status_code=404, detail="镜头不存在")
        try:
            group_id, first_job_id, last_job_id, is_new = FrameService(settings, store).enqueue_pair(project, shot, payload.requestId)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        store.save(project)
        if is_new:
            background_tasks.add_task(FrameService(settings, store).run_pair, project_id, shot_id, group_id, first_job_id, last_job_id)
        return project


@router.post("/{project_id}/shots/{shot_id}/frames/{role}/versions/{version_id}/select", response_model=Project)
def select_frame_version(project_id: str, shot_id: str, role: str, version_id: str, store: ProjectStore = Depends(get_store)) -> Project:
    if role not in {"first", "last"}:
        raise HTTPException(status_code=400, detail="只支持 first 或 last 帧")
    with store.lock(project_id):
        project = _project(store, project_id)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if not shot:
            raise HTTPException(status_code=404, detail="镜头不存在")
        if shot.video and shot.video.status in {"submitting", "generating", "downloading"}:
            raise HTTPException(status_code=409, detail="视频任务执行中，暂不能切换首尾帧")
        if shot.frames[role].job and shot.frames[role].job.status in {"queued", "generating"}:
            raise HTTPException(status_code=409, detail="图片正在生成，暂不能切换版本")
        try:
            FrameService(get_settings(), store).select_version(project, shot, role, version_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        store.save(project)
        return project


@router.delete("/{project_id}/shots/{shot_id}/frames/{role}/failed-job", response_model=Project)
def delete_failed_frame_job(project_id: str, shot_id: str, role: str, store: ProjectStore = Depends(get_store)) -> Project:
    if role not in {"first", "last"}:
        raise HTTPException(status_code=400, detail="只支持 first 或 last 帧")
    with store.lock(project_id):
        project = _project(store, project_id)
        shot = next((item for item in project.shots if item.id == shot_id), None)
        if not shot:
            raise HTTPException(status_code=404, detail="镜头不存在")
        job = shot.frames[role].job
        if not job or job.status != "failed":
            raise HTTPException(status_code=409, detail="只能删除生成失败的任务记录")
        shot.frames[role].job = None
        store.save(project)
        return project
