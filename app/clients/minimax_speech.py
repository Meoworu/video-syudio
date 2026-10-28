from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings


class MiniMaxSpeechError(RuntimeError):
    """Raised when MiniMax cannot produce a narration take."""


@dataclass(frozen=True)
class SpeechResult:
    audio_bytes: bytes
    mime_type: str
    provider_request_id: str | None = None
    reported_duration_seconds: float | None = None


class MiniMaxSpeechClient:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.minimax_speech_timeout_seconds)

    def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        emotion: str = "neutral",
        speed: float = 1.0,
        model: str | None = None,
        retry_transient_errors: bool = True,
    ) -> SpeechResult:
        if not text.strip():
            raise ValueError("旁白文本不能为空")
        if not self.settings.minimax_api_key:
            raise MiniMaxSpeechError("未配置 MINIMAX_API_KEY")
        payload: dict[str, Any] = {
            "model": model or self.settings.minimax_speech_model,
            "text": text.strip(),
            "stream": False,
            "language_boost": "Chinese",
            "output_format": "hex",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": max(0.5, min(2.0, float(speed))),
                "vol": 1.0,
                "pitch": 0,
                "emotion": emotion,
            },
            "audio_setting": {"format": "mp3", "sample_rate": 32000, "bitrate": 128000, "channel": 1},
        }
        response = None
        max_retries = self.settings.minimax_max_retries if retry_transient_errors else 0
        for attempt in range(max_retries + 1):
            try:
                response = self.client.post(
                    self.settings.minimax_speech_url,
                    headers={"Authorization": f"Bearer {self.settings.minimax_api_key}"},
                    json=payload,
                )
                if response.status_code in {408, 425, 429, 500, 502, 503, 504} and attempt < max_retries:
                    time.sleep(self.settings.retry_backoff_seconds * (2 ** attempt))
                    continue
                response.raise_for_status()
                break
            except httpx.TransportError:
                if attempt >= max_retries:
                    raise
                time.sleep(self.settings.retry_backoff_seconds * (2 ** attempt))
        if response is None:
            raise MiniMaxSpeechError("MiniMax 请求重试耗尽")
        response.raise_for_status()
        body = response.json()
        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code", 0) not in (0, "0"):
            raise MiniMaxSpeechError(base_resp.get("status_msg") or "MiniMax 旁白生成失败")
        encoded = (body.get("data") or {}).get("audio")
        if not isinstance(encoded, str) or not encoded:
            raise MiniMaxSpeechError("MiniMax 未返回旁白音频")
        try:
            audio = bytes.fromhex(encoded)
        except ValueError:
            try:
                audio = base64.b64decode(encoded, validate=True)
            except Exception as error:
                raise MiniMaxSpeechError("MiniMax 音频编码无效") from error
        if not audio:
            raise MiniMaxSpeechError("MiniMax 返回了空音频")
        length_ms = (body.get("extra_info") or {}).get("audio_length")
        return SpeechResult(
            audio_bytes=audio,
            mime_type="audio/mpeg",
            provider_request_id=body.get("trace_id"),
            reported_duration_seconds=float(length_ms) / 1000 if length_ms is not None else None,
        )

