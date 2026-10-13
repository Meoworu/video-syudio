from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import ValidationError

from app.clients.google_text import GoogleTextClient
from app.config import Settings
from app.domain.models import (
    CreateProjectRequest,
    DirectorOutline,
    DirectorShotPlan,
    Project,
    Shot,
)
from app.services.editing import rebuild_edit_plan
from app.store.project_store import ProjectStore


class DirectorService:
    """Google Vertex-only, two-stage story and shot-planning pipeline."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self.client = GoogleTextClient(settings, client=client)

    def create_project(self, request: CreateProjectRequest) -> Project:
        outline = self._generate_outline(request)
        if len(outline.scenes) != request.sceneCount:
            raise ValueError(f"导演大纲应包含 {request.sceneCount} 场，实际返回 {len(outline.scenes)} 场")
        shot_plans = self._generate_shots(request, outline)
        if len(shot_plans) != request.sceneCount:
            raise ValueError(f"导演分镜应包含 {request.sceneCount} 个镜头，实际返回 {len(shot_plans)} 个")
        return self._build_project(f"video_{uuid.uuid4().hex[:12]}", request, outline, shot_plans)

    def start_project(self, request: CreateProjectRequest, store: ProjectStore) -> Project:
        project = Project(
            projectId=f"video_{uuid.uuid4().hex[:12]}", title="正在规划故事…",
            story=request.story, aspectRatio=request.aspectRatio, style=request.style,
            status="generating", directorStage="outline",
            directorRequest=request.model_dump(mode="json"),
        )
        store.create(project)
        return project

    def run_project(self, project_id: str, store: ProjectStore) -> None:
        try:
            with store.lock(project_id):
                project = store.get(project_id)
                if project.status != "generating" or not project.directorRequest:
                    return
                request = CreateProjectRequest.model_validate(project.directorRequest)
                outline = project.directorOutline
            if outline is None:
                outline = self._generate_outline(request)
                with store.lock(project_id):
                    project = store.get(project_id)
                    project.directorOutline = outline
                    project.title = outline.title
                    project.directorStage = "shot_design"
                    store.save(project)
            plans = self._generate_shots(request, outline)
            designed = self._build_project(project_id, request, outline, plans)
            with store.lock(project_id):
                project = store.get(project_id)
                project.title = designed.title
                project.directorOutline = designed.directorOutline
                project.shots = designed.shots
                project.editPlan = designed.editPlan
                project.status = "ready"
                project.directorStage = "complete"
                project.errorMessage = None
                store.save(project)
        except Exception as error:
            with store.lock(project_id):
                project = store.get(project_id)
                project.status = "failed"
                project.directorStage = "failed"
                project.errorMessage = str(error)
                store.save(project)

    def _build_project(self, project_id: str, request: CreateProjectRequest, outline: DirectorOutline, shot_plans: list[DirectorShotPlan]) -> Project:
        if len(shot_plans) != request.sceneCount:
            raise ValueError(f"导演分镜应包含 {request.sceneCount} 个镜头，实际返回 {len(shot_plans)} 个")
        shots = []
        for index, plan in enumerate(shot_plans):
            if plan.index != index or plan.sceneIndex >= len(outline.scenes):
                raise ValueError("导演分镜序号或场景引用无效")
            if any(beat.endSeconds > plan.durationSeconds for beat in plan.motionBeats):
                raise ValueError(f"镜头 {index + 1} 的运动节拍超出镜头时长")
            scene = outline.scenes[plan.sceneIndex]
            motion_text = "；".join(
                f"{beat.startSeconds:g}-{beat.endSeconds:g} 秒：{beat.subjectAction}；"
                f"镜头运动：{beat.cameraAction or '平滑跟随'}；环境：{beat.environmentAction or '自然延续'}"
                for beat in plan.motionBeats
            )
            prompt = (
                f"{request.style}。本镜头叙事目的：{plan.narrativePurpose}。"
                f"画面行动：{plan.beat}。摄影：{plan.camera}。"
                f"严格从用户提供的首帧状态开始，并自然运动至尾帧状态；"
                f"保持人物身份、服装、道具和场景连续，不新增主体。时序：{motion_text}。"
                f"场景：{plan.locationName or scene.locationName}；连续性约束：{plan.continuityNotes}。"
                f"必须出现：{'；'.join(plan.mustAppear)}。不得出现：{'；'.join(plan.forbiddenElements)}。"
                f"全片风格：{json.dumps(outline.styleBible, ensure_ascii=False)}。"
                "镜头间不要生成字幕、文字或旁白。"
            )
            shots.append(Shot(
                id=f"shot_{index + 1:03d}", index=index, sceneIndex=plan.sceneIndex,
                title=plan.title or scene.title, prompt=prompt,
                durationSeconds=plan.durationSeconds, beat=plan.beat,
                narrativePurpose=plan.narrativePurpose, camera=plan.camera,
                visualDescription=plan.visualDescription,
                mustAppear=plan.mustAppear, forbiddenElements=plan.forbiddenElements,
                continuityNotes=plan.continuityNotes, visibleCharacters=plan.visibleCharacters,
                locationName=plan.locationName or scene.locationName,
                firstFrameDescription=plan.firstFrameDescription,
                lastFrameDescription=plan.lastFrameDescription,
                firstFramePrompt=plan.firstFramePrompt,
                lastFramePrompt=plan.lastFramePrompt,
                motionBeats=plan.motionBeats, transitionIn=plan.transitionIn,
                transitionReason=plan.transitionReason,
            ))
        project = Project(
            projectId=project_id, title=outline.title,
            story=request.story, aspectRatio=request.aspectRatio, style=request.style,
            directorOutline=outline, shots=shots,
        )
        rebuild_edit_plan(project)
        return project

    def _generate_outline(self, request: CreateProjectRequest) -> DirectorOutline:
        prompt = (
            "你是短片导演和编剧。第一阶段只规划故事，不写镜头提示词。保持因果完整、人物动机清楚、"
            "结尾有情绪或认知变化。只返回 JSON："
            '{"title":"不超过42字","logline":"一句话故事","synopsis":"完整梗概",'
            '"theme":"主题","characters":[{"name":"角色名","description":"动机与性格",'
            '"visualIdentity":"可持续识别的外观特征"}],"locations":[{"name":"地点",'
            '"description":"空间特征","visualIdentity":"跨镜头保持的环境视觉锚点"}],"scenes":[{"index":0,"title":"场名",'
            '"dramaticGoal":"场景目标","conflict":"阻碍","turningPoint":"变化点",'
            '"outcome":"结果及与下一场的衔接","locationName":"地点名","timeOfDay":"时段"}],"styleBible":{"visual":"整体影像语言",'
            '"lighting":"光线","color":"色彩","camera":"摄影风格","continuity":"连续性规则"}}。'
            f"场景数必须恰好 {request.sceneCount}。不要添加故事未提供的事实。"
            f"\n故事：{request.story}\n画面比例：{request.aspectRatio}\n用户风格：{request.style}"
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = self.client.generate_json(prompt)
                outline = DirectorOutline.model_validate(raw)
                if len(outline.scenes) != request.sceneCount:
                    raise ValueError(f"场景数量必须恰好为 {request.sceneCount}")
                return outline
            except (ValidationError, ValueError) as error:
                last_error = error
                prompt += f"\n上次输出未通过校验：{error}。请返回完整修正版 JSON。"
        raise ValueError(f"Google 导演大纲结构无效：{last_error}") from last_error

    def _generate_shots(self, request: CreateProjectRequest, outline: DirectorOutline) -> list[DirectorShotPlan]:
        prompt = (
            "你是摄影指导。第二阶段将故事大纲变成可执行的图生视频分镜。"
            "每个镜头需有可供人工审核的首帧、尾帧描述与独立图像提示词；首尾状态必须有明确变化但保持主体连续。"
            "运动节拍必须覆盖行动过程且不超镜头时长。画面中不生成字幕、文字和旁白。只返回 JSON："
            '{"shots":[{"index":0,"sceneIndex":0,"title":"镜头标题","beat":"可见动作",'
            '"narrativePurpose":"镜头在故事中的作用","durationSeconds":5,"camera":"景别、机位、焦段感和运动",'
            '"visualDescription":"空间构图、人物位置、光线和可见信息","mustAppear":["必须出现的可见事实"],'
            '"forbiddenElements":["不可出现的内容"],"continuityNotes":"跨镜头需保持的状态",'
            '"visibleCharacters":["角色名"],"locationName":"地点名",'
            '"firstFrameDescription":"动作开始时冻结画面","lastFrameDescription":"动作结束时冻结画面",'
            '"firstFramePrompt":"可直接用于生成首帧图像的英文提示词，包含构图和风格",'
            '"lastFramePrompt":"可直接用于生成尾帧图像的英文提示词，体现结束状态且身份连续",'
            '"motionBeats":[{"startSeconds":0,"endSeconds":2,"subjectAction":"主体动作",'
            '"cameraAction":"摄影机动作","environmentAction":"环境变化"}],'
            '"transitionIn":"hard_cut","transitionReason":"剪辑衔接理由"}]}。'
            f"shots 数量必须恰好 {request.sceneCount}，index 从 0 连续递增；sceneIndex 必须指向真实场景。"
            "durationSeconds 取 3-10 秒。画面提示词不得依赖未提供的素材。\n"
            f"故事大纲：{outline.model_dump_json(ensure_ascii=False)}"
        )
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = self.client.generate_json(prompt)
                items = raw.get("shots")
                if not isinstance(items, list) or len(items) != request.sceneCount:
                    raise ValueError(f"shots 数组必须恰好包含 {request.sceneCount} 个元素")
                plans = [DirectorShotPlan.model_validate(item) for item in items]
                for index, plan in enumerate(plans):
                    if plan.index != index or plan.sceneIndex >= len(outline.scenes):
                        raise ValueError("镜头 index 必须连续递增，sceneIndex 必须引用已规划场景")
                    if any(beat.endSeconds > plan.durationSeconds for beat in plan.motionBeats):
                        raise ValueError(f"镜头 {index + 1} 的运动节拍超出镜头时长")
                if {plan.sceneIndex for plan in plans} != set(range(len(outline.scenes))):
                    raise ValueError("每个导演场景必须至少被一个镜头覆盖")
                return plans
            except (ValidationError, ValueError) as error:
                last_error = error
                prompt += f"\n上次输出未通过校验：{error}。请返回完整修正版 JSON。"
        raise ValueError(f"Google 分镜结构无效：{last_error}") from last_error
