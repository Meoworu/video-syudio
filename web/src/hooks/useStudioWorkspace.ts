import { useCallback, useEffect, useRef, useState } from "react";
import {
  assembleProject, cancelVideo, createProject, generateAllVideos, generateManuscript,
  generateNarrationAudio, generateVideo, getProject, listProjects, listVideoJobs,
  retryDirector, selectNarrationTake, updateNarrationManuscript, updateShot, uploadFrame,
} from "../api";
import type { Project, Shot } from "../types";

export type CreateProjectInput = { story: string; aspectRatio: "9:16" | "16:9"; style: string; sceneCount: number };

export function useStudioWorkspace() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);
  const [selectedId, setSelectedId] = useState<string>();
  const [videoJobs, setVideoJobs] = useState<Awaited<ReturnType<typeof listVideoJobs>>>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingProject, setLoadingProject] = useState(false);
  const selectedIdRef = useRef<string | undefined>(undefined);
  const selectionVersionRef = useRef(0);
  const dataVersionRef = useRef(0);
  const pendingActionsRef = useRef(0);
  const refreshingRef = useRef(false);

  const refresh = useCallback(async (projectId = selectedIdRef.current) => {
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    const selectionVersion = selectionVersionRef.current;
    const dataVersion = dataVersionRef.current;
    try {
      const [nextProjects, nextJobs, nextProject] = await Promise.all([
        listProjects(), listVideoJobs(), projectId ? getProject(projectId) : Promise.resolve(null),
      ]);
      if (dataVersion === dataVersionRef.current) {
        setProjects(nextProjects);
        setVideoJobs(nextJobs);
        if (selectionVersion === selectionVersionRef.current && projectId === selectedIdRef.current) setSelected(nextProject);
      }
    } catch (cause) {
      if (selectionVersion === selectionVersionRef.current && dataVersion === dataVersionRef.current) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    } finally {
      refreshingRef.current = false;
      setLoadingProjects(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const timer = window.setInterval(() => { void refresh(); }, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const selectProject = useCallback(async (projectId: string) => {
    const selectionVersion = ++selectionVersionRef.current;
    const dataVersion = dataVersionRef.current;
    if (projectId !== selectedIdRef.current) setSelected(null);
    selectedIdRef.current = projectId;
    setSelectedId(projectId);
    setLoadingProject(true);
    setError("");
    try {
      const project = await getProject(projectId);
      if (selectionVersion !== selectionVersionRef.current || dataVersion !== dataVersionRef.current) return;
      dataVersionRef.current += 1;
      setSelected(project);
      await refresh(projectId);
    } catch (cause) {
      if (selectionVersion === selectionVersionRef.current && dataVersion === dataVersionRef.current) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    } finally {
      if (selectionVersion === selectionVersionRef.current) setLoadingProject(false);
    }
  }, [refresh]);

  const run = useCallback(async (action: () => Promise<Project>, selectResult = false) => {
    const selectionVersion = selectionVersionRef.current;
    pendingActionsRef.current += 1;
    setBusy(true);
    setError("");
    try {
      const project = await action();
      dataVersionRef.current += 1;
      if (selectionVersion === selectionVersionRef.current && (selectResult || project.projectId === selectedIdRef.current)) {
        if (selectResult) {
          selectionVersionRef.current += 1;
          selectedIdRef.current = project.projectId;
          setSelectedId(project.projectId);
          setLoadingProject(false);
        }
        setSelected(project);
      }
      await refresh();
      return project;
    } catch (cause) {
      if (selectionVersion === selectionVersionRef.current) setError(cause instanceof Error ? cause.message : String(cause));
      return null;
    } finally {
      pendingActionsRef.current -= 1;
      setBusy(pendingActionsRef.current > 0);
    }
  }, [refresh]);

  const create = useCallback((payload: CreateProjectInput) => run(() => createProject(payload), true), [run]);
  const actions = {
    retryDirector: (projectId: string) => run(() => retryDirector(projectId)),
    generateManuscript: (projectId: string) => run(() => generateManuscript(projectId)),
    generateNarrationAudio: (projectId: string, speed: number) => run(() => generateNarrationAudio(projectId, speed)),
    updateNarrationManuscript: (projectId: string, manuscript: string) => run(() => updateNarrationManuscript(projectId, manuscript)),
    selectNarrationTake: (projectId: string, takeId: string) => run(() => selectNarrationTake(projectId, takeId)),
    updateShot: (projectId: string, shotId: string, draft: Pick<Shot, "title" | "prompt" | "durationSeconds" | "transitionIn">) => run(() => updateShot(projectId, shotId, draft)),
    uploadFrame: async (projectId: string, shotId: string, role: "first" | "last", file: File) => run(async () => {
      await uploadFrame(projectId, shotId, role, file);
      return getProject(projectId);
    }),
    generateVideo: (projectId: string, shotId: string) => run(() => generateVideo(projectId, shotId)),
    cancelVideo: (projectId: string, shotId: string) => run(() => cancelVideo(projectId, shotId)),
    generateAllVideos: (projectId: string) => run(() => generateAllVideos(projectId)),
    assembleProject: (projectId: string) => run(() => assembleProject(projectId)),
  };

  return { projects, selected, selectedId, videoJobs, busy, error, setError, loadingProjects, loadingProject, refresh, selectProject, create, run, actions };
}
