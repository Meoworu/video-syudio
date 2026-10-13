import { Alert, Button, Card, Descriptions, Empty, Space, Tag, Typography } from "antd";
import { fileUrl } from "../api";
import type { Project } from "../types";

export function FinalAssemblyPanel({ project, busy, onAssemble }: { project: Project; busy: boolean; onAssemble: () => Promise<Project | null> }) {
  const allVideosComplete = project.shots.length > 0 && project.shots.every((shot) => shot.video?.status === "complete");
  const hasAudio = Boolean(project.narration.audioPath);
  const ready = allVideosComplete && hasAudio;
  const finalDuration = project.editPlan.at(-1)?.timelineEnd;
  return <div className="assembly-stack">
    <Card className="section-card" title="成片合成" extra={<Tag color={ready ? "success" : "default"}>{ready ? "可以合成" : "等待素材"}</Tag>}>
      <Typography.Paragraph type="secondary">按剪辑时间线组合镜头，并将已选 MiniMax 旁白混入成片。</Typography.Paragraph>
      <Descriptions size="small" column={{ xs: 1, sm: 3 }} items={[
        { key: "clips", label: "镜头视频", children: `${project.shots.filter((shot) => shot.video?.status === "complete").length} / ${project.shots.length} 已完成` },
        { key: "audio", label: "旁白音轨", children: hasAudio ? "已就绪" : "尚未生成" },
        { key: "duration", label: "预计片长", children: finalDuration === undefined ? "—" : `${finalDuration.toFixed(1)} 秒` },
      ]} />
      {!ready && <Alert className="inline-alert" showIcon type="info" message="合成前还需准备素材" description={!allVideosComplete && !hasAudio ? "完成所有镜头视频，并生成一条旁白音轨。" : !allVideosComplete ? "完成所有镜头视频后即可合成。" : "生成旁白音频后即可合成。"} />}
      <Button type="primary" size="large" disabled={busy || !ready} loading={busy} onClick={() => void onAssemble()}>合成最终视频</Button>
    </Card>
    {project.finalVideoPath ? <Card className="section-card" title="最终成片" extra={<Tag color="success">已生成</Tag>}>
      <video className="final-video" controls preload="metadata" src={fileUrl(project.projectId, project.finalVideoPath)} />
    </Card> : <Empty className="assembly-empty" description="合成完成后，成片会显示在这里。" />}
    {project.shots.some((shot) => shot.video?.errorMessage) && <Card className="section-card" title="需要处理的问题">
      <Space direction="vertical" className="full-width">{project.shots.filter((shot) => shot.video?.errorMessage).map((shot) => <Alert key={shot.id} showIcon type="error" message={`镜头 ${shot.index + 1} · ${shot.title}`} description={shot.video?.errorMessage} />)}</Space>
    </Card>}
  </div>;
}
