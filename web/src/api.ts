import type { NarrationWindow, Project } from "./types";

const base = "/v1";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export function fileUrl(projectId: string, path: string) {
  return `${base}/projects/${encodeURIComponent(projectId)}/files/${path.split("/").map(encodeURIComponent).join("/")}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  if (!response.ok) {
    const body = await response.text();
    let message = body || response.statusText;
    try {
      const parsed = JSON.parse(body) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
      else if (Array.isArray(parsed.detail)) message = parsed.detail.map((item) => typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)).join("；");
    } catch {
      // Keep plain-text error responses as-is.
    }
    throw new ApiError(message || `请求失败（${response.status}）`, response.status);
  }
  return response.json() as Promise<T>;
}

export function listProjects() {
  return request<Project[]>("/projects");
}

export function deleteProject(projectId: string) {
  return request<{ projectId: string; deleted: boolean }>(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
}

export function createProject(payload: { story: string; projectType: "story" | "science"; aspectRatio: string; style: string; sceneCount: number }) {
  return request<Project>("/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function getProject(projectId: string) {
  return request<Project>(`/projects/${projectId}`);
}

export function uploadFrame(projectId: string, shotId: string, role: "first" | "last", file: File) {
  return request<{ path: string }>(`/projects/${projectId}/shots/${shotId}/frames/${role}`, { method: "POST", headers: { "Content-Type": file.type || "image/png" }, body: file });
}

export function createAsset(projectId: string, payload: { name: string; description?: string; scopeShotIds: string[] }) {
  return request<Project>(`/projects/${projectId}/assets`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function updateAsset(projectId: string, assetId: string, payload: { name: string; description?: string; scopeShotIds: string[] }) {
  return request<Project>(`/projects/${projectId}/assets/${assetId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function uploadAssetImage(projectId: string, assetId: string, file: File) {
  return request<Project>(`/projects/${projectId}/assets/${assetId}/image`, { method: "POST", headers: { "Content-Type": file.type }, body: file });
}

export function generateAssetImage(projectId: string, assetId: string, requestId: string) {
  return request<Project>(`/projects/${projectId}/assets/${assetId}/generate-image`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requestId }) });
}

export function deleteAsset(projectId: string, assetId: string) {
  return request<Project>(`/projects/${projectId}/assets/${assetId}`, { method: "DELETE" });
}

export function updateFrameConfig(projectId: string, shotId: string, role: "first" | "last", payload: { prompt: string; referenceMode: "auto" | "manual"; assetIds: string[]; restoreDefaultPrompt?: boolean }) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/frames/${role}/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function generateFrame(projectId: string, shotId: string, role: "first" | "last", requestId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/frames/${role}/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requestId }) });
}

export function generateFrames(projectId: string, shotId: string, requestId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/generate-frames`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requestId }) });
}

export function selectFrameVersion(projectId: string, shotId: string, role: "first" | "last", versionId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/frames/${role}/versions/${versionId}/select`, { method: "POST" });
}

export function deleteFailedFrameJob(projectId: string, shotId: string, role: "first" | "last") {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/frames/${role}/failed-job`, { method: "DELETE" });
}

export function generateVideo(projectId: string, shotId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/generate-video`, { method: "POST" });
}

export function generateManuscript(projectId: string) {
  return request<Project>(`/projects/${projectId}/narration/manuscript`, { method: "POST" });
}

export function generateNarrationAudio(projectId: string, speed = 1) {
  return request<Project>(`/projects/${projectId}/narration/audio?speed=${speed}`, { method: "POST" });
}

export function updateNarrationManuscript(projectId: string, manuscript: string) {
  return request<Project>(`/projects/${projectId}/narration/manuscript`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ manuscript }) });
}

export function assembleProject(projectId: string) {
  return request<Project>(`/projects/${projectId}/assemble`, { method: "POST" });
}

export function createSilentPreview(projectId: string, requestId = crypto.randomUUID()) {
  return request<Project>(`/projects/${projectId}/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requestId }) });
}

export function planNarrationWindows(projectId: string, requestId = crypto.randomUUID()) {
  return request<Project>(`/projects/${projectId}/narration/windows/plan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ requestId }) });
}

export function saveNarrationWindows(projectId: string, previewId: string, expectedRevision: number, windows: NarrationWindow[]) {
  return request<Project>(`/projects/${projectId}/narration/windows`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ previewId, expectedRevision, windows }) });
}

export function generateWindowNarrationAudio(projectId: string, previewId: string, expectedRevision: number, speed = 1,
  windowIds?: string[], forceRegenerate = false, requestId = crypto.randomUUID()) {
  return request<Project>(`/projects/${projectId}/narration/window-audio`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ previewId, expectedRevision, speed, windowIds, forceRegenerate, requestId }) });
}

export function cancelMediaJob(projectId: string, jobId: string) {
  return request<Project>(`/projects/${projectId}/media-jobs/${jobId}/cancel`, { method: "POST" });
}

export function updateShot(projectId: string, shotId: string, payload: { title?: string; prompt?: string; durationSeconds?: number; transitionIn?: string }) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function generateAllVideos(projectId: string) {
  return request<Project>(`/projects/${projectId}/generate-videos`, { method: "POST" });
}

export function cancelVideo(projectId: string, shotId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/cancel-video`, { method: "POST" });
}

export function deleteFailedVideo(projectId: string, shotId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/video`, { method: "DELETE" });
}

export function selectNarrationTake(projectId: string, takeId: string) {
  return request<Project>(`/projects/${projectId}/narration/takes/${takeId}/select`, { method: "POST" });
}

export function listVideoJobs() {
  return request<{ projectId: string; projectTitle: string; shotId: string; shotTitle: string; status: string; path?: string | null; errorMessage?: string | null }[]>("/projects/videos/jobs");
}

export function retryDirector(projectId: string) {
  return request<Project>(`/projects/${projectId}/director/retry`, { method: "POST" });
}

