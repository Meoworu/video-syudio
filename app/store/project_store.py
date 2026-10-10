from __future__ import annotations

import json
import re
from pathlib import Path

from app.domain.models import Project


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"video_[a-z0-9]{8,64}", project_id):
            raise ValueError("项目 ID 无效")
        return self.root / project_id

    def save(self, project: Project) -> None:
        directory = self.project_dir(project.projectId)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / ".project.json.tmp"
        temporary.write_text(json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(directory / "project.json")

    def create(self, project: Project) -> None:
        directory = self.project_dir(project.projectId)
        directory.mkdir(parents=True, exist_ok=False)
        self.save(project)

    def get(self, project_id: str) -> Project:
        path = self.project_dir(project_id) / "project.json"
        if not path.is_file():
            raise FileNotFoundError(project_id)
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Project]:
        projects = []
        for path in self.root.glob("video_*/project.json"):
            try:
                projects.append(Project.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return sorted(projects, key=lambda item: item.projectId, reverse=True)

    def save_upload(self, project_id: str, shot_id: str, role: str, content: bytes, suffix: str = ".png") -> Path:
        if role not in {"first", "last"}:
            raise ValueError("只支持 first 或 last 帧")
        directory = self.project_dir(project_id) / "frames" / shot_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{role}{suffix}"
        path.write_bytes(content)
        return path

