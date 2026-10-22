from app.config import Settings
from app.domain.models import CreateProjectRequest
from app.services.director_service import DirectorService
from app.store.project_store import ProjectStore


class FakeGoogleText:
    def __init__(self):
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        if self.calls == 1:
            return {
                "title": "纸船归途", "logline": "纸船寻找归处。", "synopsis": "一只纸船沿溪流前行。",
                "theme": "归属", "characters": [{"name": "纸船", "description": "勇敢", "visualIdentity": "蓝色折纸"}],
                "locations": [{"name": "溪流", "description": "林间小溪", "visualIdentity": "青石與水草"}],
                "scenes": [{"index": 0, "title": "溪流", "dramaticGoal": "前行", "conflict": "急流", "turningPoint": "找到方向", "outcome": "继续前行", "locationName": "溪流", "timeOfDay": "清晨"}],
                "styleBible": {"visual": "手绘动画", "lighting": "柔和晨光", "color": "青绿", "camera": "电影感", "continuity": "蓝色纸船"},
            }
        return {"shots": [{
            "index": 0, "sceneIndex": 0, "title": "顺流而下", "beat": "纸船越过石缝", "narrativePurpose": "开启旅程",
            "durationSeconds": 5, "camera": "低机位跟拍", "visualDescription": "小溪中漂流的纸船",
            "firstFrameDescription": "纸船刚进入溪流", "lastFrameDescription": "纸船越过石缝",
            "firstFramePrompt": "small blue paper boat entering stream", "lastFramePrompt": "small blue paper boat past rocks",
            "motionBeats": [{"startSeconds": 0, "endSeconds": 5, "subjectAction": "漂过石缝", "cameraAction": "跟随", "environmentAction": "水流轻晃"}],
        }]}


def test_director_generates_validated_outline_and_shot_plan():
    service = DirectorService(Settings(_env_file=None), client=FakeGoogleText())
    project = service.create_project(CreateProjectRequest(story="一只纸船寻找归处。", sceneCount=1))
    assert project.directorOutline is not None
    assert len(project.directorOutline.scenes) == 1
    assert project.shots[0].firstFramePrompt
    assert project.editPlan[-1]["timelineEnd"] == 5


class ScienceGoogleText:
    def __init__(self, *, include_character=False):
        self.prompts = []
        self.include_character = include_character

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if len(self.prompts) == 1 or self.include_character:
            return {
                "title": "水的循环", "logline": "观察水在自然中的变化。", "synopsis": "水受热蒸发，遇冷凝结并降落。",
                "theme": "水循环", "characters": ([{"name": "讲解员", "description": "", "visualIdentity": ""}] if self.include_character else []),
                "locations": [{"name": "云层", "description": "大气中的云层", "visualIdentity": "白色云雾"}],
                "scenes": [{"index": 0, "title": "水汽上升", "dramaticGoal": "观察蒸发", "conflict": "受热", "turningPoint": "液体变为水汽", "outcome": "水汽上升", "locationName": "云层"}],
                "styleBible": {"visual": "科学示意图"},
            }
        return {"shots": [{
            "index": 0, "sceneIndex": 0, "title": "水汽上升", "beat": "水汽缓慢上升", "narrativePurpose": "说明蒸发",
            "durationSeconds": 5, "camera": "微观剖面", "visualDescription": "水滴与水汽",
            "firstFrameDescription": "水滴受热", "lastFrameDescription": "水汽上升",
            "firstFramePrompt": "water droplets", "lastFramePrompt": "water vapor rising",
            "motionBeats": [{"startSeconds": 0, "endSeconds": 5, "subjectAction": "水汽上升"}],
        }]}


def test_science_project_has_no_character_assets_or_shot_characters():
    client = ScienceGoogleText()
    service = DirectorService(Settings(_env_file=None), client=client)
    project = service.create_project(CreateProjectRequest(story="解释水循环", projectType="science", sceneCount=1))

    assert project.projectType == "science"
    assert project.directorOutline is not None and project.directorOutline.characters == []
    assert project.shots[0].visibleCharacters == []
    assert [asset.kind for asset in project.assets] == ["location"]
    assert "characters 必须严格为空数组" in client.prompts[0]
    assert "visibleCharacters 必须严格为空数组" in client.prompts[1]
    assert "禁止出现人类" in project.shots[0].prompt
    assert "保持主体形态" in project.shots[0].prompt


def test_science_project_type_is_saved_before_background_generation(tmp_path):
    store = ProjectStore(tmp_path)
    service = DirectorService(Settings(_env_file=None), client=ScienceGoogleText())

    created = service.start_project(CreateProjectRequest(story="解释水循环", projectType="science", sceneCount=1), store)
    persisted = store.get(created.projectId)

    assert persisted.projectType == "science"
    assert persisted.directorRequest is not None
    assert persisted.directorRequest["projectType"] == "science"


def test_science_director_rejects_character_outline_after_bounded_retries():
    service = DirectorService(Settings(_env_file=None), client=ScienceGoogleText(include_character=True))
    try:
        service.create_project(CreateProjectRequest(story="解释水循环", projectType="science", sceneCount=1))
    except ValueError as error:
        assert "大纲结构无效" in str(error)
        assert "characters 必须为空数组" in str(error)
    else:
        raise AssertionError("科普导演必须拒绝包含人物的生成大纲")
