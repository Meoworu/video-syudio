import { useEffect, useRef, useState } from "react";
import { Alert, App, Button, Card, Empty, Input, List, Slider, Space, Tag, Typography } from "antd";
import { fileUrl } from "../api";
import type { Project } from "../types";

export function NarrationPanel({ project, busy, onGenerate, onSave, onSynthesize, onSelectTake }: {
  project: Project; busy: boolean;
  onGenerate: () => Promise<Project | null>;
  onSave: (manuscript: string) => Promise<Project | null>;
  onSynthesize: (speed: number) => Promise<Project | null>;
  onSelectTake: (takeId: string) => Promise<Project | null>;
}) {
  const { message } = App.useApp();
  const [manuscript, setManuscript] = useState(project.narration.manuscript);
  const [speed, setSpeed] = useState(1);
  const [saving, setSaving] = useState(false);
  const narration = project.narration;
  const hasUnsavedChanges = manuscript !== narration.manuscript;
  const projectIdRef = useRef(project.projectId);
  const draftVersionRef = useRef(0);
  const syncedDraftVersionRef = useRef(0);

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
  return <div className="narration-stack">
    <Card className="section-card" title="连续旁白" extra={narration.status && <Tag color={narration.status === "failed" ? "error" : narration.audioPath ? "success" : "processing"}>{narration.status === "failed" ? "生成失败" : narration.audioPath ? "音频已就绪" : narration.manuscript ? "文稿已就绪" : "待生成"}</Tag>}>
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
    </Card>

    <Card className="section-card" title="语音版本" extra={narration.takes.length ? `${narration.takes.length} 个版本` : undefined}>
      {narration.takes.length ? <List dataSource={narration.takes} renderItem={(take) => <List.Item key={take.id} actions={[
        <Button key="select" type={take.id === narration.selectedTakeId ? "primary" : "default"} disabled={busy} onClick={() => void onSelectTake(take.id)}>{take.id === narration.selectedTakeId ? "当前版本" : "使用此版本"}</Button>,
      ]}>
        <List.Item.Meta title={`语速 ${take.speed.toFixed(2)}x`} description={`${take.durationSeconds.toFixed(1)} 秒 · ${take.status === "failed" ? "生成失败" : "MiniMax Speech"}`} />
      </List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="生成音频后，可在这里管理不同语速版本" />}
      {narration.audioPath && <audio className="audio-player" controls preload="metadata" src={fileUrl(project.projectId, narration.audioPath)} />}
    </Card>
  </div>;
}
