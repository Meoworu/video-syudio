from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class DirectorCharacter(BaseModel):
    name: str
    description: str
    visualIdentity: str


class DirectorLocation(BaseModel):
    name: str
    description: str
    visualIdentity: str


class DirectorScene(BaseModel):
    index: int = Field(ge=0)
    title: str
    dramaticGoal: str
    conflict: str
    turningPoint: str
    outcome: str
    locationName: str = ""
    timeOfDay: str = ""


class DirectorOutline(BaseModel):
    title: str = Field(min_length=1, max_length=42)
    logline: str
    synopsis: str
    theme: str
    characters: list[DirectorCharacter]
    locations: list[DirectorLocation] = Field(default_factory=list)
    scenes: list[DirectorScene]
    styleBible: dict[str, str]

    @model_validator(mode="after")
    def validate_scenes(self) -> "DirectorOutline":
        if [scene.index for scene in self.scenes] != list(range(len(self.scenes))):
            raise ValueError("导演场景序号必须从 0 连续递增")
        if len({item.name for item in self.characters}) != len(self.characters):
            raise ValueError("角色名称必须唯一")
        return self


class MotionBeat(BaseModel):
    startSeconds: float = Field(ge=0)
    endSeconds: float = Field(gt=0)
    subjectAction: str
    cameraAction: str = ""
    environmentAction: str = ""

    @model_validator(mode="after")
    def validate_range(self) -> "MotionBeat":
        if self.endSeconds <= self.startSeconds:
            raise ValueError("运动节拍结束时间必须晚于开始时间")
        return self


class DirectorShotPlan(BaseModel):
    index: int = Field(ge=0)
    sceneIndex: int = Field(ge=0)
    title: str
    beat: str
    narrativePurpose: str
    durationSeconds: int = Field(ge=3, le=10)
    camera: str
    visualDescription: str
    mustAppear: list[str] = Field(default_factory=list)
    forbiddenElements: list[str] = Field(default_factory=list)
    continuityNotes: str = ""
    visibleCharacters: list[str] = Field(default_factory=list)
    locationName: str = ""
    firstFrameDescription: str
    lastFrameDescription: str
    firstFramePrompt: str
    lastFramePrompt: str
    motionBeats: list[MotionBeat] = Field(min_length=1, max_length=4)
    transitionIn: Literal["hard_cut", "dissolve", "match_cut"] = "hard_cut"
    transitionReason: str = ""


class NarrationSentence(BaseModel):
    id: str
    order: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=600)
    narrativeFunction: str = ""
    sourceShotIndexes: list[int] = Field(default_factory=list)
    emotion: str = ""
    delivery: str = ""
    paceClass: Literal["slow", "natural", "brisk", "urgent"] = "natural"
    pauseAfterSeconds: float = Field(default=0.2, ge=0, le=2)
    estimatedDurationSeconds: float | None = Field(default=None, gt=0)


class NarrationCue(BaseModel):
    sentenceId: str
    startSeconds: float = Field(ge=0)
    endSeconds: float = Field(gt=0)
    startShotIndex: int = Field(ge=0)
    endShotIndex: int = Field(ge=0)
    crossesShotBoundary: bool = False


class NarrationTake(BaseModel):
    id: str
    path: str
    durationSeconds: float = Field(gt=0)
    speed: float = Field(ge=0.5, le=2)
    status: Literal["ready", "selected", "failed"] = "ready"


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
    sceneIndex: int = Field(default=0, ge=0)
    beat: str = ""
    narrativePurpose: str = ""
    camera: str = ""
    visualDescription: str = ""
    mustAppear: list[str] = Field(default_factory=list)
    forbiddenElements: list[str] = Field(default_factory=list)
    continuityNotes: str = ""
    visibleCharacters: list[str] = Field(default_factory=list)
    locationName: str = ""
    firstFrameDescription: str = ""
    lastFrameDescription: str = ""
    firstFramePrompt: str = ""
    lastFramePrompt: str = ""
    motionBeats: list[MotionBeat] = Field(default_factory=list)
    transitionIn: Literal["hard_cut", "dissolve", "match_cut"] = "hard_cut"
    transitionReason: str = ""
    uploads: ShotUploads = Field(default_factory=ShotUploads)
    video: ShotVideo | None = None


class Narration(BaseModel):
    manuscript: str = ""
    voiceStyle: str = ""
    voiceDirection: str = ""
    sentences: list[NarrationSentence] = Field(default_factory=list)
    alignment: list[NarrationCue] = Field(default_factory=list)
    targetDurationSeconds: float | None = None
    estimatedDurationSeconds: float | None = None
    audioPath: str | None = None
    audioDurationSeconds: float | None = None
    timingWarning: str | None = None
    takes: list[NarrationTake] = Field(default_factory=list)
    selectedTakeId: str | None = None
    status: Literal["idle", "draft", "audio_ready", "failed"] = "idle"


class Project(BaseModel):
    projectId: str
    title: str
    story: str
    aspectRatio: Literal["9:16", "16:9"]
    style: str
    directorStage: str = "complete"
    directorRequest: dict[str, Any] | None = None
    directorOutline: DirectorOutline | None = None
    editPlan: list[dict[str, Any]] = Field(default_factory=list)
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


class UpdateShotRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    durationSeconds: int | None = Field(default=None, ge=3, le=10)
    transitionIn: Literal["hard_cut", "dissolve", "match_cut"] | None = None


class NarrationAudioRequest(BaseModel):
    speed: float = Field(default=1.0, ge=0.5, le=2.0)

