from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime, timezone
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


class AssetImage(BaseModel):
    imageId: str
    path: str
    mimeType: Literal["image/png", "image/jpeg", "image/webp"]
    size: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ProjectAsset(BaseModel):
    id: str
    kind: Literal["character", "location", "reference"]
    name: str
    description: str = ""
    entityName: str | None = None
    scopeShotIds: list[str] = Field(default_factory=list)
    image: AssetImage | None = None
    revision: int = 0


class FrameVersion(BaseModel):
    id: str
    path: str
    source: Literal["generated", "upload", "legacy"] = "generated"
    generatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model: str = ""
    promptSnapshot: str = ""
    inputSignature: str = ""
    referenceSnapshots: list[str] = Field(default_factory=list)
    firstFrameVersionId: str | None = None


class FrameJob(BaseModel):
    id: str
    requestId: str
    groupId: str | None = None
    status: Literal["queued", "generating", "complete", "failed"] = "queued"
    errorMessage: str | None = None
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    inputSnapshot: dict[str, Any] = Field(default_factory=dict)


class FrameSlot(BaseModel):
    referenceMode: Literal["auto", "manual"] = "auto"
    assetIds: list[str] = Field(default_factory=list)
    selectedVersionId: str | None = None
    versions: list[FrameVersion] = Field(default_factory=list)
    job: FrameJob | None = None

    @model_validator(mode="before")
    @classmethod
    def import_legacy_upload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        legacy_path = value.pop("_legacyPath", None)
        if legacy_path and not value.get("versions"):
            version_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"video-studio:legacy-frame:{legacy_path}"))
            value["versions"] = [{"id": version_id, "path": legacy_path, "source": "legacy"}]
            value["selectedVersionId"] = version_id
        return value


class ShotVideo(BaseModel):
    provider: Literal["google_vertex", "google_gemini", "google_agent_platform", "google_gemini_omni_1_1"] = "google_agent_platform"
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
    directorFirstFramePrompt: str = ""
    directorLastFramePrompt: str = ""
    motionBeats: list[MotionBeat] = Field(default_factory=list)
    transitionIn: Literal["hard_cut", "dissolve", "match_cut"] = "hard_cut"
    transitionReason: str = ""
    uploads: ShotUploads = Field(default_factory=ShotUploads)
    frames: dict[Literal["first", "last"], FrameSlot] = Field(default_factory=lambda: {"first": FrameSlot(), "last": FrameSlot()})
    video: ShotVideo | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_frames(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        uploads = value.get("uploads") or {}
        frames = dict(value.get("frames") or {})
        for role, key in (("first", "firstFrame"), ("last", "lastFrame")):
            if role not in frames:
                frames[role] = {"_legacyPath": uploads.get(key)}
        value.setdefault("directorFirstFramePrompt", value.get("firstFramePrompt", ""))
        value.setdefault("directorLastFramePrompt", value.get("lastFramePrompt", ""))
        value["frames"] = frames
        return value

    @model_validator(mode="after")
    def project_selected_frames_to_uploads(self) -> "Shot":
        for role, key in (("first", "firstFrame"), ("last", "lastFrame")):
            slot = self.frames[role]
            selected = next((item for item in slot.versions if item.id == slot.selectedVersionId), None)
            setattr(self.uploads, key, selected.path if selected else None)
        return self


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
    schemaVersion: int = 2
    assets: list[ProjectAsset] = Field(default_factory=list)
    directorStage: str = "complete"
    directorRequest: dict[str, Any] | None = None
    directorOutline: DirectorOutline | None = None
    editPlan: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["ready", "generating", "failed"] = "ready"
    shots: list[Shot] = Field(default_factory=list)
    narration: Narration = Field(default_factory=Narration)
    finalVideoPath: str | None = None
    errorMessage: str | None = None

    @model_validator(mode="before")
    @classmethod
    def create_entity_asset_slots(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        value = dict(value)
        if value.get("assets") or not value.get("directorOutline"):
            return value
        outline = value["directorOutline"]
        if isinstance(outline, DirectorOutline):
            outline = outline.model_dump(mode="python")
        project_id = value.get("projectId", "")
        assets = []
        for kind, entities in (("character", outline.get("characters", [])), ("location", outline.get("locations", []))):
            for entity in entities:
                name = entity.get("name", "").strip()
                normalized = unicodedata.normalize("NFKC", name).casefold()
                asset_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"video-studio:{project_id}:{kind}:{normalized}"))
                assets.append({
                    "id": asset_id, "kind": kind, "name": name,
                    "description": entity.get("visualIdentity") or entity.get("description", ""),
                    "entityName": name,
                })
        value["assets"] = assets
        value.setdefault("schemaVersion", 2)
        return value


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


class CreateAssetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    scopeShotIds: list[str] = Field(default_factory=list)


class UpdateFrameConfigRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    referenceMode: Literal["auto", "manual"] = "auto"
    assetIds: list[str] = Field(default_factory=list)
    restoreDefaultPrompt: bool = False


class GenerateFrameRequest(BaseModel):
    requestId: str = Field(min_length=1, max_length=100)


class NarrationAudioRequest(BaseModel):
    speed: float = Field(default=1.0, ge=0.5, le=2.0)

