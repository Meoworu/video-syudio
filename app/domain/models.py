from __future__ import annotations

import re
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


ProjectType = Literal["story", "science"]
DirectorMode = Literal["legacy_outline", "source_preserving"]


class SourceSegment(BaseModel):
    id: str
    index: int = Field(ge=0)
    text: str


class SourceBeat(BaseModel):
    kind: Literal["action", "dialogue", "information"] = "action"
    text: str = Field(min_length=1)
    sourceSegmentIds: list[str] = Field(min_length=1)


class SourceCharacterReference(BaseModel):
    characterName: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    sourceSegmentIds: list[str] = Field(min_length=1)


class ProductionCharacter(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    entityType: Literal["person", "organism"] = "person"
    description: str = ""
    visualIdentity: str = ""
    sourceSegmentIds: list[str] = Field(min_length=1)


class ProductionLocation(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    visualIdentity: str = ""
    sourceSegmentIds: list[str] = Field(min_length=1)


class ProductionScene(BaseModel):
    index: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=120)
    sourceSegmentIds: list[str] = Field(min_length=1)
    locationName: str = ""
    timeOfDay: str = ""
    beats: list[SourceBeat] = Field(min_length=1)
    characterReferences: list[SourceCharacterReference] = Field(default_factory=list)


class ProductionScript(BaseModel):
    schemaVersion: int = 1
    sourceHash: str
    inputSignature: str = ""
    sourceSegments: list[SourceSegment] = Field(min_length=1)
    scenes: list[ProductionScene] = Field(min_length=1)
    characters: list[ProductionCharacter] = Field(default_factory=list)
    locations: list[ProductionLocation] = Field(default_factory=list)
    styleBible: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_references(self) -> "ProductionScript":
        segment_ids = {item.id for item in self.sourceSegments}
        if [item.index for item in self.sourceSegments] != list(range(len(self.sourceSegments))):
            raise ValueError("原文片段序号必须连续")
        if len(segment_ids) != len(self.sourceSegments):
            raise ValueError("原文片段 ID 必须唯一")
        source_index = {item.id: item.index for item in self.sourceSegments}
        original = "".join(item.text for item in self.sourceSegments)
        source_ranges: dict[str, tuple[int, int]] = {}
        offset = 0
        for segment in self.sourceSegments:
            source_ranges[segment.id] = (offset, offset + len(segment.text))
            offset += len(segment.text)
        if [item.index for item in self.scenes] != list(range(len(self.scenes))):
            raise ValueError("剧本场景序号必须连续")

        def normalized_name(name: str) -> str:
            return unicodedata.normalize("NFKC", name.strip()).casefold()

        for entities, label in ((self.characters, "角色"), (self.locations, "场景")):
            keys = [normalized_name(item.name) for item in entities]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{label}名称必须唯一")

        locations_by_name = {item.name: item for item in self.locations}
        characters_by_name = {item.name: item for item in self.characters}
        beat_source_ranges: dict[tuple[int, int], tuple[int, int]] = {}
        source_cursor = 0
        for scene in self.scenes:
            refs = set(scene.sourceSegmentIds)
            if not refs or not refs <= segment_ids:
                raise ValueError("剧本场景引用了无效原文片段")
            if len(refs) != len(scene.sourceSegmentIds):
                raise ValueError("剧本场景不能重复引用相同原文片段")
            if [source_index[item] for item in scene.sourceSegmentIds] != sorted(source_index[item] for item in scene.sourceSegmentIds):
                raise ValueError("剧本场景中的原文片段必须按顺序排列")
            scene_source = "".join(item.text for item in self.sourceSegments if item.id in refs)
            if scene.locationName and scene.locationName not in scene_source:
                raise ValueError("剧本场景地点必须出现在对应原文片段中")
            if scene.timeOfDay and scene.timeOfDay not in scene_source:
                raise ValueError("剧本场景时段必须出现在对应原文片段中")
            for beat_index, beat in enumerate(scene.beats):
                if not set(beat.sourceSegmentIds) <= refs:
                    raise ValueError("行动或台词引用必须属于对应场景")
                if len(set(beat.sourceSegmentIds)) != len(beat.sourceSegmentIds):
                    raise ValueError("行动或台词不能重复引用相同原文片段")
                if [source_index[item] for item in beat.sourceSegmentIds] != sorted(source_index[item] for item in beat.sourceSegmentIds):
                    raise ValueError("行动或台词引用必须按原文顺序排列")
                beat_indices = [source_index[item] for item in beat.sourceSegmentIds]
                if beat_indices != list(range(beat_indices[0], beat_indices[-1] + 1)):
                    raise ValueError("行动或台词引用必须对应原文中的连续片段")
                source = "".join(item.text for item in self.sourceSegments if item.id in beat.sourceSegmentIds)
                if beat.text not in source:
                    raise ValueError("行动或台词必须是对应原文片段中的精确文本")
                search_start = max(source_cursor, source_ranges[beat.sourceSegmentIds[0]][0])
                search_end = source_ranges[beat.sourceSegmentIds[-1]][1]
                beat_start = original.find(beat.text, search_start, search_end)
                if beat_start < 0:
                    raise ValueError("剧本行动和台词必须按原文顺序排列")
                if original[source_cursor:beat_start].strip():
                    raise ValueError("剧本行动和台词遗漏或改动了原文内容")
                beat_end = beat_start + len(beat.text)
                beat_source_ranges[(scene.index, beat_index)] = (beat_start, beat_end)
                source_cursor = beat_end
            for reference in scene.characterReferences:
                ref_ids = set(reference.sourceSegmentIds)
                character = characters_by_name.get(reference.characterName)
                if character is None or not ref_ids or not ref_ids <= refs:
                    raise ValueError("实体代词关联必须引用当前场景中的已知实体和原文片段")
                has_valid_antecedent = False
                for beat_index, beat in enumerate(scene.beats):
                    beat_ids = set(beat.sourceSegmentIds)
                    if not ref_ids <= beat_ids or reference.quote not in beat.text:
                        continue
                    beat_start, beat_end = beat_source_ranges[(scene.index, beat_index)]
                    quote_offset = beat.text.find(reference.quote)
                    while quote_offset >= 0:
                        quote_start = beat_start + quote_offset
                        quote_end = quote_start + len(reference.quote)
                        quote_ids = [
                            item.id for item in self.sourceSegments
                            if source_ranges[item.id][0] < quote_end
                            and source_ranges[item.id][1] > quote_start
                        ]
                        if quote_end <= beat_end and quote_ids == reference.sourceSegmentIds:
                            pronoun_pattern = (
                                r"(?<![其吉])它(?:们)?"
                                if character.entityType == "organism"
                                else r"(?<![其吉])(?:他|她|祂)(?:们)?"
                            )
                            pronouns = [
                                match for match in re.finditer(
                                    pronoun_pattern, original
                                )
                                if quote_start <= match.start()
                                and match.end() <= quote_end
                            ]
                            for pronoun in pronouns:
                                prior_names = {
                                    item.name for item in self.characters
                                    if item.entityType == character.entityType
                                    and item.name in original[:pronoun.start()]
                                }
                                if prior_names == {reference.characterName}:
                                    has_valid_antecedent = True
                                    break
                        if has_valid_antecedent:
                            break
                        quote_offset = beat.text.find(reference.quote, quote_offset + 1)
                    if has_valid_antecedent:
                        break
                if not has_valid_antecedent:
                    raise ValueError("实体代词关联必须只有一个可确认的前置实体")
            if scene.locationName:
                location = locations_by_name.get(scene.locationName)
                if location is None or not self.entity_is_present_in_scene(location, scene):
                    raise ValueError("剧本场景地点必须关联同一原文范围内的场景实体")
        if original[source_cursor:].strip():
            raise ValueError("剧本行动和台词遗漏或改动了原文内容")
        for entity in [*self.characters, *self.locations]:
            if not set(entity.sourceSegmentIds) <= segment_ids:
                raise ValueError("角色或场景实体引用了无效原文片段")
            if [source_index[item] for item in entity.sourceSegmentIds] != sorted(source_index[item] for item in entity.sourceSegmentIds):
                raise ValueError("角色或场景实体来源必须按原文顺序排列")
            if not any(entity.name in item.text for item in self.sourceSegments if item.id in entity.sourceSegmentIds):
                raise ValueError("角色或场景名称必须出现在对应原文片段中")
        return self

    def entity_is_present_in_scene(
        self, entity: ProductionCharacter | ProductionLocation, scene: ProductionScene,
    ) -> bool:
        # Scenes can share a source segment. Use their actual quotes to establish presence.
        entity_ids = set(entity.sourceSegmentIds)
        if any(
            entity.name in beat.text and entity_ids.intersection(beat.sourceSegmentIds)
            for beat in scene.beats
        ):
            return True
        if not isinstance(entity, ProductionCharacter):
            return False

        return any(
            reference.characterName == entity.name
            for reference in scene.characterReferences
        )


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
    sourceBeatIndex: int = Field(ge=0)
    sourceBeatEndIndex: int | None = Field(default=None, ge=0)
    sourceSegmentIds: list[str] = Field(min_length=1)
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
    sourceBeatIndex: int | None = Field(default=None, ge=0)
    sourceBeatEndIndex: int | None = Field(default=None, ge=0)
    sourceSegmentIds: list[str] = Field(default_factory=list)
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
    projectType: ProjectType = "story"
    directorMode: DirectorMode = "legacy_outline"
    aspectRatio: Literal["9:16", "16:9"]
    style: str
    schemaVersion: int = 2
    assets: list[ProjectAsset] = Field(default_factory=list)
    directorStage: str = "complete"
    directorRequest: dict[str, Any] | None = None
    directorOutline: DirectorOutline | None = None
    productionScript: ProductionScript | None = None
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
        if value.get("assets") or not (value.get("productionScript") or value.get("directorOutline")):
            return value
        production = value.get("productionScript")
        source_preserving = value.get("directorMode", "legacy_outline") == "source_preserving" and production
        outline = production if source_preserving else value["directorOutline"]
        if isinstance(outline, ProductionScript):
            outline = outline.model_dump(mode="python")
        if isinstance(outline, DirectorOutline):
            outline = outline.model_dump(mode="python")
        project_id = value.get("projectId", "")
        assets = []
        entity_groups = (("location", outline.get("locations", [])),)
        if value.get("projectType", "story") == "science" and source_preserving:
            organisms = [entity for entity in outline.get("characters", []) if entity.get("entityType") == "organism"]
            entity_groups = (("character", organisms), *entity_groups)
        elif value.get("projectType", "story") != "science":
            entity_groups = (("character", outline.get("characters", [])), *entity_groups)
        for kind, entities in entity_groups:
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
    projectType: ProjectType = "story"
    aspectRatio: Literal["9:16", "16:9"] = "9:16"
    style: str = "cinematic animated short film"
    sceneCount: int = Field(default=3, ge=1, le=12)

    @model_validator(mode="after")
    def validate_story_not_blank(self) -> "CreateProjectRequest":
        if not self.story.strip():
            raise ValueError("故事或科普内容不能只包含空白字符")
        return self


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

