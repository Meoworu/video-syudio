import pytest

from app.domain.models import ProductionScript
from app.services.story_source import source_hash, split_source, validate_script_coverage


@pytest.mark.parametrize("story", [
    "  第一行。\r\n\r\n第二行！\n🌧️  ",
    "重复句。重复句。",
    "繁體中文與 emoji 🦊",
    "\t\n",
])
def test_source_segments_reconstruct_exact_input(story):
    segments = split_source(story)
    assert "".join(segment.text for segment in segments) == story
    assert [segment.index for segment in segments] == list(range(len(segments)))
    assert source_hash(story)


def test_story_request_keeps_whitespace_but_rejects_blank():
    from app.domain.models import CreateProjectRequest

    original = "  原文。\n"
    assert CreateProjectRequest(story=original).story == original
    with pytest.raises(ValueError, match="空白"):
        CreateProjectRequest(story=" \n\t")


def test_script_rejects_omitted_or_reordered_source_segments():
    segments = split_source("甲。乙。")
    base = {
        "sourceHash": source_hash("甲。乙。"),
        "sourceSegments": [item.model_dump() for item in segments],
        "scenes": [
            {"index": 0, "title": "场景一", "sourceSegmentIds": [segments[1].id], "beats": [
                {"text": "乙。", "sourceSegmentIds": [segments[1].id]},
            ]},
        ],
    }
    with pytest.raises(ValueError, match="覆盖全部|遗漏"):
        ProductionScript.model_validate(base)
    base["scenes"][0]["sourceSegmentIds"] = [segments[1].id, segments[0].id]
    base["scenes"][0]["beats"][0]["sourceSegmentIds"] = [segments[1].id]
    with pytest.raises(ValueError, match="顺序|遗漏"):
        ProductionScript.model_validate(base)


def test_script_requires_exact_source_quote():
    segments = split_source("她说：“回家。”")
    with pytest.raises(ValueError, match="精确文本"):
        ProductionScript.model_validate({
            "sourceHash": source_hash("她说：“回家。”"),
            "sourceSegments": [item.model_dump() for item in segments],
            "scenes": [{"index": 0, "title": "场景", "sourceSegmentIds": [segments[0].id], "beats": [
                {"kind": "dialogue", "text": "回家吧。", "sourceSegmentIds": [segments[0].id]},
            ]}],
        })


def test_beat_order_cannot_borrow_a_later_quote_outside_its_source():
    story = "先开门，再进屋。然后开门。"
    segments = split_source(story)
    ids = [segment.id for segment in segments]
    with pytest.raises(ValueError, match="遗漏"):
        ProductionScript(
            sourceHash=source_hash(story), sourceSegments=segments,
            scenes=[
                {"index": 0, "title": "进屋", "sourceSegmentIds": [ids[0]], "beats": [
                    {"text": "进屋", "sourceSegmentIds": [ids[0]]},
                ]},
                {"index": 1, "title": "倒序开门", "sourceSegmentIds": ids, "beats": [
                    {"text": "开门", "sourceSegmentIds": [ids[0]]},
                    {"text": "。", "sourceSegmentIds": [ids[1]]},
                ]},
            ],
        )


def test_repeated_quotes_in_their_own_source_segments_keep_correct_order():
    story = "开门。开门。"
    segments = split_source(story)
    script = ProductionScript(
        sourceHash=source_hash(story), sourceSegments=segments,
        scenes=[
            {"index": i, "title": "开门", "sourceSegmentIds": [segment.id], "beats": [
                {"text": segment.text, "sourceSegmentIds": [segment.id]},
            ]}
            for i, segment in enumerate(segments)
        ],
    )
    validate_script_coverage(script)


@pytest.mark.parametrize("second_intro, names, valid", [
    ("雨停了，", ["小明"], True),
    ("小红进来，", ["小明", "小红"], False),
])
def test_repeated_pronoun_quote_uses_its_actual_beat_position(second_intro, names, valid):
    story = f"小明坐下，他笑了，{second_intro}他笑了"
    segments = split_source(story)
    ids = [item.id for item in segments]
    data = {
        "sourceHash": source_hash(story), "sourceSegments": segments,
        "characters": [{"name": name, "sourceSegmentIds": ids} for name in names],
        "scenes": [
            {"index": 0, "title": "第一场", "sourceSegmentIds": ids, "beats": [
                {"text": "小明坐下，他笑了，", "sourceSegmentIds": ids},
            ]},
            {"index": 1, "title": "第二场", "sourceSegmentIds": ids, "beats": [
                {"text": second_intro, "sourceSegmentIds": ids},
                {"text": "他笑了", "sourceSegmentIds": ids},
            ], "characterReferences": [
                {"characterName": "小明", "quote": "他笑了", "sourceSegmentIds": ids},
            ]},
        ],
    }
    if valid:
        script = ProductionScript.model_validate(data)
        validate_script_coverage(script)
        assert script.entity_is_present_in_scene(script.characters[0], script.scenes[1])
    else:
        with pytest.raises(ValueError, match="前置实体"):
            ProductionScript.model_validate(data)
