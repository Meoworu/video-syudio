import { useEffect, useRef, useState } from "react";
import { Alert, App, Button, Card, Empty, Input, InputNumber, List, Slider, Space, Tag, Typography } from "antd";
import { ApiError, fileUrl } from "../api";
import type { NarrationWindow, Project } from "../types";

export function NarrationPanel({ project, busy, onGenerate, onSave, onSynthesize, onSelectTake, onPlanWindows, onSaveWindows, onGenerateWindowAudio }: {
  project: Project; busy: boolean;
  onGenerate: () => Promise<Project | null>;
  onSave: (manuscript: string) => Promise<Project | null>;
  onSynthesize: (speed: number) => Promise<Project | null>;
  onSelectTake: (takeId: string) => Promise<Project | null>;
  onPlanWindows: () => Promise<Project | null>;
  onSaveWindows: (previewId: string, revision: number, windows: NarrationWindow[]) => Promise<Project>;
  onGenerateWindowAudio: (previewId: string, revision: number, speed: number, windowIds?: string[], forceRegenerate?: boolean) => Promise<Project | null>;
}) {
  const { message } = App.useApp();
  const [manuscript, setManuscript] = useState(project.narration.manuscript);
  const [speed, setSpeed] = useState(1);
  const [saving, setSaving] = useState(false);
  const [windowDraft, setWindowDraft] = useState<NarrationWindow[]>(project.narration.windows);
  const [savingWindows, setSavingWindows] = useState(false);
  const [windowConflict, setWindowConflict] = useState(false);
  const [windowSaveError, setWindowSaveError] = useState("");
  const narration = project.narration;
  const hasUnsavedChanges = manuscript !== narration.manuscript;
  const projectIdRef = useRef(project.projectId);
  const windowProjectIdRef = useRef(project.projectId);
  const windowBasePreviewIdRef = useRef(project.preview?.id ?? "");
  const windowBaseRevisionRef = useRef(project.narration.windowRevision);
  const windowDraftVersionRef = useRef(0);
  const draftVersionRef = useRef(0);
  const syncedDraftVersionRef = useRef(0);
  const windowDraftRef = useRef(JSON.stringify(project.narration.windows));
  const previewVideoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (projectIdRef.current !== project.projectId) {
      projectIdRef.current = project.projectId;
      draftVersionRef.current = 0;
      syncedDraftVersionRef.current = 0;
      setManuscript(narration.manuscript);
      return;
    }

    if (draftVersionRef.current === syncedDraftVersionRef.current) {
      setManuscript(narration.manuscript);
    }
  }, [project.projectId, narration.manuscript]);

  useEffect(() => {
    const incoming = JSON.stringify(project.narration.windows);
    const projectChanged = windowProjectIdRef.current !== project.projectId;
    if (projectChanged || JSON.stringify(windowDraft) === windowDraftRef.current) {
      windowProjectIdRef.current = project.projectId;
      windowDraftRef.current = incoming;
      windowBasePreviewIdRef.current = project.preview?.id ?? "";
      windowBaseRevisionRef.current = project.narration.windowRevision;
      windowDraftVersionRef.current = 0;
      setWindowConflict(false);
      setWindowDraft(project.narration.windows);
    }
  }, [project.projectId, project.preview?.id, project.narration.windowRevision, project.narration.windows, windowDraft]);

  function updateWindow(id: string, patch: Partial<NarrationWindow>) {
    windowDraftVersionRef.current += 1;
    setWindowDraft((items) => items.map((item) => item.id === id ? { ...item, ...patch, ...(patch.text !== undefined ? { textLocked: true } : {}) } : item));
  }

  function addWindow() {
    const preview = project.preview;
    if (!preview) return;
    const start = windowDraft.length ? Math.min(windowDraft.at(-1)!.endSeconds, Math.max(0, preview.durationSeconds - 1)) : 0;
    const end = Math.min(preview.durationSeconds, start + Math.min(5, preview.durationSeconds - start));
    const item: NarrationWindow = { id: crypto.randomUUID(), order: windowDraft.length, previewId: preview.id, startSeconds: start, endSeconds: end,
      sourceShotIds: [], visualSummary: "", anchorNote: "", evidenceFrameIds: [], text: "", textLocked: true, status: "draft" };
    windowDraftVersionRef.current += 1;
    setWindowDraft((items) => [...items, item]);
  }

  async function saveWindowDraft() {
    if (!project.preview) return;
    if (windowBasePreviewIdRef.current !== project.preview.id) {
      setWindowConflict(true);
      return;
    }
    const submittedVersion = windowDraftVersionRef.current;
    const submittedWindows = windowDraft.map((item, order) => ({ ...item, order }));
    setSavingWindows(true);
    setWindowSaveError("");
    try {
      const result = await onSaveWindows(windowBasePreviewIdRef.current, windowBaseRevisionRef.current, submittedWindows);
      windowDraftRef.current = JSON.stringify(result.narration.windows);
      windowBasePreviewIdRef.current = result.preview?.id ?? "";
      windowBaseRevisionRef.current = result.narration.windowRevision;
      setWindowConflict(false);
      setWindowSaveError("");
      if (windowDraftVersionRef.current === submittedVersion) setWindowDraft(result.narration.windows);
      message.success("时间窗已确认，接下来可以逐段配音");
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      if (error instanceof ApiError && error.status === 409 && /时间窗已被其他操作更新|剪辑预览已更新/.test(messageText)) {
        setWindowConflict(true);
        setWindowSaveError("");
      } else {
        setWindowConflict(false);
        setWindowSaveError(messageText);
      }
    } finally {
      setSavingWindows(false);
    }
  }

  function reloadServerWindows() {
    windowDraftRef.current = JSON.stringify(narration.windows);
    windowBasePreviewIdRef.current = project.preview?.id ?? "";
    windowBaseRevisionRef.current = narration.windowRevision;
    windowDraftVersionRef.current = 0;
    setWindowConflict(false);
    setWindowSaveError("");
    setWindowDraft(narration.windows);
  }

  function generateWindowAudio() {
    if (windowDraftDirty || busy || !project.preview || windowBasePreviewIdRef.current !== project.preview.id) return;
    void onGenerateWindowAudio(project.preview.id, narration.windowRevision, speed);
  }

  function regenerateWindowAudio(windowId: string) {
    if (!canGenerateWindowAudio || !project.preview) return;
    void onGenerateWindowAudio(project.preview.id, narration.windowRevision, speed, [windowId], true);
  }

  async function save() {
    const submittedManuscript = manuscript;
    const submittedVersion = draftVersionRef.current;
    setSaving(true);
    const result = await onSave(submittedManuscript);
    if (result) {
      syncedDraftVersionRef.current = submittedVersion;
      setManuscript((current) => draftVersionRef.current === submittedVersion ? result.narration.manuscript : current);
      message.success("旁白文稿已保存，时间线已重新对齐");
    }
    setSaving(false);
  }

  function synthesize() {
    if (busy || hasUnsavedChanges || !narration.manuscript.trim()) return;
    void onSynthesize(speed);
  }

  const cues = new Map(narration.alignment.map((cue) => [cue.sentenceId, cue]));
  const windowJob = [...project.mediaJobs].reverse().find((job) => job.kind === "windows" && ["queued", "running"].includes(job.status));
  const audioJob = [...project.mediaJobs].reverse().find((job) => job.kind === "audio" && ["queued", "running"].includes(job.status));
  const windowPreview = project.preview?.status === "ready" ? project.preview : null;
  const windowDraftDirty = Boolean(project.preview && JSON.stringify(windowDraft) !== JSON.stringify(narration.windows));
  const hasUnconfirmedWindows = narration.windows.some((item) => item.status === "draft");
  const canConfirmWindows = windowDraft.length > 0 && (windowDraftDirty || narration.mode !== "windowed" || hasUnconfirmedWindows);
  const canGenerateWindowAudio = !busy && !windowJob && !audioJob && !windowDraftDirty &&
    windowBasePreviewIdRef.current === project.preview?.id && narration.mode === "windowed" && narration.windows.length > 0 &&
    narration.windows.every((item) => ["ready", "complete", "needs_edit", "failed"].includes(item.status));
  return <div className="narration-stack">
    {windowPreview && <Card className="section-card windowed-narration-card" title="按画面时间窗安排旁白" extra={<Tag color={narration.mode === "windowed" ? "success" : "processing"}>{narration.mode === "windowed" ? "分段模式" : "待确认"}</Tag>}>
      <Typography.Paragraph type="secondary">先看无旁白预览，再按完整语义划分窗口。每段按实际时长校准，语音不会越窗或被截断。</Typography.Paragraph>
      <video ref={previewVideoRef} className="final-video" controls preload="metadata" src={fileUrl(project.projectId, narration.takes.find((take) => take.id === narration.selectedTakeId && take.previewId === windowPreview.id)?.auditionPath || windowPreview.path)} />
      <Space wrap className="narration-actions">
        <Button onClick={() => void onPlanWindows()} disabled={busy || Boolean(windowJob) || Boolean(audioJob) || windowDraftDirty} loading={Boolean(windowJob)}>根据真实画面生成建议</Button>
        <Button onClick={addWindow} disabled={busy || Boolean(windowJob) || Boolean(audioJob)}>手动添加时间窗</Button>
        <Button type="primary" onClick={() => void saveWindowDraft()} disabled={busy || Boolean(windowJob) || Boolean(audioJob) || !canConfirmWindows} loading={savingWindows}>确认并保存时间窗</Button>
        <div className="speed-control"><Typography.Text>基础语速</Typography.Text><Slider min={0.8} max={1.2} step={0.05} value={speed} onChange={setSpeed} tooltip={{ formatter: (value) => `${Number(value).toFixed(2)}x` }} /><Typography.Text>{speed.toFixed(2)}x</Typography.Text></div>
        <Button type="primary" disabled={!canGenerateWindowAudio} loading={Boolean(audioJob)} onClick={generateWindowAudio}>生成 / 重新生成分段配音</Button>
      </Space>
      {windowDraftDirty && <Alert className="inline-alert" showIcon type="warning" message="时间窗有未保存修改，请先确认并保存，再生成配音或重新分析画面。" />}
      {windowConflict && <Alert className="inline-alert" showIcon type="warning" message="服务端时间窗版本已变化，当前草稿没有覆盖服务端内容。请复制需要保留的修改后加载最新版本，再合并并保存。" action={<Button size="small" onClick={reloadServerWindows}>加载服务端版本</Button>} />}
      {windowSaveError && <Alert className="inline-alert" showIcon type="error" message="时间窗保存失败，草稿仍保留。" description={windowSaveError} />}
      {windowJob?.status === "running" && <Alert className="inline-alert" showIcon type="info" message="正在分析实际画面，完成后会显示可编辑的建议时间窗。" />}
      {audioJob && <Alert className="inline-alert" showIcon type="info" message={`分段配音处理中：${audioJob.progress.completed ?? 0} / ${audioJob.progress.total ?? narration.windows.length} 段完成。`} />}
      {project.mediaJobs.filter((job) => ["windows", "audio"].includes(job.kind) && job.status === "failed").at(-1)?.errorMessage && <Alert className="inline-alert" showIcon type="error" message={project.mediaJobs.filter((job) => ["windows", "audio"].includes(job.kind) && job.status === "failed").at(-1)?.errorMessage} description="画面分析失败时，可手动添加并编辑时间窗后保存。" />}
      {windowDraft.map((item) => <Card key={item.id} size="small" className="window-editor-card" title={`旁白窗口 ${item.order + 1}`} extra={<Space><Tag color={item.status === "needs_edit" ? "error" : item.status === "complete" ? "success" : "default"}>{item.status === "needs_edit" ? "需要调整" : item.status === "complete" ? "已配音" : item.status === "stale" ? "预览已过期" : "草稿"}</Tag><Button size="small" onClick={() => regenerateWindowAudio(item.id)} disabled={!canGenerateWindowAudio || !item.text.trim()}>重新生成此段</Button><Button size="small" danger onClick={() => { windowDraftVersionRef.current += 1; setWindowDraft((items) => items.filter((window) => window.id !== item.id).map((window, order) => ({ ...window, order }))); }}>删除</Button></Space>}>
        <div className="window-time-fields"><label className="field-label">开始秒数<InputNumber min={0} max={windowPreview.durationSeconds} step={0.1} value={item.startSeconds} onChange={(value) => updateWindow(item.id, { startSeconds: Number(value ?? 0) })} /></label><label className="field-label">结束秒数<InputNumber min={0} max={windowPreview.durationSeconds} step={0.1} value={item.endSeconds} onChange={(value) => updateWindow(item.id, { endSeconds: Number(value ?? 0) })} /></label><Typography.Text type="secondary">窗口 {item.endSeconds - item.startSeconds > 0 ? `${(item.endSeconds - item.startSeconds).toFixed(1)} 秒` : "时长无效"} · 实测配音 {item.estimatedDurationSeconds?.toFixed(2) ?? "待生成"} 秒</Typography.Text></div>
        <label className="field-label">对应画面摘要<Input value={item.visualSummary} onChange={(event) => updateWindow(item.id, { visualSummary: event.target.value })} placeholder="例如：毛毛虫伪装在蛛网上的微距画面" /></label>
        <label className="field-label">关键动作锚点<Input value={item.anchorNote} onChange={(event) => updateWindow(item.id, { anchorNote: event.target.value })} placeholder="例如：主体伪装特写出现时讲到伪装方式" /></label>
        <label className="field-label">旁白文案<Input.TextArea rows={3} value={item.text} onChange={(event) => updateWindow(item.id, { text: event.target.value })} placeholder="按完整语义写一段旁白，可以跨多个镜头" /></label>
        {item.evidenceFrameIds.length > 0 && <div className="window-evidence-frames">{item.evidenceFrameIds.map((frameId) => {
          const frame = project.preview?.evidenceFrames.find((evidence) => evidence.id === frameId);
          return frame ? <button key={frame.id} className="window-evidence-frame" type="button" onClick={() => { if (previewVideoRef.current) previewVideoRef.current.currentTime = frame.timeSeconds; }}>
            <img src={fileUrl(project.projectId, frame.relativePath)} alt={`${frame.timeSeconds.toFixed(1)} 秒画面`} /><span>{frame.timeSeconds.toFixed(1)} 秒 · 跳转预览</span>
          </button> : null;
        })}<Typography.Text type="secondary">对应镜头 {item.sourceShotIds.flatMap((id) => { const shot = project.shots.find((candidate) => candidate.id === id); return shot ? [shot.index + 1] : []; }).join("、")}</Typography.Text></div>}
      </Card>)}
      {narration.audioPath && narration.mode === "windowed" && <audio className="audio-player" controls preload="metadata" src={fileUrl(project.projectId, narration.audioPath)} />}
    </Card>}
    {narration.mode !== "windowed" && <Card className="section-card" title="连续旁白（旧版）" extra={narration.status && <Tag color={narration.status === "failed" ? "error" : narration.audioPath ? "success" : "processing"}>{narration.status === "failed" ? "生成失败" : narration.audioPath ? "音频已就绪" : narration.manuscript ? "文稿已就绪" : "待生成"}</Tag>}>
      <Typography.Paragraph type="secondary">旁白按完整句子对齐剪辑时间线，可修改文稿后重新生成音频。</Typography.Paragraph>
      <Space wrap className="narration-actions">
        <Button onClick={() => void onGenerate()} disabled={busy || project.status !== "ready"} loading={busy}>生成 / 重写文稿</Button>
        <div className="speed-control"><Typography.Text>语速</Typography.Text><Slider min={0.8} max={1.2} step={0.05} value={speed} onChange={setSpeed} tooltip={{ formatter: (value) => `${Number(value).toFixed(2)}x` }} /><Typography.Text>{speed.toFixed(2)}x</Typography.Text></div>
        <Button type="primary" onClick={synthesize} disabled={busy || hasUnsavedChanges || !narration.manuscript.trim()} loading={busy}>生成 MiniMax 音频</Button>
      </Space>
      {hasUnsavedChanges && <Alert className="inline-alert" showIcon type="info" message="文稿有未保存修改，请先保存并重新对齐，再生成音频。" />}
      {narration.timingWarning && <Alert className="inline-alert" showIcon type="warning" message="旁白时长提示" description={narration.timingWarning} />}
      {narration.manuscript ? <>
        <div className="narration-metrics">
          <div><Typography.Text type="secondary">时间线目标</Typography.Text><Typography.Title level={5}>{narration.targetDurationSeconds?.toFixed(1) ?? "—"}<small> 秒</small></Typography.Title></div>
          <div><Typography.Text type="secondary">文稿估算</Typography.Text><Typography.Title level={5}>{narration.estimatedDurationSeconds?.toFixed(1) ?? "—"}<small> 秒</small></Typography.Title></div>
          <div><Typography.Text type="secondary">实际音频</Typography.Text><Typography.Title level={5}>{narration.audioDurationSeconds?.toFixed(1) ?? "—"}<small> 秒</small></Typography.Title></div>
        </div>
        <label className="field-label">旁白文稿<Input.TextArea rows={8} value={manuscript} onChange={(event) => { draftVersionRef.current += 1; setManuscript(event.target.value); }} /></label>
        <Button className="save-manuscript" onClick={() => void save()} disabled={busy || !manuscript.trim() || !hasUnsavedChanges} loading={saving}>保存并重新对齐</Button>
        {(narration.voiceStyle || narration.voiceDirection) && <Typography.Paragraph className="voice-direction"><Typography.Text strong>声音设定</Typography.Text><br />{narration.voiceStyle}<br /><Typography.Text type="secondary">{narration.voiceDirection}</Typography.Text></Typography.Paragraph>}
        <div className="cue-section"><Typography.Title level={5}>句子与镜头对齐</Typography.Title>
          {narration.sentences.length ? <List size="small" dataSource={narration.sentences} renderItem={(sentence) => {
            const cue = cues.get(sentence.id);
            return <List.Item key={sentence.id}>
              <div className="cue-row"><Tag color={cue ? "processing" : "default"}>{cue ? `${cue.startSeconds.toFixed(1)}–${cue.endSeconds.toFixed(1)} 秒` : "未对齐"}</Tag>
                {cue && <Typography.Text type="secondary">镜头 {cue.startShotIndex + 1}{cue.endShotIndex !== cue.startShotIndex ? ` → ${cue.endShotIndex + 1}` : ""}</Typography.Text>}
                <Typography.Text className="cue-copy">{sentence.text}</Typography.Text>
              </div>
            </List.Item>;
          }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="生成文稿后显示句子时间线" />}
        </div>
      </> : <Empty description="还没有旁白文稿" />}
    </Card>}

    <Card className="section-card" title="语音版本" extra={narration.takes.length ? `${narration.takes.length} 个版本` : undefined}>
      {narration.takes.length ? <List dataSource={narration.takes} renderItem={(take) => <List.Item key={take.id} actions={[
        <Button key="select" type={take.id === narration.selectedTakeId ? "primary" : "default"} disabled={busy || take.status === "stale" || (narration.mode === "windowed" && (take.mode !== "windowed" || take.previewId !== project.preview?.id || take.windowRevision !== narration.windowRevision))} onClick={() => void onSelectTake(take.id)}>{take.status === "stale" ? "版本过期" : take.id === narration.selectedTakeId ? "当前版本" : "使用此版本"}</Button>,
      ]}>
        <List.Item.Meta title={`语速 ${take.speed.toFixed(2)}x`} description={`${take.durationSeconds.toFixed(1)} 秒 · ${take.status === "failed" ? "生成失败" : take.status === "stale" ? "画面时间线已变更" : "MiniMax Speech"}`} />
      </List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="生成音频后，可在这里管理不同语速版本" />}
      {narration.audioPath && <audio className="audio-player" controls preload="metadata" src={fileUrl(project.projectId, narration.audioPath)} />}
    </Card>
  </div>;
}
