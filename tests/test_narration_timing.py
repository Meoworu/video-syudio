import pytest

from app.domain.models import NarrationSentence, Project, Shot
from app.services.narration_timing import align_narration


def test_alignment_places_complete_sentence_across_shot_boundary():
    project = Project(
        projectId="video_test1234", title="测试", story="故事", aspectRatio="9:16", style="style",
        shots=[
            Shot(id="shot_001", index=0, title="一", prompt="一", durationSeconds=3),
            Shot(id="shot_002", index=1, title="二", prompt="二", durationSeconds=3),
        ],
    )
    sentence = NarrationSentence(id="narration_000", order=0, text="纸船越过石缝，沿着清晨的溪流继续寻找回家的方向。")
    aligned, cues, target, _ = align_narration(project, [sentence])
    assert aligned[0].estimatedDurationSeconds is not None
    assert cues[0].crossesShotBoundary
    assert target == 5.04


def test_alignment_rejects_duplicate_sentence_ids():
    project = Project(
        projectId="video_test1234", title="测试", story="故事", aspectRatio="9:16", style="style",
        shots=[Shot(id="shot_001", index=0, title="一", prompt="一", durationSeconds=5)],
    )
    sentence = NarrationSentence(id="same", order=0, text="完整的一句话。")
    duplicate = sentence.model_copy(update={"order": 1})
    with pytest.raises(ValueError, match="ID 必须唯一"):
        align_narration(project, [sentence, duplicate])
