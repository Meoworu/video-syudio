import { useCallback, useEffect, useRef, useState } from "react";
import {
  assembleProject, cancelVideo, createAsset, createProject, deleteAsset, deleteFailedFrameJob, deleteFailedVideo, deleteProject, generateAllVideos,
  generateAssetImage, generateFrame, generateFrames, generateManuscript, generateNarrationAudio, generateVideo, getProject, listProjects, listVideoJobs,
  ApiError, retryDirector, selectFrameVersion, selectNarrationTake, updateAsset, updateFrameConfig, updateNarrationManuscript, updateShot, uploadAssetImage, uploadFrame,
  cancelMediaJob, createSilentPreview, generateWindowNarrationAudio, planNarrationWindows, saveNarrationWindows,
} from "../api";
import type { NarrationWindow, Project, Shot } from "../types";

export type CreateProjectInput = { story: string; projectType: "story" | "science"; aspectRatio: "9:16" | "16:9"; style: string; sceneCount: number };

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
      const [projectsResult, jobsResult, projectResult] = await Promise.allSettled([
        listProjects(), listVideoJobs(), projectId ? getProject(projectId) : Promise.resolve(null),
      ]);
      if (dataVersion !== dataVersionRef.current) return;

      if (projectsResult.status === "fulfilled") setProjects(projectsResult.value);
      if (jobsResult.status === "fulfilled") setVideoJobs(jobsResult.value);

      if (selectionVersion === selectionVersionRef.current && projectId === selectedIdRef.current) {
        if (projectResult.status === "fulfilled") {
          setSelected(projectResult.value);
        } else if (projectResult.reason instanceof ApiError && projectResult.reason.status === 404) {
          selectionVersionRef.current += 1;
          selectedIdRef.current = undefined;
          setSelectedId(undefined);
          setSelected(null);
          setLoadingProject(false);
          setError("");
        } else {
          setError(projectResult.reason instanceof Error ? projectResult.reason.message : String(projectResult.reason));
        }
      }

      const listError = projectsResult.status === "rejected" ? projectsResult.reason : jobsResult.status === "rejected" ? jobsResult.reason : null;
      if (listError) setError(listError instanceof Error ? listError.message : String(listError));
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
  const removeProject = useCallback(async (projectId: string) => {
    if (pendingActionsRef.current) return false;
    // Invalidate reads that started before the deletion request. If deletion fails,
    // reload the current selection below so an ignored read cannot leave it stale.
    dataVersionRef.current += 1;
    pendingActionsRef.current += 1;
    setBusy(true);
    setError("");
    try {
      await deleteProject(projectId);
    } catch (cause) {
      if (!(cause instanceof ApiError) || cause.status !== 404) {
        const currentProjectId = selectedIdRef.current;
        const selectionVersion = selectionVersionRef.current;
        const dataVersion = dataVersionRef.current;
        if (currentProjectId) {
          try {
            const currentProject = await getProject(currentProjectId);
            if (selectionVersion === selectionVersionRef.current && dataVersion === dataVersionRef.current && currentProjectId === selectedIdRef.current) {
              setSelected(currentProject);
              setLoadingProject(false);
            }
          } catch (reloadCause) {
            if (reloadCause instanceof ApiError && reloadCause.status === 404
              && selectionVersion === selectionVersionRef.current
              && dataVersion === dataVersionRef.current
              && currentProjectId === selectedIdRef.current) {
              selectionVersionRef.current += 1;
              selectedIdRef.current = undefined;
              setSelectedId(undefined);
              setSelected(null);
              setLoadingProject(false);
              setProjects((items) => items.filter((item) => item.projectId !== currentProjectId));
              setVideoJobs((items) => items.filter((item) => item.projectId !== currentProjectId));
            }
          }
        }
        setError(cause instanceof Error ? cause.message : String(cause));
        return false;
      }
    } finally {
      pendingActionsRef.current -= 1;
      setBusy(pendingActionsRef.current > 0);
    }
    dataVersionRef.current += 1;
    setProjects((items) => items.filter((item) => item.projectId !== projectId));
    setVideoJobs((items) => items.filter((item) => item.projectId !== projectId));
    if (selectedIdRef.current === projectId) {
      selectionVersionRef.current += 1;
      selectedIdRef.current = undefined;
      setSelectedId(undefined);
      setSelected(null);
      setLoadingProject(false);
    } else if (selectedIdRef.current) {
      const currentProjectId = selectedIdRef.current;
      const selectionVersion = selectionVersionRef.current;
      const dataVersion = dataVersionRef.current;
      void getProject(currentProjectId).then((project) => {
        if (selectionVersion === selectionVersionRef.current && dataVersion === dataVersionRef.current && currentProjectId === selectedIdRef.current) {
          setSelected(project);
        }
      }).catch((cause) => {
        if (selectionVersion === selectionVersionRef.current && dataVersion === dataVersionRef.current) {
          if (cause instanceof ApiError && cause.status === 404 && currentProjectId === selectedIdRef.current) {
            selectionVersionRef.current += 1;
            selectedIdRef.current = undefined;
            setSelectedId(undefined);
            setSelected(null);
            setLoadingProject(false);
            setProjects((items) => items.filter((item) => item.projectId !== currentProjectId));
            setVideoJobs((items) => items.filter((item) => item.projectId !== currentProjectId));
            setError("");
          } else {
            setError(cause instanceof Error ? cause.message : String(cause));
          }
        }
      });
    }
    return true;
  }, []);
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
    deleteFailedVideo: (projectId: string, shotId: string) => run(() => deleteFailedVideo(projectId, shotId)),
    createAsset: (projectId: string, payload: { name: string; description?: string; scopeShotIds: string[] }) => run(() => createAsset(projectId, payload)),
    updateAsset: (projectId: string, assetId: string, payload: { name: string; description?: string; scopeShotIds: string[] }) => run(() => updateAsset(projectId, assetId, payload)),
    uploadAssetImage: (projectId: string, assetId: string, file: File) => run(() => uploadAssetImage(projectId, assetId, file)),
    generateAssetImage: (projectId: string, assetId: string) => run(() => generateAssetImage(projectId, assetId, crypto.randomUUID())),
    deleteAsset: (projectId: string, assetId: string) => run(() => deleteAsset(projectId, assetId)),
    updateFrameConfig: (projectId: string, shotId: string, role: "first" | "last", payload: { prompt: string; referenceMode: "auto" | "manual"; assetIds: string[]; restoreDefaultPrompt?: boolean }) => run(() => updateFrameConfig(projectId, shotId, role, payload)),
    generateFrame: (projectId: string, shotId: string, role: "first" | "last") => run(() => generateFrame(projectId, shotId, role, crypto.randomUUID())),
    generateFrames: (projectId: string, shotId: string) => run(() => generateFrames(projectId, shotId, crypto.randomUUID())),
    selectFrameVersion: (projectId: string, shotId: string, role: "first" | "last", versionId: string) => run(() => selectFrameVersion(projectId, shotId, role, versionId)),
    deleteFailedFrameJob: (projectId: string, shotId: string, role: "first" | "last") => run(() => deleteFailedFrameJob(projectId, shotId, role)),
    generateAllVideos: (projectId: string) => run(() => generateAllVideos(projectId)),
    assembleProject: (projectId: string) => run(() => assembleProject(projectId)),
    createSilentPreview: (projectId: string) => run(() => createSilentPreview(projectId)),
    planNarrationWindows: (projectId: string) => run(() => planNarrationWindows(projectId)),
    saveNarrationWindows: async (projectId: string, previewId: string, expectedRevision: number, windows: NarrationWindow[]) => {
      const selectionVersion = selectionVersionRef.current;
      pendingActionsRef.current += 1;
      setBusy(true);
      setError("");
      try {
        const project = await saveNarrationWindows(projectId, previewId, expectedRevision, windows);
        dataVersionRef.current += 1;
        if (selectionVersion === selectionVersionRef.current && projectId === selectedIdRef.current) setSelected(project);
        await refresh();
        return project;
      } catch (cause) {
        if (selectionVersion === selectionVersionRef.current) setError(cause instanceof Error ? cause.message : String(cause));
        throw cause;
      } finally {
        pendingActionsRef.current -= 1;
        setBusy(pendingActionsRef.current > 0);
      }
    },
    generateWindowNarrationAudio: (projectId: string, previewId: string, expectedRevision: number, speed: number,
      windowIds?: string[], forceRegenerate = false) => run(() => generateWindowNarrationAudio(
        projectId, previewId, expectedRevision, speed, windowIds, forceRegenerate,
      )),
    cancelMediaJob: (projectId: string, jobId: string) => run(() => cancelMediaJob(projectId, jobId)),
  };

  return { projects, selected, selectedId, videoJobs, busy, error, setError, loadingProjects, loadingProject, refresh, selectProject, create, removeProject, run, actions };
}
