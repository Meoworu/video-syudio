from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import Settings
from app.domain.models import Project
from app.store.project_store import ProjectStore
from app.services.editing import TRANSITION_OVERLAP_SECONDS


class AssemblyService:
    def __init__(self, settings: Settings, store: ProjectStore) -> None:
        self.settings = settings
        self.store = store

    def assemble(self, project: Project) -> Project:
        root = self.store.project_dir(project.projectId).resolve()
        shots_by_index = {shot.index: shot for shot in project.shots}
        clips = sorted(project.editPlan, key=lambda item: float(item.get("timelineStart", 0))) if project.editPlan else [
            {"shotIndex": shot.index, "sourceIn": 0, "sourceOut": shot.durationSeconds, "transitionIn": shot.transitionIn}
            for shot in sorted(project.shots, key=lambda item: item.index)
        ]
        shots = [shots_by_index[int(clip["shotIndex"])] for clip in clips]
        if not shots or any(not shot.video or shot.video.status != "complete" or not shot.video.path for shot in shots):
            raise ValueError("请先完成所有分镜视频生成")
        videos = [self._project_file(root, shot.video.path) for shot in shots]
        source_durations = [self._duration(path) for path in videos]
        clip_durations = []
        for clip, source_duration in zip(clips, source_durations):
            source_in = max(0.0, float(clip.get("sourceIn", 0)))
            source_out = float(clip.get("sourceOut", source_duration))
            clip_durations.append(min(source_duration - source_in, source_out - source_in))
        if any(duration <= 0 for duration in clip_durations):
            raise ValueError("剪辑时间线包含空片段或无效的源视频区间")
        groups: list[list[int]] = []
        group: list[int] = []
        for index, shot in enumerate(shots):
            if group and shot.transitionIn == "dissolve":
                groups.append(group)
                group = []
            group.append(index)
        if group:
            groups.append(group)
        crossfade_count = sum(1 for group in groups[1:])
        total_duration = sum(clip_durations) - crossfade_count * TRANSITION_OVERLAP_SECONDS
        if total_duration <= 0:
            raise ValueError("剪辑时间线时长无效")
        if not project.narration.audioPath:
            raise ValueError("请先生成并选择 MiniMax 连续旁白音频")
        audio = self._project_file(root, project.narration.audioPath)
        output = root / "final" / "final.mp4"
        partial = output.with_name("final.part.mp4")
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [self.settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
        for path in videos:
            args.extend(["-i", str(path)])
        args.extend(["-i", str(audio)])

        filters = []
        width, height = (720, 1280) if project.aspectRatio == "9:16" else (1280, 720)
        for index in range(len(videos)):
            label = f"v{index}"
            source_in = max(0.0, float(clips[index].get("sourceIn", 0)))
            filters.append(
                f"[{index}:v:0]trim=start={source_in:.3f}:duration={clip_durations[index]:.3f},"
                f"setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p,settb=AVTB[v{index}]"
            )
        group_labels: list[str] = []
        group_durations: list[float] = []
        for group_index, indexes in enumerate(groups):
            label = f"g{group_index}"
            if len(indexes) == 1:
                filters.append(f"[v{indexes[0]}]null[{label}]")
            else:
                filters.append("".join(f"[v{index}]" for index in indexes) + f"concat=n={len(indexes)}:v=1:a=0[{label}]")
            group_labels.append(label)
            group_durations.append(sum(clip_durations[index] for index in indexes))
        video_label = group_labels[0]
        accumulated_duration = group_durations[0]
        for group_index in range(1, len(groups)):
            next_label = f"x{group_index}"
            overlap = min(TRANSITION_OVERLAP_SECONDS, accumulated_duration / 2, group_durations[group_index] / 2)
            offset = accumulated_duration - overlap
            filters.append(
                f"[{video_label}][{group_labels[group_index]}]xfade=transition=fade:"
                f"duration={overlap:.3f}:offset={offset:.3f}[{next_label}]"
            )
            accumulated_duration += group_durations[group_index] - overlap
            video_label = next_label
        # Resolve the final chained transition label before mapping it.
        filters.append(f"[{video_label}]null[vout]")
        audio_index = len(videos)
        filters.append(f"[{audio_index}:a:0]apad,atrim=duration={total_duration:.3f},asetpts=PTS-STARTPTS[aout]")
        args.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]"])
        args.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-movflags", "+faststart"])
        args.extend(["-c:a", "aac", "-b:a", "192k"])
        args.extend(["-f", "mp4", str(partial)])
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            if result.returncode:
                raise RuntimeError(f"FFmpeg 合成失败：{result.stderr[-1200:]}")
            self._probe(partial, require_audio=True)
            partial.replace(output)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        project.finalVideoPath = str(output.relative_to(root))
        self.store.save(project)
        return project

    def _project_file(self, root: Path, relative_path: str | None) -> Path:
        if not relative_path:
            raise ValueError("项目媒体路径为空")
        path = (root / relative_path).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError(f"项目媒体文件不存在：{relative_path}")
        return path

    def _duration(self, path: Path) -> float:
        payload = self._probe(path)
        try:
            duration = float(payload["format"]["duration"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"无法读取视频时长：{path.name}") from error
        if duration <= 0:
            raise RuntimeError(f"视频时长无效：{path.name}")
        return duration

    def _probe(self, path: Path, *, require_audio: bool = False) -> dict:
        result = subprocess.run(
            [self.settings.ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"媒体文件校验失败：{result.stderr[-800:]}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("ffprobe 返回了无效结果") from error
        types = {stream.get("codec_type") for stream in payload.get("streams", [])}
        if "video" not in types or (require_audio and "audio" not in types):
            raise RuntimeError("成片缺少有效的视频或旁白音轨")
        return payload
