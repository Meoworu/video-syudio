import { Alert, Button, Card, Collapse, Descriptions, Empty, Space, Tag, Typography } from "antd";
import type { Project } from "../types";

function ProjectState({ project }: { project: Project }) {
  if (project.status === "generating") {
    const stages: Record<string, string> = { outline: "正在构思故事大纲", shot_design: "正在设计场景与镜头" };
    return <Alert showIcon type="info" message="导演正在规划项目" description={stages[project.directorStage] || "完成后页面会自动更新。"} />;
  }
  if (project.status === "failed") return <Alert showIcon type="error" message="导演规划失败" description={project.errorMessage || "请检查配置后重试。"} />;
  return <Tag color="success">分镜已就绪</Tag>;
}

function EditTimeline({ project }: { project: Project }) {
  if (!project.editPlan.length) return null;
  const finalEnd = project.editPlan.at(-1)?.timelineEnd || 0;
  return <Card className="section-card" title="剪辑时间线" extra={<Typography.Text type="secondary">总时长 {finalEnd.toFixed(1)} 秒</Typography.Text>}>
    <div className="timeline-scroll">
      <div className="timeline-track" role="img" aria-label="镜头剪辑时间线">
        {project.editPlan.map((clip) => {
          const shot = project.shots.find((item) => item.index === clip.shotIndex);
          const overlap = clip.transitionIn === "dissolve" ? 0.5 : 0;
          const duration = Math.max(0.2, clip.timelineEnd - clip.timelineStart - overlap);
          return <div className="timeline-clip" key={clip.shotIndex} style={{ flex: `${duration} 1 0%` }} title={clip.transitionReason}>
            <span>镜头 {clip.shotIndex + 1}</span><small>{shot?.title || "未命名"}</small><small>{duration.toFixed(1)} 秒</small>
          </div>;
        })}
      </div>
      {project.narration.alignment.length > 0 && <div className="timeline-track narration-track" role="img" aria-label="旁白句子时间线">
        {project.narration.alignment.map((cue) => {
          const sentence = project.narration.sentences.find((item) => item.id === cue.sentenceId);
          const duration = Math.max(0.2, cue.endSeconds - cue.startSeconds);
          return <div className="timeline-cue" key={cue.sentenceId} style={{ flex: `${duration} 1 0%` }} title={sentence?.text}>
            <span>{cue.sentenceId}</span><small>镜头 {cue.startShotIndex + 1}{cue.endShotIndex !== cue.startShotIndex ? `–${cue.endShotIndex + 1}` : ""}</small>
          </div>;
        })}
      </div>}
    </div>
    <div className="timeline-axis"><span>{project.editPlan[0].timelineStart.toFixed(1)} 秒</span><span>{finalEnd.toFixed(1)} 秒</span></div>
  </Card>;
}

export function ProjectOverview({ project, busy, onRetry }: { project: Project; busy: boolean; onRetry: () => void }) {
  const outline = project.directorOutline;
  const outlineItems = outline ? [
    { key: "characters", label: `角色 · ${outline.characters.length}`, children: outline.characters.length ? <div className="detail-grid">{outline.characters.map((character) => <Card size="small" key={character.name}><Typography.Text strong>{character.name}</Typography.Text><Typography.Paragraph>{character.description}</Typography.Paragraph><Typography.Text type="secondary">外观：{character.visualIdentity}</Typography.Text></Card>)}</div> : <Empty description="暂无角色信息" /> },
    { key: "locations", label: `场景资产 · ${outline.locations.length}`, children: outline.locations.length ? <div className="detail-grid">{outline.locations.map((location) => <Card size="small" key={location.name}><Typography.Text strong>{location.name}</Typography.Text><Typography.Paragraph>{location.description}</Typography.Paragraph><Typography.Text type="secondary">视觉锚点：{location.visualIdentity}</Typography.Text></Card>)}</div> : <Empty description="暂无场景资产" /> },
    { key: "scenes", label: `场景推进 · ${outline.scenes.length}`, children: <div className="scene-list">{outline.scenes.map((scene) => <div className="scene-row" key={scene.index}><Tag>{String(scene.index + 1).padStart(2, "0")}</Tag><div><Typography.Text strong>{scene.title}</Typography.Text><Typography.Paragraph type="secondary">{scene.locationName}{scene.timeOfDay ? ` · ${scene.timeOfDay}` : ""}</Typography.Paragraph><Typography.Text>{scene.dramaticGoal} → {scene.conflict} → {scene.turningPoint} → {scene.outcome}</Typography.Text></div></div>)}</div> },
    { key: "style", label: "风格圣经", children: <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={Object.entries(outline.styleBible).map(([key, value]) => ({ key, label: key, children: value }))} /> },
  ] : [];

  return <div className="overview-stack">
    <Card className="hero-card">
      <div className="project-hero-top"><div><Typography.Text className="eyebrow">项目概览</Typography.Text><Typography.Title level={2}>{project.title}</Typography.Title></div><ProjectState project={project} /></div>
      <Typography.Paragraph className="project-story">{project.story}</Typography.Paragraph>
      <Descriptions size="small" column={{ xs: 1, sm: 3 }} items={[
        { key: "aspect", label: "画面比例", children: project.aspectRatio },
        { key: "shots", label: "镜头数", children: `${project.shots.length} 个` },
        { key: "style", label: "视觉风格", children: project.style },
      ]} />
      {project.status === "failed" && <Button className="retry-button" onClick={onRetry} loading={busy}>重试导演规划</Button>}
    </Card>

    {outline && <Card className="section-card" title="导演大纲" extra={<Tag color="processing">{outline.scenes.length} 个场景</Tag>}>
      <Typography.Title level={4}>{outline.logline}</Typography.Title>
      <Typography.Paragraph>{outline.synopsis}</Typography.Paragraph>
      {outline.theme && <Typography.Paragraph><Typography.Text strong>主题：</Typography.Text>{outline.theme}</Typography.Paragraph>}
      <Collapse ghost items={outlineItems} />
    </Card>}
    {!outline && project.status !== "generating" && project.status !== "failed" && <Empty className="overview-empty" description="项目大纲尚未生成" />}
    <EditTimeline project={project} />
    <Card className="section-card" title="制作进度">
      <Space wrap size={[8, 8]}>
        <Tag color={project.directorOutline ? "success" : project.status === "failed" ? "error" : "processing"}>导演规划{project.directorOutline ? "完成" : project.status === "failed" ? "失败" : "处理中"}</Tag>
        <Tag color={project.shots.length && project.shots.every((shot) => shot.uploads.firstFrame && shot.uploads.lastFrame) ? "success" : "default"}>首尾帧素材</Tag>
        <Tag color={project.shots.length && project.shots.every((shot) => shot.video?.status === "complete") ? "success" : "default"}>镜头视频</Tag>
        <Tag color={project.narration.audioPath ? "success" : "default"}>连续旁白</Tag>
        <Tag color={project.finalVideoPath ? "success" : "default"}>最终成片</Tag>
      </Space>
    </Card>
  </div>;
}
