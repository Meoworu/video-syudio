from __future__ import annotations

import hashlib
from collections.abc import Iterable

from app.domain.models import ProductionScript, SourceSegment


def split_source(story: str) -> list[SourceSegment]:
    """Split at sentence/newline boundaries without changing a single source character."""
    chunks: list[str] = []
    start = 0
    index = 0
    while index < len(story):
        char = story[index]
        if char in "\r\n":
            end = index + 1
            if char == "\r" and end < len(story) and story[end] == "\n":
                end += 1
            chunks.append(story[start:end])
            start = end
            index = end
            continue
        if char in "。！？!?":
            end = index + 1
            while end < len(story) and story[end] in "。！？!?」』”’\")】》":
                end += 1
            chunks.append(story[start:end])
            start = end
            index = end
            continue
        index += 1
    if start < len(story):
        chunks.append(story[start:])
    if not chunks and story:
        chunks = [story]
    merged: list[str] = []
    pending_whitespace = ""
    for chunk in chunks:
        if chunk.isspace():
            if merged:
                merged[-1] += chunk
            else:
                pending_whitespace += chunk
            continue
        merged.append(pending_whitespace + chunk)
        pending_whitespace = ""
    if pending_whitespace:
        if merged:
            merged[-1] += pending_whitespace
        else:
            merged.append(pending_whitespace)
    chunks = merged
    return [SourceSegment(id=f"source_{i:04d}", index=i, text=text) for i, text in enumerate(chunks)]


def source_hash(story: str) -> str:
    return hashlib.sha256(story.encode("utf-8")).hexdigest()


def source_signature(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def validate_script_coverage(script: ProductionScript) -> None:
    """Require ordered, complete source coverage; adjacent scenes may share a segment."""
    flattened = [segment_id for scene in script.scenes for segment_id in scene.sourceSegmentIds]
    collapsed = [value for i, value in enumerate(flattened) if i == 0 or value != flattened[i - 1]]
    expected = [segment.id for segment in script.sourceSegments]
    if collapsed != expected:
        raise ValueError("剧本场景必须按原文顺序覆盖全部原文片段")
    locate_script_beats(script)


def locate_script_beats(script: ProductionScript) -> dict[tuple[int, int], tuple[int, int]]:
    """Locate each beat's actual occurrence while checking complete ordered coverage."""
    original = "".join(segment.text for segment in script.sourceSegments)
    source_ranges: dict[str, tuple[int, int]] = {}
    offset = 0
    for segment in script.sourceSegments:
        source_ranges[segment.id] = (offset, offset + len(segment.text))
        offset += len(segment.text)
    cursor = 0
    spans: dict[tuple[int, int], tuple[int, int]] = {}
    for scene in script.scenes:
        for beat_index, beat in enumerate(scene.beats):
            # Repeated wording elsewhere cannot stand in for the cited occurrence.
            start = max(cursor, source_ranges[beat.sourceSegmentIds[0]][0])
            end = source_ranges[beat.sourceSegmentIds[-1]][1]
            position = original.find(beat.text, start, end)
            if position < 0:
                raise ValueError("剧本行动和台词必须按原文顺序排列")
            if original[cursor:position].strip():
                raise ValueError("剧本行动和台词遗漏或改动了原文内容")
            cursor = position + len(beat.text)
            spans[(scene.index, beat_index)] = (position, cursor)
    if original[cursor:].strip():
        raise ValueError("剧本行动和台词遗漏或改动了原文内容")
    return spans


def quote_source_ids(text: str, source_segments: Iterable[SourceSegment]) -> list[str]:
    """Find the smallest contiguous source range containing an exact quote."""
    segments = list(source_segments)
    for start in range(len(segments)):
        joined = ""
        for end in range(start, len(segments)):
            joined += segments[end].text
            if text in joined:
                return [item.id for item in segments[start : end + 1]]
    return []
