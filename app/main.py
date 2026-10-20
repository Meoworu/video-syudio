import asyncio

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.projects import router as project_router
from app.config import get_settings
from app.services.director_service import DirectorService
from app.services.video_service import VideoService
from app.store.project_store import ProjectStore

_RECOVERY_TASKS: set[asyncio.Task] = set()


app = FastAPI(
    title="video-studio",
    version="0.1.0",
    description="Google Gemini video studio with MiniMax continuous narration.",
)
app.include_router(health_router, prefix="/v1")
app.include_router(project_router, prefix="/v1")


@app.on_event("startup")
async def resume_video_tasks() -> None:
    settings = get_settings()
    store = ProjectStore(settings.video_studio_data_dir)
    for project in store.list():
        if project.status == "generating" and project.directorRequest:
            task = asyncio.create_task(asyncio.to_thread(DirectorService(settings).run_project, project.projectId, store))
            _RECOVERY_TASKS.add(task)
            task.add_done_callback(_RECOVERY_TASKS.discard)
            continue
        for shot in project.shots:
            if not shot.video or shot.video.status not in {"submitting", "generating", "downloading"}:
                continue
            if shot.video.remoteJobId:
                task = asyncio.create_task(asyncio.to_thread(VideoService(settings, store).run, project.projectId, shot.id))
                _RECOVERY_TASKS.add(task)
                task.add_done_callback(_RECOVERY_TASKS.discard)
                continue
            # A crash between remote submission and persisting its ID cannot be
            # resumed safely; flag it instead of silently submitting duplicates.
            with store.lock(project.projectId):
                current = store.get(project.projectId)
                current_shot = next(item for item in current.shots if item.id == shot.id)
                if current_shot.video and current_shot.video.status == "submitting" and not current_shot.video.remoteJobId:
                    current_shot.video.status = "failed"
                    current_shot.video.errorMessage = "服务重启时未找到 Google 任务 ID，请重新提交该镜头"
                    store.save(current)

