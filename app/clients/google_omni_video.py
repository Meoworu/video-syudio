from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.clients.google_client import build_google_video_client, safe_google_error
from app.config import Settings


class GoogleOmniVideoError(RuntimeError):
    """Raised when a Google Omni video task cannot be completed."""


class GoogleOmniVideoCancelled(GoogleOmniVideoError):
    """Raised when saving a video is stopped after local cancellation."""


class _CancelableWriter:
    def __init__(self, destination, cancel_check) -> None:
        self.destination = destination
        self.cancel_check = cancel_check

    def write(self, chunk: bytes | memoryview) -> int:
        if self.cancel_check and self.cancel_check():
            raise GoogleOmniVideoCancelled("视频任务已取消")
        return self.destination.write(chunk)


class GoogleOmniVideoClient:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = build_google_video_client(self.settings, max_http_attempts=1)
            # Interactions interprets its retry count as additional requests.
            # Disable that strategy so an ambiguous POST cannot submit twice.
            retry_config = self._client.interactions.sdk_configuration.retry_config
            retry_config.strategy = "none"
            retry_config.retry_connection_errors = False
            retry_config.max_retries = 0
        return self._client

    def create_interaction(self, *, prompt: str, first_frame: Path, last_frame: Path, aspect_ratio: str, duration_seconds: int) -> str:
        if not first_frame.is_file() or not last_frame.is_file():
            raise GoogleOmniVideoError("Google Omni 视频必须提供首帧和尾帧")
        if not 3 <= duration_seconds <= 10:
            raise GoogleOmniVideoError("Google Omni 视频时长必须在 3-10 秒之间")
        try:
            response = self.client.interactions.create(
                model=self.settings.google_omni_model,
                input=[
                    self._image_input(first_frame),
                    self._image_input(last_frame),
                    {"type": "text", "text": (
                        f"{prompt}\nCreate a video about {duration_seconds} seconds long. "
                        "[# Sources <FIRST_FRAME>@Image1 <LAST_FRAME>@Image2] "
                        "Use Image1 as the first frame and Image2 as the last frame."
                    )},
                ],
                background=True,
                store=True,
                response_format={
                    "type": "video", "aspect_ratio": aspect_ratio,
                    "delivery": "uri", "duration": f"{duration_seconds}s",
                },
                generation_config={"video_config": {"task": "image_to_video"}},
            )
        except Exception as error:
            raise GoogleOmniVideoError(
                f"Google Omni 提交失败或结果未知（不会自动重试）：{safe_google_error(error, self.settings)}"
            ) from None
        interaction_id = _read(response, "id")
        if not interaction_id:
            raise GoogleOmniVideoError("Google Omni 提交结果未知：未返回 Interaction ID。请先检查 Gemini API 活动记录，再手动决定是否重试")
        return str(interaction_id)

    def get_interaction(self, remote_job_id: str) -> Any:
        try:
            return self.client.interactions.get(id=remote_job_id)
        except TypeError:
            try:
                return self.client.interactions.get(remote_job_id)
            except Exception as error:
                raise GoogleOmniVideoError(f"Google Omni 查询任务失败：{safe_google_error(error, self.settings)}") from error
        except Exception as error:
            raise GoogleOmniVideoError(f"Google Omni 查询任务失败：{safe_google_error(error, self.settings)}") from error

    def cancel_interaction(self, remote_job_id: str) -> Any:
        try:
            return self.client.interactions.cancel(remote_job_id)
        except Exception as error:
            raise GoogleOmniVideoError(f"Google Omni 取消任务失败：{safe_google_error(error, self.settings)}") from None

    def wait_for_completion(self, remote_job_id: str, *, cancel_check=None) -> Any:
        deadline = time.monotonic() + self.settings.google_request_timeout_seconds
        while True:
            if cancel_check and cancel_check():
                self.cancel_interaction(remote_job_id)
                raise GoogleOmniVideoError("Google Omni 视频任务已取消")
            try:
                interaction = self.get_interaction(remote_job_id)
            except GoogleOmniVideoError as error:
                if not _is_transient_error(error) or time.monotonic() >= deadline:
                    raise
                time.sleep(min(self.settings.google_poll_interval_seconds, max(0, deadline - time.monotonic())))
                continue
            status = str(_read(interaction, "status") or "").lower()
            if status in {"completed", "complete", "failed", "cancelled", "canceled", "rejected"}:
                return interaction
            if time.monotonic() >= deadline:
                raise GoogleOmniVideoError("Google Omni 视频任务轮询超时")
            time.sleep(min(self.settings.google_poll_interval_seconds, max(0, deadline - time.monotonic())))

    def save_video(self, interaction: Any, output_path: Path, *, cancel_check=None) -> None:
        status = str(_read(interaction, "status") or "").lower()
        if status in {"failed", "cancelled", "canceled", "rejected"}:
            raise GoogleOmniVideoError(f"Google Omni 视频任务未成功：{status}")
        video = _find_video(interaction)
        if video is None:
            raise GoogleOmniVideoError(f"Google Omni 未返回视频，状态：{_read(interaction, 'status') or 'unknown'}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = output_path.with_name(f"{output_path.stem}.part{output_path.suffix}")
        data = _read(video, "data")
        uri = _read(video, "uri")
        try:
            if data:
                video_bytes = memoryview(base64.b64decode(str(data), validate=True))
                with partial_path.open("wb") as output_file:
                    writer = _CancelableWriter(output_file, cancel_check)
                    for offset in range(0, len(video_bytes), 1024 * 1024):
                        writer.write(video_bytes[offset:offset + 1024 * 1024])
            elif uri:
                file_name = _gemini_file_name(str(uri))
                if not file_name:
                    raise GoogleOmniVideoError("Gemini 返回了不受支持的视频文件地址")
                file_resource = self._wait_for_file(file_name, cancel_check=cancel_check)
                self.client.files.download(file=file_resource, destination=str(partial_path))
            else:
                raise GoogleOmniVideoError("Google Omni 返回了不支持的视频位置")
            if cancel_check and cancel_check():
                raise GoogleOmniVideoCancelled("视频任务已取消")
            result = subprocess.run(
                [self.settings.ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(partial_path)],
                capture_output=True, text=True, check=False,
            )
            payload = json.loads(result.stdout) if result.returncode == 0 else {}
            duration = float((payload.get("format") or {}).get("duration") or 0)
            if not partial_path.is_file() or partial_path.stat().st_size == 0 or not any(
                stream.get("codec_type") == "video" for stream in payload.get("streams", [])
            ) or duration <= 0:
                raise GoogleOmniVideoError("Google Omni 视频无效或 ffprobe 无法验证")
            partial_path.replace(output_path)
        except GoogleOmniVideoError:
            partial_path.unlink(missing_ok=True)
            raise
        except (binascii.Error, ValueError) as error:
            partial_path.unlink(missing_ok=True)
            raise GoogleOmniVideoError("Google Omni 返回的 Base64 视频无效") from error
        except Exception as error:
            partial_path.unlink(missing_ok=True)
            raise GoogleOmniVideoError(f"视频校验失败：{safe_google_error(error, self.settings)}") from None

    def _wait_for_file(self, name: str, *, cancel_check=None) -> Any:
        deadline = time.monotonic() + self.settings.google_request_timeout_seconds
        while True:
            if cancel_check and cancel_check():
                raise GoogleOmniVideoCancelled("视频任务已取消")
            try:
                resource = self.client.files.get(name=name)
            except Exception as error:
                if not _is_transient_error(error):
                    raise GoogleOmniVideoError(f"Gemini 文件查询失败：{safe_google_error(error, self.settings)}") from None
                if time.monotonic() >= deadline:
                    raise GoogleOmniVideoError(
                        f"等待 Gemini 视频文件就绪超时：{safe_google_error(error, self.settings)}"
                    ) from None
                time.sleep(min(self.settings.google_poll_interval_seconds, max(0, deadline - time.monotonic())))
                continue
            state = str(_read(resource, "state") or "").split(".")[-1].upper()
            if state == "ACTIVE":
                return resource
            if state == "FAILED":
                raise GoogleOmniVideoError("Gemini 视频文件处理失败")
            if state not in {"PROCESSING", "STATE_UNSPECIFIED", ""}:
                raise GoogleOmniVideoError(f"Gemini 视频文件状态异常：{state}")
            if time.monotonic() >= deadline:
                raise GoogleOmniVideoError("等待 Gemini 视频文件就绪超时")
            time.sleep(min(self.settings.google_poll_interval_seconds, max(0, deadline - time.monotonic())))

    @staticmethod
    def _image_input(path: Path) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        return {"type": "image", "data": base64.b64encode(path.read_bytes()).decode("ascii"), "mime_type": mime_type}


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _find_video(value: Any) -> Any | None:
    output_video = _read(value, "output_video")
    if output_video is not None:
        return output_video
    steps = _read(value, "steps")
    if not isinstance(steps, list):
        return None
    for step in steps:
        if str(_read(step, "type") or "").lower() != "model_output":
            continue
        content = _read(step, "content")
        if not isinstance(content, list):
            continue
        for item in content:
            mime_type = str(_read(item, "mime_type") or "").lower()
            if _read(item, "type") == "video" or mime_type.startswith("video/"):
                return item
    return None


def _gemini_file_name(uri: str) -> str | None:
    if uri.startswith("files/"):
        name = uri
    else:
        parsed = urlparse(uri)
        if parsed.scheme != "https" or parsed.hostname != "generativelanguage.googleapis.com":
            return None
        if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
            return None
        prefix = "/v1beta/files/"
        if not parsed.path.startswith(prefix):
            return None
        name = f"files/{parsed.path[len(prefix):]}"
    if not re.fullmatch(r"files/[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?", name):
        return None
    return name


def _http_status(error: Exception) -> int | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for value in (getattr(current, "code", None), getattr(current, "status_code", None)):
            try:
                status = int(value)
            except (TypeError, ValueError):
                continue
            if 100 <= status <= 599:
                return status
        response = getattr(current, "response", None)
        try:
            status = int(getattr(response, "status_code", None))
        except (TypeError, ValueError):
            status = None
        if status is not None and 100 <= status <= 599:
            return status
        match = re.search(r"\b([1-5]\d{2})\b", str(current))
        if match:
            return int(match.group(1))
        current = current.__cause__ or current.__context__
    return None


def _is_transient_error(error: Exception) -> bool:
    if _http_status(error) in {408, 429, 500, 502, 503, 504}:
        return True
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, (httpx.TransportError, TimeoutError, ConnectionError)):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False
