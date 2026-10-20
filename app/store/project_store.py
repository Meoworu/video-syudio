from __future__ import annotations

import json
import re
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.domain.models import Project


_LOCKS_GUARD = threading.Lock()
_PROJECT_LOCKS: dict[str, threading.RLock] = {}


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"video_[a-z0-9]{8,64}", project_id):
            raise ValueError("项目 ID 无效")
        return self.root / project_id

    @contextmanager
    def lock(self, project_id: str) -> Iterator[None]:
        key = str(self.project_dir(project_id).resolve())
        with _LOCKS_GUARD:
            lock = _PROJECT_LOCKS.setdefault(key, threading.RLock())
        with lock:
            yield

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

    def delete_project(self, project_id: str) -> None:
        """Permanently remove one project directory without following symlinks."""
        with self.lock(project_id):
            root = self.root.resolve()
            directory = self.project_dir(project_id)
            if directory.is_symlink():
                raise ValueError("项目目录不能是符号链接")
            resolved = directory.resolve()
            if resolved.parent != root:
                raise ValueError("项目目录超出数据根目录")
            if not directory.exists():
                raise FileNotFoundError(project_id)
            if not directory.is_dir():
                raise ValueError("项目路径不是目录")
            shutil.rmtree(directory)

    def save_upload(self, project_id: str, shot_id: str, role: str, content: bytes, suffix: str = ".png") -> Path:
        if role not in {"first", "last"}:
            raise ValueError("只支持 first 或 last 帧")
        if not re.fullmatch(r"shot_[a-zA-Z0-9_-]{1,64}", shot_id):
            raise ValueError("镜头 ID 无效")
        if suffix not in {".png", ".jpg", ".webp"} or not content:
            raise ValueError("图片内容或类型无效")
        directory = self.project_dir(project_id) / "frames" / shot_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{role}{suffix}"
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return path

    def save_media(self, project_id: str, relative_path: str, content: bytes) -> Path:
        root = self.project_dir(project_id).resolve()
        if relative_path.startswith("/") or "\\" in relative_path:
            raise ValueError("媒体路径无效")
        destination = root / relative_path
        if root not in destination.resolve(strict=False).parents or destination.is_symlink():
            raise ValueError("媒体路径无效")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
        return destination

