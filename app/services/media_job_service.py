from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.domain.models import MediaJob, Project


ACTIVE_MEDIA_JOB_STATES = {"queued", "running"}


def signature(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def active_media_job(project: Project) -> MediaJob | None:
    return next((job for job in project.mediaJobs if job.status in ACTIVE_MEDIA_JOB_STATES), None)


def cancel_requested(job: MediaJob | None) -> bool:
    return bool(job and (job.status == "cancelled" or job.progress.get("cancelRequested")))


def _job_cancel_requested(project_id: str, job_id: str, store) -> bool:
    try:
        project = store.get(project_id)
    except FileNotFoundError:
        return True
    return cancel_requested(next((item for item in project.mediaJobs if item.id == job_id), None))


def enqueue_media_job(project: Project, *, kind: str, request_id: str, snapshot: dict, input_signature: str) -> tuple[MediaJob, bool]:
    prior = next((job for job in project.mediaJobs if job.kind == kind and job.requestId == request_id), None)
    if prior:
        if prior.inputSignature != input_signature:
            raise ValueError("相同 requestId 不能用于不同输入")
        return prior, False
    active = active_media_job(project)
    if active:
        raise ValueError(f"媒体任务 {active.id} 正在执行，请等待完成")
    # Snapshots need a stable project state, not the historical jobs which
    # themselves contain snapshots. Dropping that recursive branch keeps the
    # persisted project size linear as jobs accumulate.
    for prior_job in project.mediaJobs:
        prior_project = prior_job.inputSnapshot.get("project")
        if isinstance(prior_project, dict):
            prior_project["mediaJobs"] = []
    snapshot_project = snapshot.get("project")
    if isinstance(snapshot_project, dict):
        snapshot_project["mediaJobs"] = []
    job = MediaJob(
        id=f"media_{signature([project.projectId, kind, request_id])[:24]}",
        kind=kind, requestId=request_id, inputSnapshot=snapshot, inputSignature=input_signature,
    )
    project.mediaJobs.append(job)
    return job, True


def touch_job(job: MediaJob, status: str, *, message: str | None = None, code: str | None = None) -> None:
    job.status = status  # type: ignore[assignment]
    job.updatedAt = datetime.now(timezone.utc).isoformat()
    if message is not None:
        job.errorMessage = message
    if code is not None:
        job.errorCode = code


def timeline_snapshot(project: Project) -> dict:
    return {
        "projectId": project.projectId,
        "aspectRatio": project.aspectRatio,
        "editPlan": project.editPlan,
        "shots": [{"id": shot.id, "index": shot.index, "transitionIn": shot.transitionIn,
                   "video": shot.video.model_dump(mode="json") if shot.video else None} for shot in project.shots],
    }


def run_preview_job(project_id: str, job_id: str, settings, store) -> None:
    from app.services.preview_service import PreviewService

    with store.lock(project_id):
        current = store.get(project_id)
        job = next((item for item in current.mediaJobs if item.id == job_id), None)
        if not job or job.status != "queued":
            return
        touch_job(job, "running")
        snapshot = Project.model_validate(job.inputSnapshot["project"])
        store.save(current)
    try:
        preview = PreviewService(settings, store).render(snapshot, cancel_check=lambda: _job_cancel_requested(project_id, job_id, store))
        with store.lock(project_id):
            current = store.get(project_id)
            job = next((item for item in current.mediaJobs if item.id == job_id), None)
            if not job:
                (store.project_dir(project_id) / preview.path).unlink(missing_ok=True)
                return
            if cancel_requested(job):
                (store.project_dir(project_id) / preview.path).unlink(missing_ok=True)
                touch_job(job, "cancelled", message="预览任务已取消")
                store.save(current)
                return
            if signature(timeline_snapshot(current)) != job.inputSignature:
                touch_job(job, "failed", code="STALE_INPUT", message="生成期间剪辑输入发生变化，请重新生成预览")
            else:
                if current.preview and current.preview.id != preview.id:
                    for window in current.narration.windows:
                        window.status = "stale"
                    current.narration.audioPath = None
                    current.narration.audioDurationSeconds = None
                    current.narration.selectedTakeId = None
                    current.narration.status = "draft" if current.narration.mode == "windowed" else current.narration.status
                    for take in current.narration.takes:
                        take.status = "stale"
                current.preview = preview
                current.finalRender = current.finalRender.model_copy(update={"isCurrent": False}) if current.finalRender else None
                if current.finalRender and current.finalVideoPath == current.finalRender.path:
                    current.finalVideoPath = None
                touch_job(job, "complete")
                job.progress = {"completed": 1, "total": 1}
            store.save(current)
    except Exception as error:
        with store.lock(project_id):
            current = store.get(project_id)
            job = next((item for item in current.mediaJobs if item.id == job_id), None)
            if job and cancel_requested(job):
                touch_job(job, "cancelled", message="预览任务已取消")
                store.save(current)
            elif job:
                touch_job(job, "failed", code="PREVIEW_FAILED", message=str(error)[:1200])
                store.save(current)


def run_windows_job(project_id: str, job_id: str, settings, store) -> None:
    from app.services.narration_windows_service import NarrationWindowsService

    with store.lock(project_id):
        current = store.get(project_id)
        job = next((item for item in current.mediaJobs if item.id == job_id), None)
        if not job or job.status != "queued":
            return
        touch_job(job, "running")
        snapshot = Project.model_validate(job.inputSnapshot["project"])
        preview = current.preview.model_copy(deep=True) if current.preview else None
        store.save(current)
    try:
        if not preview:
            raise ValueError("请先生成剪辑预览")
        planner = NarrationWindowsService(settings, store)
        windows = planner.suggest(snapshot, preview)
        with store.lock(project_id):
            current = store.get(project_id)
            job = next((item for item in current.mediaJobs if item.id == job_id), None)
            if not job:
                return
            was_cancelled = cancel_requested(job)
            if not current.preview or current.preview.id != preview.id:
                touch_job(job, "failed", code="STALE_PREVIEW", message="剪辑预览已更新，请重新规划旁白")
            else:
                current.narration.windows = windows
                # Keep a confirmed project in windowed mode while replacing its
                # plan. Its old selected take no longer matches the new revision.
                if current.narration.mode == "windowed":
                    current.narration.audioPath = None
                    current.narration.audioDurationSeconds = None
                    current.narration.selectedTakeId = None
                    current.narration.status = "draft"
                    for take in current.narration.takes:
                        if take.mode == "windowed":
                            take.status = "stale"
                    if current.finalRender:
                        current.finalRender.isCurrent = False
                    current.finalVideoPath = None
                current.narration.windowRevision += 1
                current.preview.evidenceFrames = planner.evidence_frames if current.preview else []
                if was_cancelled:
                    touch_job(job, "cancelled", message="画面规划请求完成，建议已保存；任务已取消")
                else:
                    touch_job(job, "complete")
                    job.progress = {"completed": 1, "total": 1}
            store.save(current)
    except Exception as error:
        with store.lock(project_id):
            current = store.get(project_id)
            job = next((item for item in current.mediaJobs if item.id == job_id), None)
            if job and cancel_requested(job):
                touch_job(job, "cancelled", message="画面规划任务已取消")
                store.save(current)
            elif job:
                touch_job(job, "failed", code="WINDOW_PLAN_FAILED", message=str(error)[:1200])
                store.save(current)


def run_narration_audio_job(project_id: str, job_id: str, speed: float, settings, store, *,
                           window_ids: list[str] | None = None, force_regenerate: bool = False) -> None:
    from app.services.narration_audio_service import NarrationAudioService
    NarrationAudioService(settings, store).run(
        project_id, job_id, speed=speed, window_ids=window_ids, force_regenerate=force_regenerate,
    )




def run_export_job(project_id: str, job_id: str, settings, store) -> None:
    from app.services.assembly_service import AssemblyService

    with store.lock(project_id):
        current = store.get(project_id)
        job = next((item for item in current.mediaJobs if item.id == job_id), None)
        if not job or job.status != "queued":
            return
        touch_job(job, "running")
        snapshot = Project.model_validate(job.inputSnapshot["project"])
        store.save(current)
    try:
        final_render = AssemblyService(settings, store).assemble_windowed(snapshot)
        with store.lock(project_id):
            current = store.get(project_id)
            job = next((item for item in current.mediaJobs if item.id == job_id), None)
            if not job:
                return
            if cancel_requested(job):
                touch_job(job, "cancelled", message="成片封装已取消")
                store.save(current)
                return
            if not current.preview or not snapshot.preview or current.preview.id != snapshot.preview.id or current.narration.windowRevision != snapshot.narration.windowRevision or current.narration.selectedTakeId != snapshot.narration.selectedTakeId:
                touch_job(job, "failed", code="STALE_EXPORT", message="导出期间预览或旁白版本发生变化")
            else:
                current.finalRender = final_render
                current.finalVideoPath = final_render.path
                touch_job(job, "complete")
                job.progress = {"completed": 1, "total": 1}
            store.save(current)
    except Exception as error:
        with store.lock(project_id):
            current = store.get(project_id)
            job = next((item for item in current.mediaJobs if item.id == job_id), None)
            if job and cancel_requested(job):
                touch_job(job, "cancelled", message="成片封装已取消")
                store.save(current)
            elif job:
                touch_job(job, "failed", code="EXPORT_FAILED", message=str(error)[:1200])
                store.save(current)
