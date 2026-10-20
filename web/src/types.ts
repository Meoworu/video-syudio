export type Shot = {
  id: string;
  index: number;
  title: string;
  prompt: string;
  durationSeconds: number;
  sceneIndex: number;
  beat: string;
  narrativePurpose: string;
  camera: string;
  visualDescription: string;
  mustAppear: string[];
  forbiddenElements: string[];
  continuityNotes: string;
  visibleCharacters: string[];
  locationName: string;
  firstFrameDescription: string;
  lastFrameDescription: string;
  firstFramePrompt: string;
  lastFramePrompt: string;
  directorFirstFramePrompt: string;
  directorLastFramePrompt: string;
  motionBeats: { startSeconds: number; endSeconds: number; subjectAction: string; cameraAction: string; environmentAction: string }[];
  transitionIn: "hard_cut" | "dissolve" | "match_cut";
  transitionReason: string;
  uploads: { firstFrame?: string | null; lastFrame?: string | null };
  frames: Record<"first" | "last", FrameSlot>;
  video?: { model: string; status: string; remoteJobId?: string | null; path?: string | null; errorMessage?: string | null } | null;
};

export type ProjectAsset = {
  id: string; kind: "character" | "location" | "reference"; name: string; description: string;
  entityName?: string | null; scopeShotIds: string[];
  image?: { imageId: string; path: string; mimeType: string; size: number; width: number; height: number } | null;
  revision: number;
};

export type FrameSlot = {
  referenceMode: "auto" | "manual"; assetIds: string[]; selectedVersionId?: string | null;
  versions: { id: string; path: string; source: "generated" | "upload" | "legacy"; generatedAt: string; model: string; promptSnapshot: string; referenceSnapshots: string[]; firstFrameVersionId?: string | null }[];
  job?: { id: string; requestId: string; groupId?: string | null; status: "queued" | "generating" | "complete" | "failed"; errorMessage?: string | null } | null;
};

export type DirectorOutline = {
  title: string; logline: string; synopsis: string; theme: string;
  characters: { name: string; description: string; visualIdentity: string }[];
  locations: { name: string; description: string; visualIdentity: string }[];
  scenes: { index: number; title: string; dramaticGoal: string; conflict: string; turningPoint: string; outcome: string; locationName: string; timeOfDay: string }[];
  styleBible: Record<string, string>;
};

export type Project = {
  projectId: string;
  title: string;
  story: string;
  aspectRatio: "9:16" | "16:9";
  style: string;
  schemaVersion: number;
  assets: ProjectAsset[];
  status: string;
  directorStage: string;
  errorMessage?: string | null;
  directorOutline?: DirectorOutline | null;
  editPlan: { shotIndex: number; timelineStart: number; timelineEnd: number; sourceIn: number; sourceOut: number; transitionIn: string; transitionReason: string }[];
  finalVideoPath?: string | null;
  shots: Shot[];
  narration: {
    manuscript: string; voiceStyle: string; voiceDirection: string;
    sentences: { id: string; order: number; text: string; narrativeFunction: string; sourceShotIndexes: number[]; emotion: string; delivery: string; paceClass: string; pauseAfterSeconds: number; estimatedDurationSeconds?: number | null }[];
    alignment: { sentenceId: string; startSeconds: number; endSeconds: number; startShotIndex: number; endShotIndex: number; crossesShotBoundary: boolean }[];
    targetDurationSeconds?: number | null; estimatedDurationSeconds?: number | null;
    audioPath?: string | null; audioDurationSeconds?: number | null;
    timingWarning?: string | null;
    takes: { id: string; path: string; durationSeconds: number; speed: number; status: string }[];
    selectedTakeId?: string | null; status: string;
  };
};

