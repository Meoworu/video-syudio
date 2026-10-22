import pytest

from app.config import Settings
from app.domain.models import CreateProjectRequest, ProductionScript, Project, Shot
from app.services.director_service import DirectorService
from app.services.story_source import split_source
from app.store.project_store import ProjectStore


class FakeGoogleText:
    def __init__(self, story="纸船沿着溪流寻找归处。", *, include_character=False, wrong_quote=False):
        self.calls = 0
        self.prompts = []
        self.story = story
        self.include_character = include_character
        self.wrong_quote = wrong_quote
        self.segments = split_source(story)

    def generate_json(self, prompt):
        self.calls += 1
        self.prompts.append(prompt)
        ids = [item.id for item in self.segments]
        if "忠实剧本拆解助手" in prompt:
            return {
                "scenes": [{
                    "index": 0, "title": "原文场景", "sourceSegmentIds": ids,
                    "locationName": "溪流" if "溪流" in self.story else "", "beats": [{
                        "kind": "action", "text": "虚构动作" if self.wrong_quote else self.story,
                        "sourceSegmentIds": ids,
                    }],
                }],
                "characters": ([{"name": "讲解员", "sourceSegmentIds": ids}] if self.include_character else []),
                "locations": ([{"name": "溪流", "sourceSegmentIds": ids}] if "溪流" in self.story else []),
                "styleBible": {"visual": "手绘动画"},
            }
        return {"shots": [{
            "index": 0, "sceneIndex": 0, "sourceBeatIndex": 0, "sourceSegmentIds": ids, "title": "顺流而下",
            "beat": self.story, "narrativePurpose": "呈现原文", "durationSeconds": 5,
            "camera": "低机位跟拍", "visualDescription": "小溪中的纸船",
            "locationName": "", "visibleCharacters": [],
            "firstFrameDescription": "开始状态", "lastFrameDescription": "结束状态",
            "firstFramePrompt": "small paper boat entering stream", "lastFramePrompt": "paper boat downstream",
            "motionBeats": [{"startSeconds": 0, "endSeconds": 5, "subjectAction": self.story}],
        }]}


def test_director_preserves_story_and_generates_source_linked_script_and_shot():
    story = "  纸船沿着溪流寻找归处。\n"
    client = FakeGoogleText(story)
    project = DirectorService(Settings(_env_file=None), client=client).create_project(
        CreateProjectRequest(story=story, sceneCount=1),
    )
    assert project.story == story
    assert project.directorMode == "source_preserving"
    assert project.directorOutline is None
    assert project.productionScript is not None
    assert "".join(item.text for item in project.productionScript.sourceSegments) == story
    assert project.shots[0].sourceSegmentIds == [item.id for item in project.productionScript.sourceSegments]
    assert story in client.prompts[1]
    assert project.editPlan[-1]["timelineEnd"] == 5
    assert project.shots[0].locationName == "溪流"
    assert any(asset.kind == "location" and asset.entityName == "溪流" for asset in project.assets)


class ScienceGoogleText(FakeGoogleText):
    def __init__(self, story="解释水循环", *, include_character=False):
        super().__init__(story, include_character=include_character)

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        self.calls += 1
        ids = [item.id for item in self.segments]
        if "忠实剧本拆解助手" in prompt:
            return {
                "scenes": [{"index": 0, "title": "水循环", "sourceSegmentIds": ids,
                            "beats": [{"text": self.story, "sourceSegmentIds": ids}]}],
                "characters": ([{"name": "讲解员", "sourceSegmentIds": ids}] if self.include_character else []),
                "locations": [],
                "styleBible": {"visual": "科学示意图"},
            }
        return {"shots": [{
            "index": 0, "sceneIndex": 0, "sourceBeatIndex": 0, "sourceSegmentIds": ids, "title": "水循环",
            "beat": self.story, "narrativePurpose": "解释过程", "durationSeconds": 5,
            "camera": "微观剖面", "visualDescription": "水滴与水汽", "locationName": "",
            "visibleCharacters": [], "firstFrameDescription": "水滴受热", "lastFrameDescription": "水汽上升",
            "firstFramePrompt": "water droplets", "lastFramePrompt": "water vapor rising",
            "motionBeats": [{"startSeconds": 0, "endSeconds": 5, "subjectAction": self.story}],
        }]}


def test_science_project_has_no_character_assets_or_shot_characters():
    client = ScienceGoogleText()
    project = DirectorService(Settings(_env_file=None), client=client).create_project(
        CreateProjectRequest(story="解释水循环", projectType="science", sceneCount=1),
    )
    assert project.projectType == "science"
    assert project.productionScript and project.productionScript.characters == []
    assert project.shots[0].visibleCharacters == []
    assert project.assets == []
    assert "原文是剧情事实的最终依据" in client.prompts[1]
    assert "禁止出现人类" in project.shots[0].prompt
    assert "保持主体形态" in project.shots[0].prompt


def test_science_project_type_is_saved_before_background_generation(tmp_path):
    store = ProjectStore(tmp_path)
    service = DirectorService(Settings(_env_file=None), client=ScienceGoogleText())
    created = service.start_project(CreateProjectRequest(story="解释水循环", projectType="science", sceneCount=1), store)
    persisted = store.get(created.projectId)
    assert persisted.projectType == "science"
    assert persisted.directorMode == "source_preserving"
    assert persisted.directorRequest["projectType"] == "science"
    assert persisted.directorStage == "script_breakdown"


def test_science_director_rejects_character_without_mutating_story():
    story = "解释水循环，讲解员观察水汽。"
    client = ScienceGoogleText(story, include_character=True)
    try:
        DirectorService(Settings(_env_file=None), client=client).create_project(
            CreateProjectRequest(story=story, projectType="science", sceneCount=1),
        )
    except ValueError as error:
        assert "不能安全移除原文人物" in str(error)
    else:
        raise AssertionError("科普导演不能通过删除原文人物来满足科普规则")
    assert story in client.prompts[0]


def test_director_rejects_non_verbatim_source_quotes():
    service = DirectorService(Settings(_env_file=None), client=FakeGoogleText(wrong_quote=True))
    try:
        service.create_project(CreateProjectRequest(story="纸船沿着溪流寻找归处。", sceneCount=1))
    except ValueError as error:
        assert "精确文本" in str(error)
    else:
        raise AssertionError("来源引用必须逐字匹配原文")


def test_failed_project_reuses_valid_script_cache_for_shot_retry(tmp_path):
    store = ProjectStore(tmp_path)
    request = CreateProjectRequest(story="原文内容。", sceneCount=1)
    seed_service = DirectorService(Settings(_env_file=None), client=FakeGoogleText(request.story))
    designed = seed_service.create_project(request)
    project = Project.model_validate({
        **designed.model_dump(mode="python"),
        "status": "generating", "directorStage": "shot_design",
        "directorRequest": request.model_dump(mode="json"), "shots": [], "assets": [],
    })
    store.create(project)
    retry_client = FakeGoogleText(request.story)
    DirectorService(Settings(_env_file=None), client=retry_client).run_project(project.projectId, store)
    recovered = store.get(project.projectId)
    assert recovered.status == "ready"
    assert recovered.productionScript == designed.productionScript
    assert retry_client.calls == 1


def test_legacy_retry_migrates_empty_outline_and_preserves_story(tmp_path):
    store = ProjectStore(tmp_path)
    request = CreateProjectRequest(story="  原文故事。\n", sceneCount=1)
    legacy = Project(
        projectId="video_legacy1234", title="旧大纲标题", story=request.story,
        aspectRatio=request.aspectRatio, style=request.style,
        directorRequest=request.model_dump(mode="json"), status="generating",
        directorOutline={"title": "旧大纲标题", "logline": "改写内容", "synopsis": "改写内容", "theme": "", "characters": [], "locations": [], "scenes": [{"index": 0, "title": "旧场", "dramaticGoal": "", "conflict": "", "turningPoint": "", "outcome": ""}], "styleBible": {}},
    )
    store.create(legacy)
    DirectorService(Settings(_env_file=None), client=FakeGoogleText(request.story)).run_project(legacy.projectId, store)
    migrated = store.get(legacy.projectId)
    assert migrated.status == "ready"
    assert migrated.story == request.story
    assert migrated.directorOutline is None
    assert migrated.directorMode == "source_preserving"


def test_legacy_retry_refuses_to_overwrite_existing_shots(tmp_path):
    store = ProjectStore(tmp_path)
    request = CreateProjectRequest(story="原文。", sceneCount=1)
    legacy = Project(
        projectId="video_legacy5678", title="旧项目", story=request.story,
        aspectRatio=request.aspectRatio, style=request.style,
        directorRequest=request.model_dump(mode="json"), status="generating",
        shots=[Shot(id="shot_001", index=0, title="用户镜头", prompt="保留", durationSeconds=5)],
    )
    store.create(legacy)
    DirectorService(Settings(_env_file=None), client=FakeGoogleText(request.story)).run_project(legacy.projectId, store)
    saved = store.get(legacy.projectId)
    assert saved.status == "failed"
    assert saved.shots[0].title == "用户镜头"
    assert "不能安全迁移" in saved.errorMessage


def test_director_fails_if_request_snapshot_differs_from_original(tmp_path):
    store = ProjectStore(tmp_path)
    request = CreateProjectRequest(story="另一个故事", sceneCount=1)
    project = Project(
        projectId="video_mismatch123", title="原始标题", story="用户原文。",
        aspectRatio=request.aspectRatio, style=request.style,
        directorRequest=request.model_dump(mode="json"), status="generating",
    )
    store.create(project)
    DirectorService(Settings(_env_file=None), client=FakeGoogleText()).run_project(project.projectId, store)
    saved = store.get(project.projectId)
    assert saved.status == "failed"
    assert saved.story == "用户原文。"
    assert "快照不一致" in saved.errorMessage


@pytest.mark.parametrize("wrong_entity", ["character", "location", None])
@pytest.mark.parametrize("scene_separator", ["。", "，"])
def test_shot_entities_require_a_name_in_their_own_scene_even_with_broad_references(wrong_entity, scene_separator):
    scene_quotes = [f"小明在学校{scene_separator}", "小红在公园。"]
    story = "".join(scene_quotes)
    segments = split_source(story)
    ids = [segment.id for segment in segments]
    scene_ids = [ids[min(i, len(ids) - 1)] for i in range(2)]
    script = ProductionScript(
        sourceHash="unused-by-shot-validation", sourceSegments=segments,
        scenes=[
            {"index": i, "title": "原文场景", "sourceSegmentIds": [scene_ids[i]],
             "locationName": ["学校", "公园"][i],
             "beats": [{"text": quote, "sourceSegmentIds": [scene_ids[i]]}]}
            for i, quote in enumerate(scene_quotes)
        ],
        characters=[{"name": name, "sourceSegmentIds": ids} for name in ["小明", "小红"]],
        locations=[{"name": name, "sourceSegmentIds": ids} for name in ["学校", "公园"]],
    )

    class ShotClient:
        def generate_json(self, prompt):
            plans = []
            for i, quote in enumerate(scene_quotes):
                character_index = 1 - i if wrong_entity == "character" else i
                location_index = 1 - i if wrong_entity == "location" else i
                plans.append({
                    "index": i, "sceneIndex": i, "sourceBeatIndex": 0, "sourceSegmentIds": [scene_ids[i]], "title": "原文镜头",
                    "beat": quote, "narrativePurpose": "呈现原文", "durationSeconds": 5,
                    "camera": "固定", "visualDescription": "原文场景",
                    "visibleCharacters": [["小明"], ["小红"]][character_index],
                    "locationName": ["学校", "公园"][location_index],
                    "firstFrameDescription": "开始", "lastFrameDescription": "结束",
                    "firstFramePrompt": "start", "lastFramePrompt": "end",
                    "motionBeats": [{"startSeconds": 0, "endSeconds": 5, "subjectAction": quote}],
                })
            return {"shots": plans}

    service = DirectorService(Settings(_env_file=None), client=ShotClient())
    request = CreateProjectRequest(story=story, sceneCount=2)
    if wrong_entity:
        with pytest.raises(ValueError, match="不属于当前场景"):
            service._generate_shots(request, script)
    else:
        plans = service._generate_shots(request, script)
        assert [(plan.visibleCharacters, plan.locationName) for plan in plans] == [
            (["小明"], "学校"), (["小红"], "公园"),
        ]
