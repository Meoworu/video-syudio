from __future__ import annotations

import re

from app.domain.models import NarrationCue, NarrationSentence, Project
from app.services.editing import project_duration


_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)?")
_PACE = {"slow": 0.82, "natural": 1.0, "brisk": 1.08, "urgent": 1.15}


def estimate_sentence_duration(sentence: NarrationSentence) -> float:
    cjk = len(_CJK.findall(sentence.text))
    latin = len(_LATIN_WORD.findall(sentence.text))
    spoken_seconds = (cjk / 3.8 + latin / 2.6) / _PACE[sentence.paceClass]
    punctuation_pauses = sum(sentence.text.count(mark) for mark in "，,、；;：:") * 0.12
    punctuation_pauses += sum(sentence.text.count(mark) for mark in "。！？?!") * 0.22
    return round(max(0.25, spoken_seconds + min(1.4, punctuation_pauses)), 3)


def align_narration(project: Project, sentences: list[NarrationSentence]) -> tuple[list[NarrationSentence], list[NarrationCue], float, float]:
    if not project.shots:
        raise ValueError("项目没有可用于旁白对齐的镜头")
    if [item.order for item in sentences] != list(range(len(sentences))):
        raise ValueError("旁白句子顺序必须从 0 连续递增")
    if len({item.id for item in sentences}) != len(sentences):
        raise ValueError("旁白句子 ID 必须唯一")
    shot_starts: list[tuple[int, float, float]] = []
    if project.editPlan:
        shot_starts = [(int(clip["shotIndex"]), float(clip["timelineStart"]), float(clip["timelineEnd"])) for clip in project.editPlan]
    else:
        cursor = 0.0
        for shot in sorted(project.shots, key=lambda item: item.index):
            shot_starts.append((shot.index, cursor, cursor + shot.durationSeconds))
            cursor += shot.durationSeconds
    cursor = project_duration(project)
    target = round(cursor * 0.84, 3)
    timeline_cursor = 0.0
    aligned: list[NarrationSentence] = []
    cues: list[NarrationCue] = []
    for sentence in sentences:
        if not sentence.text.strip() or sentence.text.strip()[-1] not in "。！？?!":
            raise ValueError(f"旁白句子 {sentence.id} 必须为完整句并以标点结尾")
        if any(index not in {shot.index for shot in project.shots} for index in sentence.sourceShotIndexes):
            raise ValueError(f"旁白句子 {sentence.id} 引用了不存在的镜头")
        # Provider estimates are advisory only; timeline placement is calculated
        # from the validated text and shared local speech policy.
        duration = estimate_sentence_duration(sentence)
        sentence = sentence.model_copy(update={"estimatedDurationSeconds": duration})
        start = timeline_cursor
        end = start + duration
        if end > cursor + 1.5:
            raise ValueError(f"旁白预计超出成片时长：{end:.1f}s / {cursor:.1f}s，请精简文案")
        start_shot = _shot_at(shot_starts, start)
        end_shot = _shot_at(shot_starts, max(start, end - 0.001))
        cues.append(NarrationCue(
            sentenceId=sentence.id, startSeconds=round(start, 3), endSeconds=round(end, 3),
            startShotIndex=start_shot, endShotIndex=end_shot,
            crossesShotBoundary=start_shot != end_shot,
        ))
        aligned.append(sentence)
        timeline_cursor = end + sentence.pauseAfterSeconds
    estimated = round(sum(item.estimatedDurationSeconds or 0 for item in aligned), 3)
    return aligned, cues, target, estimated


def split_manuscript(text: str) -> list[NarrationSentence]:
    parts = [part.strip() for part in re.findall(r"[^。！？?!]+[。！？?!]?", text) if part.strip()]
    sentences = []
    for index, part in enumerate(parts):
        normalized = part if part[-1] in "。！？?!" else f"{part}。"
        sentences.append(NarrationSentence(id=f"narration_{index:03d}", order=index, text=normalized))
    return sentences


def _shot_at(shots: list[tuple[int, float, float]], timestamp: float) -> int:
    for index, start, end in shots:
        if start <= timestamp < end:
            return index
    return shots[-1][0]
