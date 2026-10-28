from typing import Any

from app.domain.models import Project, PreviewClip


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


def build_measured_timeline(project: Project, source_durations: dict[str, float], source_digests: dict[str, str]) -> tuple[list[dict[str, Any]], float]:
    """Build the single timeline used to render and timestamp a silent preview."""
    shots_by_index = {shot.index: shot for shot in project.shots}
    intent = sorted(project.editPlan, key=lambda item: float(item.get("timelineStart", 0))) if project.editPlan else [
        {"shotIndex": shot.index, "sourceIn": 0, "sourceOut": shot.durationSeconds}
        for shot in sorted(project.shots, key=lambda item: item.index)
    ]
    prepared: list[tuple[Any, float, float, float]] = []
    for item in intent:
        shot = shots_by_index.get(int(item["shotIndex"]))
        if shot is None or not shot.video or not shot.video.path:
            raise ValueError("剪辑计划引用了不存在的视频镜头")
        source_duration = source_durations[shot.id]
        source_in = max(0.0, float(item.get("sourceIn", 0)))
        if source_in >= source_duration:
            raise ValueError(f"镜头 {shot.index + 1} 的源视频起点超出实际时长")
        requested_out = float(item.get("sourceOut", source_duration))
        source_out = min(source_duration, requested_out)
        if source_out <= source_in:
            raise ValueError(f"镜头 {shot.index + 1} 的源视频区间无效")
        prepared.append((shot, source_in, source_out, source_out - source_in))
    if not prepared:
        raise ValueError("没有可用于剪辑预览的视频")

    clips: list[dict[str, Any]] = []
    cursor = 0.0
    for index, (shot, source_in, source_out, duration) in enumerate(prepared):
        overlap = 0.0
        if index and shot.transitionIn == "dissolve":
            previous_duration = prepared[index - 1][3]
            overlap = min(TRANSITION_OVERLAP_SECONDS, previous_duration / 2, duration / 2)
        start = max(0.0, cursor - overlap)
        end = start + duration
        clips.append(PreviewClip(
            shotId=shot.id, shotIndex=shot.index, sourceDigest=source_digests[shot.id],
            sourceIn=source_in, sourceOut=source_out, timelineStart=start,
            timelineEnd=end, overlapSeconds=overlap,
        ).model_dump(mode="json"))
        cursor = end
    return clips, cursor
