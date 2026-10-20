from __future__ import annotations

import base64
import binascii
import re
import mimetypes
import json
import subprocess
import time
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

from app.clients.google_client import build_google_client, safe_google_error
from app.config import Settings


class GoogleOmniVideoError(RuntimeError):
    """Raised when a Google Omni video task cannot be completed."""


class GoogleOmniVideoCancelled(GoogleOmniVideoError):
    """Raised when a video download is stopped after local cancellation."""


class _CancelableWriter:
    def __init__(self, destination, cancel_check) -> None:
        self.destination = destination
        self.cancel_check = cancel_check

    def write(self, chunk: bytes) -> int:
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
            self._client = build_google_client(self.settings)
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
                response_format={"type": "video", "aspect_ratio": aspect_ratio},
                generation_config={"video_config": {"task": "image_to_video"}},
            )
        except Exception as error:
            raise GoogleOmniVideoError(f"Google Omni 提交任务失败：{safe_google_error(error, self.settings)}") from None
        interaction_id = _read(response, "id")
        if not interaction_id:
            raise GoogleOmniVideoError("Google Omni 未返回 Interaction ID")
        return str(interaction_id)

    def get_interaction(self, remote_job_id: str) -> Any:
        try:
            return self.client.interactions.get(id=remote_job_id)
        except TypeError:
            try:
                return self.client.interactions.get(remote_job_id)
            except Exception as error:
                raise GoogleOmniVideoError(f"Google Omni 查询任务失败：{safe_google_error(error, self.settings)}") from None
        except Exception as error:
            raise GoogleOmniVideoError(f"Google Omni 查询任务失败：{safe_google_error(error, self.settings)}") from None

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
            interaction = self.get_interaction(remote_job_id)
            status = str(_read(interaction, "status") or "").lower()
            if status in {"completed", "complete", "failed", "cancelled", "canceled", "rejected"}:
                return interaction
            if time.monotonic() >= deadline:
                raise GoogleOmniVideoError("Google Omni 视频任务轮询超时")
            time.sleep(self.settings.google_poll_interval_seconds)

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
        uri = _read(video, "uri") or _read(video, "gcs_uri")
        try:
            if data:
                partial_path.write_bytes(base64.b64decode(str(data), validate=True))
            elif uri:
                self._download_gemini_file(str(uri), partial_path, cancel_check=cancel_check)
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

    def _download_gemini_file(self, uri: str, destination: Path, *, cancel_check=None) -> None:
        if uri.startswith("files/"):
            resource = uri
        else:
            parsed = urlparse(uri)
            if parsed.scheme != "https" or parsed.hostname != "generativelanguage.googleapis.com":
                raise GoogleOmniVideoError("Gemini 返回的文件 URI 无效")
            resource = parsed.path.removeprefix("/v1beta/")
        if not re.fullmatch(r"files/[A-Za-z0-9_-]+(?::download)?", resource):
            raise GoogleOmniVideoError("Gemini 返回的文件 URI 无效")
        file_name = resource.split(":", 1)[0]
        deadline = time.monotonic() + self.settings.google_request_timeout_seconds
        while True:
            if cancel_check and cancel_check():
                raise GoogleOmniVideoCancelled("视频任务已取消")
            info = self.client.files.get(name=file_name)
            raw_state = _read(info, "state")
            state = str(_read(raw_state, "value") or _read(raw_state, "name") or raw_state or "").upper().split(".")[-1]
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise GoogleOmniVideoError("Gemini 视频文件处理失败")
            if time.monotonic() >= deadline:
                raise GoogleOmniVideoError("Gemini 视频文件等待超时")
            time.sleep(self.settings.google_poll_interval_seconds)
        if cancel_check and cancel_check():
            raise GoogleOmniVideoCancelled("视频任务已取消")
        download_uri = f"https://generativelanguage.googleapis.com/v1beta/{file_name}:download?alt=media"
        with destination.open("wb") as output_file:
            self.client.files.download(
                file=download_uri,
                destination=_CancelableWriter(output_file, cancel_check),
            )

    @staticmethod
    def _image_input(path: Path) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        return {"type": "image", "data": base64.b64encode(path.read_bytes()).decode("ascii"), "mime_type": mime_type}


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
        output_video = getattr(value, "output_video", None)
        if output_video is not None:
            return output_video
        if getattr(value, "type", None) == "video":
            return value
        for key in ("content", "contents", "steps", "response", "outputs", "output_video"):
            found = _find_video(getattr(value, key, None))
            if found is not None:
                return found
    return None
