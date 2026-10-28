from __future__ import annotations

import array
import wave
from pathlib import Path

from app.domain.models import NarrationWindow, SegmentAudio


SAMPLE_RATE = 48_000


def assemble_pcm_timeline(windows: list[NarrationWindow], segments: dict[str, tuple[SegmentAudio, bytes]], duration_seconds: float, output_path: Path) -> None:
    total_samples = round(duration_seconds * SAMPLE_RATE)
    timeline = array.array("h", [0]) * total_samples
    occupied: list[tuple[int, int]] = []
    for window in windows:
        segment = segments.get(window.id)
        if not segment:
            raise ValueError(f"时间窗 {window.id} 缺少有效配音")
        audio, pcm = segment
        if len(pcm) % 2:
            raise ValueError("旁白 PCM 样本数据无效")
        start = round(audio.placedStartSeconds * SAMPLE_RATE)
        samples = array.array("h")
        samples.frombytes(pcm)
        end = start + len(samples)
        window_start = round(window.startSeconds * SAMPLE_RATE)
        window_end = round(window.endSeconds * SAMPLE_RATE)
        if start < window_start or end > window_end:
            raise ValueError(f"时间窗 {window.id} 的配音超出自身时间范围")
        if start < 0 or end > total_samples:
            raise ValueError(f"时间窗 {window.id} 配音超出预览片长")
        if any(start < prior_end and end > prior_start for prior_start, prior_end in occupied):
            raise ValueError("旁白片段发生重叠，请调整时间窗")
        occupied.append((start, end))
        for offset, value in enumerate(samples, start):
            mixed = timeline[offset] + value
            timeline[offset] = max(-32768, min(32767, mixed))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(timeline.tobytes())
