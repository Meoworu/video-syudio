from __future__ import annotations

import json
import uuid
from typing import Any

from app.clients.google_text import GoogleTextClient
from app.config import Settings
from app.domain.models import CreateProjectRequest, Project, Shot


class DirectorService:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self.client = GoogleTextClient(settings, client=client)

    def create_project(self, request: CreateProjectRequest) -> Project:
        plan = self._generate_plan(request)
        shots = [
            Shot(
                id=f"shot_{index + 1:03d}",
                index=index,
                title=str(item.get("title") or f"镜头 {index + 1}"),
                prompt=str(item.get("prompt") or item.get("description") or request.story),
                durationSeconds=max(3, min(10, int(item.get("durationSeconds") or 5))),
            )
            for index, item in enumerate(plan.get("shots", []))
        ]
        if not shots:
            shots = [Shot(id="shot_001", index=0, title="开场", prompt=request.story, durationSeconds=5)]
        return Project(
            projectId=f"video_{uuid.uuid4().hex[:12]}",
            title=str(plan.get("title") or request.story[:42]),
            story=request.story,
            aspectRatio=request.aspectRatio,
            style=request.style,
            shots=shots,
        )

    def _generate_plan(self, request: CreateProjectRequest) -> dict[str, Any]:
        prompt = (
            "将下面故事拆成适合旁白驱动短视频的镜头计划。只返回 JSON，格式为 "
            '{"title":"...","shots":[{"title":"...","prompt":"...","durationSeconds":5}]}。'
            f"镜头数量约为 {request.sceneCount}，比例 {request.aspectRatio}，风格 {request.style}。故事：{request.story}"
        )
        return self.client.generate_json(prompt)

