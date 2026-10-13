import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Collapse, Empty, Input, InputNumber, Select, Space, Tag, Typography, Upload } from "antd";
import { fileUrl } from "../api";
import type { Project, Shot } from "../types";

type ShotDraft = Pick<Shot, "title" | "prompt" | "durationSeconds" | "transitionIn">;
const activeStatuses = new Set(["submitting", "generating", "downloading"]);
const statusLabels: Record<string, [string, string]> = {
  idle: ["待生成", "default"], submitting: ["提交中", "processing"], generating: ["生成中", "processing"],
  downloading: ["下载中", "processing"], complete: ["已完成", "success"], failed: ["失败", "error"], cancelled: ["已取消", "default"],
};

function ShotEditor({ project, shot, busy, onUpdate, onUpload, onGenerate, onCancel }: {
  project: Project; shot: Shot; busy: boolean;
  onUpdate: (shotId: string, draft: ShotDraft) => Promise<Project | null>;
  onUpload: (shotId: string, role: "first" | "last", file: File) => Promise<Project | null>;
  onGenerate: (shotId: string) => Promise<Project | null>;
  onCancel: (shotId: string) => Promise<Project | null>;
}) {
  const { message, modal } = App.useApp();
  const [draft, setDraft] = useState<ShotDraft>(() => ({ title: shot.title, prompt: shot.prompt, durationSeconds: shot.durationSeconds, transitionIn: shot.transitionIn }));
  const active = activeStatuses.has(shot.video?.status || "");
  const [statusLabel, statusColor] = statusLabels[shot.video?.status || "idle"] || [shot.video?.status || "待生成", "default"];

  useEffect(() => {
    setDraft({ title: shot.title, prompt: shot.prompt, durationSeconds: shot.durationSeconds, transitionIn: shot.transitionIn });
  }, [project.projectId, shot.id]);

  async function save() {
    const submit = async () => {
      const result = await onUpdate(shot.id, draft);
      if (result) message.success(`镜头 ${shot.index + 1} 已保存`);
    };
    if (shot.video || project.finalVideoPath) {
      modal.confirm({
        title: "保存修改并重新生成素材？",
        content: "修改镜头会清除该镜头已有视频和当前成片，完成后需要重新生成并合成。",
        okText: "继续保存", cancelText: "返回检查", onOk: submit,
      });
    } else await submit();
  }

  async function upload(role: "first" | "last", file: File) {
    const allowed = ["image/png", "image/jpeg", "image/webp"];
    if (!allowed.includes(file.type)) {
      message.error("请选择 PNG、JPG 或 WebP 图片");
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      message.error("图片不能超过 20 MB");
      return;
    }
    const submit = async () => {
      const result = await onUpload(shot.id, role, file);
      if (result) message.success(`${role === "first" ? "首帧" : "尾帧"}已上传`);
    };
    if (shot.video || project.finalVideoPath) {
      modal.confirm({
        title: `替换${role === "first" ? "首帧" : "尾帧"}素材？`,
        content: "替换素材会清除该镜头已有视频和当前成片，完成后需要重新生成并合成。",
        okText: "继续上传", cancelText: "返回检查", onOk: submit,
      });
    } else await submit();
  }

  function generate() {
    const submit = () => onGenerate(shot.id);
    if (shot.video?.status === "complete" || project.finalVideoPath) {
      modal.confirm({
        title: "重新生成这个镜头？",
        content: "重新生成会清除当前成片，完成后需要重新合成。",
        okText: "重新生成", cancelText: "取消", onOk: submit,
      });
    } else void submit();
  }

  const details = [
    { key: "purpose", label: "叙事作用", children: shot.narrativePurpose || shot.beat || "—" },
    { key: "camera", label: "摄影说明", children: shot.camera || "—" },
    { key: "visual", label: "画面描述", children: shot.visualDescription || "—" },
    { key: "continuity", label: "连续性", children: shot.continuityNotes || "—" },
    { key: "first-description", label: "首帧画面", children: shot.firstFrameDescription || "—" },
    { key: "first", label: "首帧提示词", children: <Typography.Paragraph className="preserve-copy">{shot.firstFramePrompt || "—"}</Typography.Paragraph> },
    { key: "last-description", label: "尾帧画面", children: shot.lastFrameDescription || "—" },
    { key: "last", label: "尾帧提示词", children: <Typography.Paragraph className="preserve-copy">{shot.lastFramePrompt || "—"}</Typography.Paragraph> },
    { key: "motion", label: "动作节拍", children: shot.motionBeats.length ? <div className="motion-list">{shot.motionBeats.map((beat, index) => <Typography.Paragraph key={index}><Typography.Text strong>{beat.startSeconds}–{beat.endSeconds}s</Typography.Text>　{beat.subjectAction}{beat.cameraAction ? ` · 机位：${beat.cameraAction}` : ""}{beat.environmentAction ? ` · 环境：${beat.environmentAction}` : ""}</Typography.Paragraph>)}</div> : "—" },
    { key: "avoid", label: "必须出现 / 避免", children: <Space wrap>{shot.mustAppear.map((item) => <Tag color="success" key={`must-${item}`}>{item}</Tag>)}{shot.forbiddenElements.map((item) => <Tag color="error" key={`avoid-${item}`}>{item}</Tag>)}{!shot.mustAppear.length && !shot.forbiddenElements.length && "—"}</Space> },
    { key: "transition", label: "入场转场", children: `${shot.transitionIn} · ${shot.transitionReason || "未提供说明"}` },
  ];

  return <Card className="shot-card" title={<Space><span className="shot-index">{String(shot.index + 1).padStart(2, "0")}</span><span>{shot.title}</span></Space>} extra={<Space><Typography.Text type="secondary">{shot.durationSeconds} 秒</Typography.Text><Tag color={statusColor}>{statusLabel}</Tag></Space>}>
    {shot.video?.errorMessage && <Alert className="inline-alert" showIcon type="error" message={shot.video.errorMessage} />}
    <Typography.Paragraph type="secondary">{shot.locationName}{shot.locationName && shot.visibleCharacters.length ? " · " : ""}{shot.visibleCharacters.join("、")}</Typography.Paragraph>
    <Collapse ghost items={[{ key: "direction", label: "查看导演设计", children: <div className="shot-direction">{details.map((item) => <div key={item.key}><Typography.Text type="secondary">{item.label}</Typography.Text><div>{item.children}</div></div>)}</div> }]} />

    <div className="shot-edit-grid">
      <div className="shot-fields">
        <label className="field-label">镜头标题<Input maxLength={120} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
        <label className="field-label">Google 视频提示词<Input.TextArea rows={4} maxLength={8000} showCount value={draft.prompt} onChange={(event) => setDraft({ ...draft, prompt: event.target.value })} /></label>
        <Space wrap>
          <label className="field-label compact-field">时长<InputNumber min={3} max={10} precision={0} addonAfter="秒" value={draft.durationSeconds} onChange={(value) => value && setDraft({ ...draft, durationSeconds: value })} /></label>
          <label className="field-label compact-field">入场转场<Select value={draft.transitionIn} onChange={(transitionIn) => setDraft({ ...draft, transitionIn })} options={[
            { value: "hard_cut", label: "硬切" }, { value: "dissolve", label: "叠化" }, { value: "match_cut", label: "匹配剪辑" },
          ]} /></label>
        </Space>
        <Space wrap>
          <Button disabled={busy || active || !draft.title.trim() || !draft.prompt.trim()} onClick={() => void save()}>保存修改</Button>
          <Button type="primary" disabled={busy || active || !shot.uploads.firstFrame || !shot.uploads.lastFrame} loading={busy} onClick={generate}>生成视频</Button>
          {active && <Button danger disabled={busy} onClick={() => void onCancel(shot.id)}>取消任务</Button>}
        </Space>
      </div>
      <div className="frame-pair">
        {(["first", "last"] as const).map((role) => {
          const path = role === "first" ? shot.uploads.firstFrame : shot.uploads.lastFrame;
          const label = role === "first" ? "首帧" : "尾帧";
          return <div className="frame-slot" key={role}>
          <div className="frame-preview">{path ? <img src={fileUrl(project.projectId, path)} alt={`${shot.title}${label}预览`} /> : <Typography.Text type="secondary">上传{label}素材</Typography.Text>}</div>
            <Upload accept="image/png,image/jpeg,image/webp" maxCount={1} showUploadList={false} beforeUpload={(file) => { void upload(role, file); return false; }}>
              <Button block disabled={busy || active}>{path ? `替换${label}` : `上传${label}`}</Button>
            </Upload>
          </div>;
        })}
      </div>
    </div>
    {shot.video?.path && <video className="shot-video" controls preload="metadata" src={fileUrl(project.projectId, shot.video.path)} />}
  </Card>;
}

export function ShotWorkspace({ project, busy, onUpdate, onUpload, onGenerate, onCancel, onGenerateAll }: {
  project: Project; busy: boolean;
  onUpdate: (shotId: string, draft: ShotDraft) => Promise<Project | null>;
  onUpload: (shotId: string, role: "first" | "last", file: File) => Promise<Project | null>;
  onGenerate: (shotId: string) => Promise<Project | null>;
  onCancel: (shotId: string) => Promise<Project | null>;
  onGenerateAll: () => Promise<Project | null>;
}) {
  if (!project.shots.length) return <Empty description="导演正在整理镜头，完成后会显示在这里。" />;
  const readyCount = project.shots.filter((shot) => shot.uploads.firstFrame && shot.uploads.lastFrame && shot.video?.status !== "complete" && !activeStatuses.has(shot.video?.status || "")).length;
  return <div className="shot-workspace">
    <div className="section-heading"><div><Typography.Title level={4}>分镜</Typography.Title><Typography.Text type="secondary">{project.shots.length} 个镜头 · {readyCount} 个可提交生成</Typography.Text></div>
      <Button type="primary" disabled={busy || readyCount === 0} loading={busy} onClick={() => void onGenerateAll()}>批量生成可提交镜头</Button>
    </div>
    {project.shots.map((shot) => <ShotEditor key={`${project.projectId}-${shot.id}`} project={project} shot={shot} busy={busy} onUpdate={onUpdate} onUpload={onUpload} onGenerate={onGenerate} onCancel={onCancel} />)}
  </div>;
}
