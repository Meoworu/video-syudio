from app.domain.models import Project


def invalidate_picture_timeline(project: Project) -> None:
    """Keep old media for playback while preventing it from being used as current output."""
    if project.preview:
        project.preview.status = "stale"
    for window in project.narration.windows:
        window.status = "stale"
    if project.finalRender:
        project.finalRender.isCurrent = False
    project.finalVideoPath = None
    project.narration.audioPath = None
    project.narration.audioDurationSeconds = None
    project.narration.selectedTakeId = None
    for take in project.narration.takes:
        take.status = "stale"
    if project.narration.mode == "windowed":
        project.narration.status = "draft"
