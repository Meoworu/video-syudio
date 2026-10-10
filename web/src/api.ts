import type { Project } from "./types";

const base = "/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export function listProjects() {
  return request<Project[]>("/projects");
}

export function createProject(payload: { story: string; aspectRatio: string; style: string; sceneCount: number }) {
  return request<Project>("/projects", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

export function getProject(projectId: string) {
  return request<Project>(`/projects/${projectId}`);
}

export function uploadFrame(projectId: string, shotId: string, role: "first" | "last", file: File) {
  return request<{ path: string }>(`/projects/${projectId}/shots/${shotId}/frames/${role}`, { method: "POST", headers: { "Content-Type": file.type || "image/png" }, body: file });
}

export function generateVideo(projectId: string, shotId: string) {
  return request<Project>(`/projects/${projectId}/shots/${shotId}/generate-video`, { method: "POST" });
}

export function generateManuscript(projectId: string) {
  return request<Project>(`/projects/${projectId}/narration/manuscript`, { method: "POST" });
}

export function generateNarrationAudio(projectId: string) {
  return request<Project>(`/projects/${projectId}/narration/audio`, { method: "POST" });
}

