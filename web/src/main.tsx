import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { createProject, generateManuscript, generateNarrationAudio, generateVideo, getProject, listProjects, uploadFrame } from "./api";
import type { Project } from "./types";

import "./styles.css";

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);
  const [story, setStory] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh(projectId?: string) {
    const next = projectId ? await getProject(projectId) : null;
    setProjects(await listProjects());
    if (next) setSelected(next);
  }

  useEffect(() => { void refresh(); }, []);

  async function create() {
    if (!story.trim()) return;
    setBusy(true);
    try {
      const project = await createProject({ story, aspectRatio: "9:16", style: "cinematic animated short film", sceneCount: 3 });
      setStory("");
      await refresh(project.projectId);
    } catch (error) { setMessage(String(error)); } finally { setBusy(false); }
  }

  async function run(action: () => Promise<Project>) {
    setBusy(true);
    try { const project = await action(); setSelected(project); await refresh(project.projectId); }
    catch (error) { setMessage(String(error)); }
    finally { setBusy(false); }
  }

  return <main className="shell">
    <header><h1>video-studio</h1><span>Google Vertex AI 视频 · MiniMax 连续旁白</span></header>
    <section className="layout">
      <aside className="panel"><h2>项目</h2><textarea value={story} onChange={(event) => setStory(event.target.value)} placeholder="输入故事" /><button disabled={busy || !story.trim()} onClick={() => void create()}>创建项目</button>
        {projects.map((project) => <button className="project" key={project.projectId} onClick={() => void refresh(project.projectId)}>{project.title}</button>)}
      </aside>
      <section className="panel content">{message && <p className="error">{message}</p>}{!selected ? <p>请选择或创建项目。</p> : <>
        <h2>{selected.title}</h2><p>{selected.story}</p>
        <div className="actions"><button disabled={busy} onClick={() => void run(() => generateManuscript(selected.projectId))}>生成连续旁白文案</button><button disabled={busy || selected.narration.status !== "draft"} onClick={() => void run(() => generateNarrationAudio(selected.projectId))}>用 MiniMax 生成旁白</button></div>
        {selected.narration.manuscript && <article className="manuscript">{selected.narration.manuscript}</article>}
        {selected.shots.map((shot) => <article className="shot" key={shot.id}><h3>{shot.index + 1}. {shot.title}</h3><p>{shot.prompt}</p><div className="uploads"><label>首帧<input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void run(async () => { await uploadFrame(selected.projectId, shot.id, "first", file); return getProject(selected.projectId); }); }} /></label><label>尾帧<input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) void run(async () => { await uploadFrame(selected.projectId, shot.id, "last", file); return getProject(selected.projectId); }); }} /></label></div><button disabled={busy || !shot.uploads.firstFrame || !shot.uploads.lastFrame} onClick={() => void run(() => generateVideo(selected.projectId, shot.id))}>生成 Google 视频</button><span className="status">{shot.video?.status || "待生成"}</span></article>)}
      </>}</section>
    </section>
  </main>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

