from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import Settings
from app.domain.models import Project, ProjectPreview
from app.services.editing import build_measured_timeline
from app.services.media_probe import probe_media, sha256_file
from app.store.project_store import ProjectStore


class PreviewService:
    def __init__(self, settings: Settings, store: ProjectStore) -> None:
        self.settings = settings
        self.store = store

    def render(self, project: Project, *, cancel_check=None) -> ProjectPreview:
        root = self.store.project_dir(project.projectId).resolve()
        ordered_clips = sorted(project.editPlan, key=lambda item: float(item.get("timelineStart", 0))) if project.editPlan else [
            {"shotIndex": shot.index, "sourceIn": 0, "sourceOut": shot.durationSeconds}
            for shot in sorted(project.shots, key=lambda item: item.index)
        ]
        shots_by_index = {shot.index: shot for shot in project.shots}
        video_paths: dict[str, Path] = {}
        source_durations: dict[str, float] = {}
        source_digests: dict[str, str] = {}
        for clip in ordered_clips:
            shot = shots_by_index.get(int(clip["shotIndex"]))
            if not shot or not shot.video or shot.video.status != "complete" or not shot.video.path:
                raise ValueError("请先完成所有分镜视频生成")
            path = self._project_file(root, shot.video.path)
            info = probe_media(path, self.settings.ffprobe_bin)
            if not info.has_video:
                raise ValueError(f"镜头 {shot.index + 1} 文件不含视频流")
            video_paths[shot.id] = path
            source_durations[shot.id] = info.duration_seconds
            source_digests[shot.id] = sha256_file(path)
        clips, planned_duration = build_measured_timeline(project, source_durations, source_digests)
        preview_id = uuid.uuid4().hex
        output = root / "previews" / preview_id / "silent.mp4"
        output.parent.mkdir(parents=True, exist_ok=False)
        partial = output.with_name("silent.part.mp4")
        self._render_video(project, clips, video_paths, partial, cancel_check=cancel_check)
        try:
            result = probe_media(partial, self.settings.ffprobe_bin)
            if not result.has_video or result.has_audio:
                raise RuntimeError("无旁白预览必须包含视频流且不包含音频流")
            tolerance = 1 / max(result.fps or 24, 24) + 0.1
            if abs(result.duration_seconds - planned_duration) > tolerance:
                raise RuntimeError(
                    f"预览时长与实测剪辑计划不一致：{result.duration_seconds:.3f}s / {planned_duration:.3f}s"
                )
            partial.replace(output)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        signature_payload = {
            "clips": clips, "aspectRatio": project.aspectRatio,
            "transitions": [(shot.id, shot.transitionIn) for shot in sorted(project.shots, key=lambda item: item.index)],
            "renderer": "silent-preview-v1",
        }
        signature = hashlib.sha256(json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return ProjectPreview(
            id=preview_id, path=str(output.relative_to(root)), durationSeconds=result.duration_seconds,
            fps=result.fps or 24, inputSignature=signature, clips=clips,
        )

    def _render_video(self, project: Project, clips: list[dict[str, Any]], paths: dict[str, Path], output: Path, *, cancel_check=None) -> None:
        width, height = (720, 1280) if project.aspectRatio == "9:16" else (1280, 720)
        args = [self.settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
        for clip in clips:
            args.extend(["-i", str(paths[clip["shotId"]])])
        filters: list[str] = []
        for index, clip in enumerate(clips):
            duration = float(clip["sourceOut"]) - float(clip["sourceIn"])
            filters.append(
                f"[{index}:v:0]trim=start={clip['sourceIn']:.6f}:duration={duration:.6f},"
                f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p,settb=AVTB[v{index}]"
            )
        groups: list[list[int]] = []
        current: list[int] = []
        for index, clip in enumerate(clips):
            if index and float(clip["overlapSeconds"]) > 0:
                groups.append(current)
                current = []
            current.append(index)
        if current:
            groups.append(current)
        labels: list[str] = []
        durations: list[float] = []
        for group_index, group in enumerate(groups):
            label = f"g{group_index}"
            duration = sum(float(clips[index]["sourceOut"]) - float(clips[index]["sourceIn"]) for index in group)
            if len(group) == 1:
                filters.append(f"[v{group[0]}]null[{label}]")
            else:
                filters.append("".join(f"[v{index}]" for index in group) + f"concat=n={len(group)}:v=1:a=0[{label}]")
            labels.append(label)
            durations.append(duration)
        accumulated = durations[0]
        active = labels[0]
        for group_index in range(1, len(groups)):
            # The first clip of each group owns the overlap with the previous group.
            next_clip = groups[group_index][0]
            overlap = float(clips[next_clip]["overlapSeconds"])
            label = f"x{group_index}"
            filters.append(f"[{active}][{labels[group_index]}]xfade=transition=fade:duration={overlap:.6f}:offset={accumulated - overlap:.6f}[{label}]")
            accumulated += durations[group_index] - overlap
            active = label
        filters.append(f"[{active}]null[vout]")
        args.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-movflags", "+faststart", "-f", "mp4", str(output)])
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        started = time.monotonic()
        while process.poll() is None:
            if cancel_check and cancel_check():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                output.unlink(missing_ok=True)
                raise RuntimeError("剪辑预览已取消")
            if time.monotonic() - started > self.settings.preview_render_timeout_seconds:
                process.kill()
                process.wait()
                output.unlink(missing_ok=True)
                raise TimeoutError("剪辑预览渲染超时")
            time.sleep(0.25)
        stderr = process.stderr.read() if process.stderr else ""
        if process.returncode:
            output.unlink(missing_ok=True)
            raise RuntimeError(f"FFmpeg 无旁白预览失败：{stderr[-1200:]}")

    @staticmethod
    def _project_file(root: Path, relative_path: str) -> Path:
        path = (root / relative_path).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(f"项目媒体文件不存在：{relative_path}")
        return path
