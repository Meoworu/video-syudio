from app.config import Settings
from app.domain.models import CreateProjectRequest
from app.services.director_service import DirectorService


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
