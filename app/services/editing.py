from app.domain.models import Project


TRANSITION_OVERLAP_SECONDS = 0.5


def rebuild_edit_plan(project: Project) -> list[dict[str, object]]:
    clips: list[dict[str, object]] = []
    previous_end = 0.0
    for shot in sorted(project.shots, key=lambda item: item.index):
        overlap = TRANSITION_OVERLAP_SECONDS if clips and shot.transitionIn == "dissolve" else 0.0
        start = max(0.0, previous_end - overlap)
        end = start + shot.durationSeconds
        clips.append({
            "shotIndex": shot.index,
            "timelineStart": round(start, 3),
            "timelineEnd": round(end, 3),
            "sourceIn": 0.0,
            "sourceOut": float(shot.durationSeconds),
            "transitionIn": "none" if not clips else shot.transitionIn,
            "transitionReason": shot.transitionReason,
        })
        previous_end = end
    project.editPlan = clips
    return clips


def project_duration(project: Project) -> float:
    if project.editPlan:
        return max(float(clip.get("timelineEnd", 0)) for clip in project.editPlan)
    return sum(shot.durationSeconds for shot in project.shots)
