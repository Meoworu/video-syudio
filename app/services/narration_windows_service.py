from __future__ import annotations

import json
import math
import subprocess
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.clients.google_text import GoogleTextClient
from app.config import Settings
from app.domain.models import NarrationWindow, Project, ProjectPreview
from app.store.project_store import ProjectStore


MAX_EVIDENCE_FRAMES = 24
MAX_FRAME_EDGE = 768
MAX_FRAME_BYTES = 150_000
MAX_TOTAL_FRAME_BYTES = 4_000_000


class NarrationWindowsService:
    def __init__(self, settings: Settings, store: ProjectStore, *, google: GoogleTextClient | None = None) -> None:
        self.settings = settings
        self.store = store
        self.google = google or GoogleTextClient(settings)
        self.evidence_frames: list[dict[str, Any]] = []

    def suggest(self, project: Project, preview: ProjectPreview) -> list[NarrationWindow]:
        root = self.store.project_dir(project.projectId).resolve()
        preview_path = self._project_file(root, preview.path)
        frames = self._extract_frames(root, preview, preview_path)
        self.evidence_frames = [{key: item[key] for key in ("id", "timeSeconds", "shotIds", "relativePath")} for item in frames]
        if not frames:
            raise ValueError("無法從實際剪輯預覽抽取畫面；可以手動建立時間窗")
        story_basis = project.productionScript.model_dump(mode="json") if project.productionScript else project.story
        clips = [{"shotId": clip.shotId, "startSeconds": clip.timelineStart, "endSeconds": clip.timelineEnd} for clip in preview.clips]
        frame_index = [{"id": item["id"], "timeSeconds": item["timeSeconds"], "shotIds": item["shotIds"]} for item in frames]
        prompt = (
            "你是旁白剪輯師。只能根據原始內容中的事實撰寫旁白，並根據提供的實際影片抽幀安排時間。"
            "按完整語義分段，允許一段跨多個鏡頭，允許留白；不要逐鏡頭硬切句子。"
            "每個窗口提供 startSeconds/endSeconds、sourceShotIds、visualSummary、text、anchorNote、evidenceFrameIds。"
            "時間必須落在片長內，窗口不得重叠。每個 evidenceFrameIds 必須使用下方有效 frame id。"
            "只輸出 JSON：{\"windows\":[...]}。抽幀標籤中含 frame id 和真實時間。\n"
            f"片長：{preview.durationSeconds:.3f} 秒\n"
            f"原始內容/劇本：{json.dumps(story_basis, ensure_ascii=False)}\n"
            f"實測鏡頭時間線：{json.dumps(clips, ensure_ascii=False)}\n"
            f"抽幀索引：{json.dumps(frame_index, ensure_ascii=False)}"
        )
        image_inputs = [(Path(item["path"]).read_bytes(), "image/jpeg") for item in frames]
        response = self.google.generate_json(prompt, images=image_inputs)
        raw_windows = response.get("windows")
        if not isinstance(raw_windows, list):
            raise ValueError("畫面分析未返回有效的旁白窗口；可以手動建立時間窗")
        windows = [NarrationWindow.model_validate({
            **item, "id": str(item.get("id") or f"window_{uuid.uuid4().hex[:16]}"),
            "previewId": preview.id, "order": index, "status": "draft",
        }) for index, item in enumerate(raw_windows)]
        return validate_windows(windows, preview, valid_frame_ids={item["id"] for item in frames}, require_ready=False)

    def _extract_frames(self, root: Path, preview: ProjectPreview, path: Path) -> list[dict[str, Any]]:
        times = {round((clip.timelineStart + clip.timelineEnd) / 2, 3) for clip in preview.clips}
        if len(times) < min(MAX_EVIDENCE_FRAMES, max(1, len(preview.clips))):
            for ratio_index in range(MAX_EVIDENCE_FRAMES):
                times.add(round(preview.durationSeconds * (ratio_index + 0.5) / MAX_EVIDENCE_FRAMES, 3))
                if len(times) >= min(MAX_EVIDENCE_FRAMES, max(1, len(preview.clips) * 2)):
                    break
        ordered = sorted(time for time in times if 0 <= time < preview.durationSeconds)[:MAX_EVIDENCE_FRAMES]
        directory = root / "previews" / preview.id / "frames"
        directory.mkdir(parents=True, exist_ok=True)
        frames: list[dict[str, Any]] = []
        total_bytes = 0
        for index, timestamp in enumerate(ordered):
            frame_path = directory / f"frame_{index + 1:02d}.jpg"
            command = [self.settings.ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={MAX_FRAME_EDGE}:{MAX_FRAME_EDGE}:force_original_aspect_ratio=decrease", "-f", "image2", str(frame_path)]
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
            if result.returncode or not frame_path.is_file():
                continue
            with Image.open(frame_path) as source:
                image = source.convert("RGB")
                image.thumbnail((MAX_FRAME_EDGE, MAX_FRAME_EDGE))
                encoded = b""
                for quality in (82, 72, 62, 52, 42):
                    stream = BytesIO()
                    image.save(stream, format="JPEG", quality=quality, optimize=True)
                    encoded = stream.getvalue()
                    if len(encoded) <= MAX_FRAME_BYTES:
                        break
                if len(encoded) > MAX_FRAME_BYTES or total_bytes + len(encoded) > MAX_TOTAL_FRAME_BYTES:
                    frame_path.unlink(missing_ok=True)
                    continue
                frame_path.write_bytes(encoded)
                total_bytes += len(encoded)
            shot_ids = [clip.shotId for clip in preview.clips if clip.timelineStart <= timestamp <= clip.timelineEnd]
            frames.append({"id": f"frame_{index + 1:02d}", "timeSeconds": timestamp, "shotIds": shot_ids,
                           "path": str(frame_path), "relativePath": str(frame_path.relative_to(root))})
        return frames

    @staticmethod
    def _project_file(root: Path, relative_path: str) -> Path:
        path = (root / relative_path).resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError("剪辑预览文件不存在")
        return path


def validate_windows(windows: list[NarrationWindow], preview: ProjectPreview, *, valid_frame_ids: set[str] | None = None, require_ready: bool = True) -> list[NarrationWindow]:
    normalized = sorted(windows, key=lambda item: (item.startSeconds, item.endSeconds, item.order))
    previous_end = 0.0
    frame_ids = valid_frame_ids
    for index, window in enumerate(normalized):
        if window.previewId != preview.id:
            raise ValueError("旁白时间窗属于过期剪辑预览")
        if not math.isfinite(window.startSeconds) or not math.isfinite(window.endSeconds):
            raise ValueError("时间窗起止必须是有限数值")
        if window.endSeconds <= window.startSeconds or window.endSeconds > preview.durationSeconds:
            raise ValueError("旁白时间窗必须在剪辑片长内且结束时间晚于开始时间")
        if index and window.startSeconds < previous_end - 1e-6:
            raise ValueError("旁白时间窗不能相互重叠")
        if not window.text.strip():
            raise ValueError("旁白时间窗文本不能为空")
        if frame_ids is not None and any(frame_id not in frame_ids for frame_id in window.evidenceFrameIds):
            raise ValueError("旁白时间窗引用了无效的实际抽帧")
        source_ids = [clip.shotId for clip in preview.clips if clip.timelineStart < window.endSeconds and clip.timelineEnd > window.startSeconds]
        window.sourceShotIds = list(dict.fromkeys(source_ids))
        if not source_ids:
            raise ValueError("旁白时间窗未覆盖任何实际镜头")
        window.order = index
        if require_ready:
            window.status = "ready"
        previous_end = window.endSeconds
    return normalized
