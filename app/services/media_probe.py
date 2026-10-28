from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MediaInfo:
    duration_seconds: float
    fps: float | None
    has_video: bool
    has_audio: bool


def probe_media(path: Path, ffprobe_bin: str, *, timeout_seconds: float = 30) -> MediaInfo:
    result = subprocess.run(
        [ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=False, timeout=timeout_seconds,
    )
    if result.returncode:
        raise RuntimeError(f"媒体文件校验失败：{result.stderr[-800:]}")
    try:
        payload = json.loads(result.stdout)
        duration = float(payload["format"]["duration"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"无法读取媒体文件时长：{path.name}") from error
    if duration <= 0:
        raise RuntimeError(f"媒体文件时长无效：{path.name}")
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = any(stream.get("codec_type") == "audio" for stream in streams)
    fps = None
    if video:
        rate = video.get("avg_frame_rate") or video.get("r_frame_rate")
        try:
            numerator, denominator = rate.split("/", 1)
            fps = float(numerator) / float(denominator)
        except (AttributeError, ValueError, ZeroDivisionError):
            fps = None
    return MediaInfo(duration, fps, video is not None, audio)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
