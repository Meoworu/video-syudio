from __future__ import annotations

import base64
import binascii
import mimetypes
import time
from pathlib import Path
from typing import Any

from app.clients.google_vertex import build_vertex_client, load_vertex_runtime
from app.config import Settings


class GoogleOmniVideoError(RuntimeError):
    """Raised when a Google Omni video task cannot be completed."""


class GoogleOmniVideoClient:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client
        self._runtime = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._runtime = load_vertex_runtime(self.settings)
            self._client = build_vertex_client(self.settings)
        return self._client

    def create_interaction(self, *, prompt: str, first_frame: Path, last_frame: Path, aspect_ratio: str, duration_seconds: int) -> str:
        if not first_frame.is_file() or not last_frame.is_file():
            raise GoogleOmniVideoError("Google Omni 视频必须提供首帧和尾帧")
        if not 3 <= duration_seconds <= 10:
            raise GoogleOmniVideoError("Google Omni 视频时长必须在 3-10 秒之间")
        response = self.client.interactions.create(
            model=self.settings.google_omni_model,
            input=[
                {"type": "text", "text": prompt, "background": True},
                self._image_input(first_frame, label="first frame"),
                self._image_input(last_frame, label="last frame"),
            ],
            background=True,
            store=True,
            response_format=[
                {"type": "video", "aspect_ratio": aspect_ratio, "duration": f"{duration_seconds}s"}
            ],
            generation_config={"video_config": {"task": "image_to_video"}},
        )
        interaction_id = _read(response, "id")
        if not interaction_id:
            raise GoogleOmniVideoError("Google Omni 未返回 Interaction ID")
        return str(interaction_id)

    def get_interaction(self, remote_job_id: str) -> Any:
        try:
            return self.client.interactions.get(id=remote_job_id)
        except TypeError:
            return self.client.interactions.get(remote_job_id)
        except Exception as error:
            raise GoogleOmniVideoError(f"Google Omni 查询任务失败：{error}") from error

    def cancel_interaction(self, remote_job_id: str) -> Any:
        try:
            return self.client.interactions.cancel(remote_job_id)
        except Exception as error:
            raise GoogleOmniVideoError(f"Google Omni 取消任务失败：{error}") from error

    def wait_for_completion(self, remote_job_id: str, *, cancel_check=None) -> Any:
        deadline = time.monotonic() + self.settings.google_request_timeout_seconds
        while True:
            if cancel_check and cancel_check():
                self.cancel_interaction(remote_job_id)
                raise GoogleOmniVideoError("Google Omni 视频任务已取消")
            interaction = self.get_interaction(remote_job_id)
            status = str(_read(interaction, "status") or "").lower()
            if status in {"completed", "complete", "failed", "cancelled", "canceled", "rejected"}:
                return interaction
            if time.monotonic() >= deadline:
                raise GoogleOmniVideoError("Google Omni 视频任务轮询超时")
            time.sleep(self.settings.google_poll_interval_seconds)

    def save_video(self, interaction: Any, output_path: Path) -> None:
        video = _find_video(interaction)
        if video is None:
            raise GoogleOmniVideoError(f"Google Omni 未返回视频，状态：{_read(interaction, 'status') or 'unknown'}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = _read(video, "data")
        uri = _read(video, "uri") or _read(video, "gcs_uri")
        if data:
            try:
                output_path.write_bytes(base64.b64decode(str(data), validate=True))
            except (binascii.Error, ValueError) as error:
                raise GoogleOmniVideoError("Google Omni 返回的 Base64 视频无效") from error
        elif uri and str(uri).startswith("gs://"):
            self._download_gcs(str(uri), output_path)
        else:
            raise GoogleOmniVideoError("Google Omni 返回了不支持的视频位置")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise GoogleOmniVideoError("Google Omni 视频文件为空")

    def _download_gcs(self, uri: str, destination: Path) -> None:
        try:
            from google.cloud import storage
        except ImportError as error:  # pragma: no cover
            raise GoogleOmniVideoError("未安装 google-cloud-storage") from error
        bucket_name, _, blob_name = uri[5:].partition("/")
        if not bucket_name or not blob_name:
            raise GoogleOmniVideoError("GCS 视频 URI 无效")
        runtime = self._runtime or load_vertex_runtime(self.settings)
        storage.Client(project=runtime.project, credentials=runtime.credentials).bucket(bucket_name).blob(blob_name).download_to_filename(destination)

    @staticmethod
    def _image_input(path: Path, *, label: str) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        return {"type": "image", "data": base64.b64encode(path.read_bytes()).decode("ascii"), "mime_type": mime_type, "label": label}


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _find_video(value: Any) -> Any | None:
    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return None
    if isinstance(value, dict):
        if value.get("type") == "video" or value.get("mime_type", "").startswith("video/"):
            return value
        for child in value.values():
            found = _find_video(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_video(child)
            if found is not None:
                return found
    else:
        if getattr(value, "type", None) == "video":
            return value
        for key in ("content", "contents", "steps", "response", "outputs"):
            found = _find_video(getattr(value, key, None))
            if found is not None:
                return found
    return None

