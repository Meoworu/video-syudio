from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ShotUploads(BaseModel):
    firstFrame: str | None = None
    lastFrame: str | None = None


class ShotVideo(BaseModel):
    provider: Literal["google_vertex"] = "google_vertex"
    model: str
    status: Literal["idle", "submitting", "generating", "downloading", "complete", "cancelled", "failed"] = "idle"
    remoteJobId: str | None = None
    path: str | None = None
    errorMessage: str | None = None


class Shot(BaseModel):
    id: str
    index: int = Field(ge=0)
    title: str
    prompt: str
    durationSeconds: int = Field(ge=3, le=10)
    uploads: ShotUploads = Field(default_factory=ShotUploads)
    video: ShotVideo | None = None


class Narration(BaseModel):
    manuscript: str = ""
    audioPath: str | None = None
    status: Literal["idle", "draft", "audio_ready", "failed"] = "idle"


class Project(BaseModel):
    projectId: str
    title: str
    story: str
    aspectRatio: Literal["9:16", "16:9"]
    style: str
    status: Literal["ready", "generating", "failed"] = "ready"
    shots: list[Shot] = Field(default_factory=list)
    narration: Narration = Field(default_factory=Narration)
    finalVideoPath: str | None = None
    errorMessage: str | None = None


class CreateProjectRequest(BaseModel):
    story: str = Field(min_length=1)
    aspectRatio: Literal["9:16", "16:9"] = "9:16"
    style: str = "cinematic animated short film"
    sceneCount: int = Field(default=3, ge=1, le=12)

