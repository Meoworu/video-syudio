import { Alert, Button, Card, Descriptions, Empty, Progress, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { fileUrl } from "../api";
import type { Project } from "../types";

export function FinalAssemblyPanel({ project, busy, onAssemble, onCreatePreview, onPlanWindows, onCancelJob }: {
  project: Project; busy: boolean; onAssemble: () => Promise<Project | null>;
  onCreatePreview: () => Promise<Project | null>; onPlanWindows: () => Promise<Project | null>;
  onCancelJob: (jobId: string) => Promise<Project | null>;
}) {
  const [canceling, setCanceling] = useState(false);
  const allVideosComplete = project.shots.length > 0 && project.shots.every((shot) => shot.video?.status === "complete");
  const hasAudio = Boolean(project.narration.audioPath);
  const ready = allVideosComplete && hasAudio;
  const preview = project.preview;
  const activeJob = [...project.mediaJobs].reverse().find((job) => ["preview", "windows", "audio", "export"].includes(job.kind) && ["queued", "running"].includes(job.status));
  const finalDuration = preview?.status === "ready" ? preview.durationSeconds : project.editPlan.at(-1)?.timelineEnd;
  const displayedFinalPath = project.finalVideoPath || project.finalRender?.path;
  const selectedTake = project.narration.takes.find((take) => take.id === project.narration.selectedTakeId);
  return <div className="assembly-stack">
    <Card className="section-card" title="剪辑预览与成片" extra={<Tag color={preview?.status === "ready" ? "success" : "default"}>{preview?.status === "ready" ? "预览有效" : preview?.status === "stale" ? "预览过期" : "尚无预览"}</Tag>}>
      <Typography.Paragraph type="secondary">先按镜头实际视频生成无旁白预览，再依据真实画面安排旁白时间窗、分段配音并导出。</Typography.Paragraph>
      <Descriptions size="small" column={{ xs: 1, sm: 3 }} items={[
        { key: "clips", label: "镜头视频", children: `${project.shots.filter((shot) => shot.video?.status === "complete").length} / ${project.shots.length} 已完成` },
        { key: "audio", label: "旁白音轨", children: project.narration.mode === "windowed" ? `${project.narration.windows.length} 个时间窗 · ${hasAudio ? "已就绪" : "待配音"}` : hasAudio ? "整段旁白已就绪" : "尚未生成" },
        { key: "duration", label: "预计片长", children: finalDuration === undefined ? "—" : `${finalDuration.toFixed(1)} 秒` },
      ]} />
      {!allVideosComplete && <Alert className="inline-alert" showIcon type="info" message="先完成所有镜头视频" />}
      {preview?.status !== "ready" && <Button type="primary" size="large" disabled={busy || !allVideosComplete || Boolean(activeJob)} loading={activeJob?.kind === "preview"} onClick={() => void onCreatePreview()}>{preview?.status === "stale" ? "重新生成剪辑预览" : "生成无旁白剪辑预览"}</Button>}
      {preview?.status === "ready" && <>
        <Button disabled={busy || Boolean(activeJob)} loading={activeJob?.kind === "windows"} onClick={() => void onPlanWindows()}>根据画面规划旁白时间窗</Button>
        {project.narration.mode === "windowed" && project.narration.windows.length > 0 && <Typography.Text type="secondary">时间窗已确认后，在“连续旁白”中生成分段配音。</Typography.Text>}
      </>}
      {activeJob && <Space className="inline-alert" align="center"><Progress style={{ minWidth: 260 }} status={activeJob.status === "running" ? "active" : "normal"} percent={activeJob.progress.total ? Math.round(100 * (activeJob.progress.completed ?? 0) / activeJob.progress.total) : undefined} format={() => `${activeJob.kind === "preview" ? "剪辑预览" : activeJob.kind === "windows" ? "画面分析" : activeJob.kind === "audio" ? "分段配音" : "成片封装"} · ${activeJob.progress.cancelRequested ? "正在停止" : activeJob.status === "running" ? "处理中" : "排队中"}`} />
        <Button danger size="small" loading={canceling} disabled={Boolean(activeJob.progress.cancelRequested)} onClick={async () => { setCanceling(true); await onCancelJob(activeJob.id); setCanceling(false); }}>{activeJob.progress.cancelRequested ? "正在停止" : "取消任务"}</Button>
      </Space>}
      {project.mediaJobs.some((job) => job.status === "failed" && job.errorMessage) && <Alert className="inline-alert" showIcon type="error" message={project.mediaJobs.filter((job) => job.status === "failed").at(-1)?.errorMessage} />}
      {preview?.status === "ready" && <video className="final-video" controls preload="metadata" src={fileUrl(project.projectId, selectedTake?.previewId === preview.id && selectedTake.auditionPath ? selectedTake.auditionPath : preview.path)} />}
      {preview?.status !== "ready" && <Alert className="inline-alert" showIcon type="info" message="完成镜头视频后可先生成无旁白预览，再规划和编辑旁白时间窗。" />}
      {project.narration.mode === "legacy" && <Button type="primary" size="large" disabled={busy || !ready} loading={activeJob?.kind === "export"} onClick={() => void onAssemble()}>合成最终视频</Button>}
      {project.narration.mode === "windowed" && <Button type="primary" size="large" disabled={busy || !ready || !preview || preview.status !== "ready"} loading={activeJob?.kind === "export"} onClick={() => void onAssemble()}>导出时间窗配音成片</Button>}
    </Card>
    {displayedFinalPath ? <Card className="section-card" title="最终成片" extra={<Tag color={project.finalRender?.isCurrent === false ? "default" : "success"}>{project.finalRender?.isCurrent === false ? "历史版本" : "已生成"}</Tag>}>
      <video className="final-video" controls preload="metadata" src={fileUrl(project.projectId, displayedFinalPath)} />
    </Card> : <Empty className="assembly-empty" description="合成完成后，成片会显示在这里。" />}
    {project.shots.some((shot) => shot.video?.errorMessage) && <Card className="section-card" title="需要处理的问题">
      <Space direction="vertical" className="full-width">{project.shots.filter((shot) => shot.video?.errorMessage).map((shot) => <Alert key={shot.id} showIcon type="error" message={`镜头 ${shot.index + 1} · ${shot.title}`} description={shot.video?.errorMessage} />)}</Space>
    </Card>}
  </div>;
}
