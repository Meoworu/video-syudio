import { useEffect, useState } from "react";
import { Alert, App, Button, Card, Image, Input, Popconfirm, Select, Space, Tag, Typography, Upload } from "antd";
import { fileUrl } from "../api";
import type { FrameSlot, Project, ProjectAsset, Shot } from "../types";

type Role = "first" | "last";
type Config = { prompt: string; referenceMode: "auto" | "manual"; assetIds: string[] };

function normalizeName(value: string) {
  return value.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function resolveAssets(project: Project, shot: Shot, config: Config): ProjectAsset[] {
  if (config.referenceMode === "manual") return project.assets.filter((asset) => config.assetIds.includes(asset.id) && asset.image);
  const names = new Set([...shot.visibleCharacters, shot.locationName].filter(Boolean).map(normalizeName));
  return project.assets.filter((asset) => asset.image && (
    (asset.kind === "character" || asset.kind === "location") && names.has(normalizeName(asset.entityName || asset.name))
    || asset.kind === "reference" && asset.scopeShotIds.includes(shot.id)
  ));
}

function FrameCard({ project, shot, role, config, slot, busy, onConfig, onDraftChange, onGenerate, onSelectVersion, onDeleteFailed, onUpload }: {
  project: Project; shot: Shot; role: Role; config: Config; slot: FrameSlot; busy: boolean;
  onConfig: (role: Role, config: Config) => Promise<Project | null>;
  onDraftChange: (role: Role, config: Config) => void;
  onGenerate: (role: Role) => Promise<Project | null>;
  onSelectVersion: (role: Role, versionId: string) => Promise<Project | null>;
  onDeleteFailed: (role: Role) => Promise<Project | null>;
  onUpload: (role: Role, file: File) => Promise<Project | null>;
}) {
  const { message } = App.useApp();
  const title = role === "first" ? "首帧" : "尾帧";
  const frameDescription = role === "first" ? shot.firstFrameDescription : shot.lastFrameDescription;
  const slotJob = slot.job;
  const generating = slotJob?.status === "queued" || slotJob?.status === "generating";
  const current = slot.versions.find((version) => version.id === slot.selectedVersionId);
  const refs = resolveAssets(project, shot, config);
  const firstFrameChanged = role === "last" && current?.source === "generated" && current.firstFrameVersionId !== shot.frames.first.selectedVersionId;
  const stale = Boolean(current && (current.promptSnapshot !== config.prompt || firstFrameChanged || current.source === "generated" && JSON.stringify([...current.referenceSnapshots].sort()) !== JSON.stringify(refs.map((asset) => `${asset.id}:${asset.image?.imageId}`).sort())));

  async function copyPrompt() {
    try {
      await navigator.clipboard.writeText(config.prompt);
      message.success(`${title}提示词已复制`);
    } catch {
      message.error("复制失败，请检查浏览器剪贴板权限");
    }
  }

  return <Card size="small" className="frame-generation-card" title={title} extra={<Tag color={generating ? "processing" : slotJob?.status === "failed" ? "error" : current ? "success" : "default"}>{generating ? slotJob?.status === "queued" ? "排队中" : "生成中" : slotJob?.status === "failed" ? "生成失败" : current ? "已就绪" : "待生成"}</Tag>}>
    <div className="frame-reference-list">{refs.length ? refs.map((asset) => <Space key={asset.id} size={8}><img src={fileUrl(project.projectId, asset.image!.path)} alt="" /><Typography.Text>{asset.name}</Typography.Text></Space>) : <Typography.Text type="secondary">{config.referenceMode === "manual" ? "请选择参考资产" : "暂无匹配的参考资产"}</Typography.Text>}
      {config.referenceMode === "auto" && project.assets.filter((asset) => !asset.image && (asset.kind === "character" && shot.visibleCharacters.some((name) => normalizeName(name) === normalizeName(asset.entityName || asset.name)) || asset.kind === "location" && normalizeName(shot.locationName) === normalizeName(asset.entityName || asset.name))).map((asset) => <Tag color="warning" key={asset.id}>请上传：{asset.name}</Tag>)}
    </div>
    <Typography.Paragraph type="secondary">{frameDescription || "导演未提供画面描述"}</Typography.Paragraph>
    <label className="field-label">生成提示词<Input.TextArea value={config.prompt} maxLength={8000} rows={4} onChange={(event) => onDraftChange(role, { ...config, prompt: event.target.value })} /></label>
    <div className="frame-reference-config"><Select value={config.referenceMode} onChange={(referenceMode) => onDraftChange(role, { ...config, referenceMode, assetIds: referenceMode === "manual" ? config.assetIds : [] })} options={[{ value: "auto", label: "自动关联资产" }, { value: "manual", label: "手动选择资产" }]} />
      {config.referenceMode === "manual" && <Select mode="multiple" value={config.assetIds} onChange={(assetIds) => onDraftChange(role, { ...config, assetIds })} placeholder="选择参考图" options={project.assets.filter((asset) => asset.image).map((asset) => ({ value: asset.id, label: asset.name }))} />}
      <Button disabled={!config.prompt.trim()} onClick={() => void copyPrompt()}>复制提示词</Button>
      <Button disabled={busy || generating || !config.prompt.trim()} onClick={() => void onConfig(role, config)}>保存配置</Button>
      <Button disabled={busy || generating} onClick={() => onDraftChange(role, { ...config, prompt: role === "first" ? shot.directorFirstFramePrompt : shot.directorLastFramePrompt })}>恢复导演提示词</Button>
    </div>
    {current && <div className="frame-current-image"><Image src={fileUrl(project.projectId, current.path)} alt={`${title}预览`} /><Space direction="vertical"><Typography.Text strong>{current.source === "generated" ? "生成结果" : current.source === "legacy" ? "历史上传帧" : "手动上传"}</Typography.Text>{stale && <Tag color="warning">{firstFrameChanged ? "首帧已更换，建议重生成尾帧" : "提示词或参考资产已更新"}</Tag>}<Typography.Text type="secondary">{new Date(current.generatedAt).toLocaleString()}</Typography.Text></Space></div>}
    {slotJob?.status === "failed" && <Alert className="inline-alert" type="error" showIcon message="生成失败" description={slotJob.errorMessage || "请求未完成，请重试"} action={<Popconfirm title="删除失败记录？" okText="删除" cancelText="取消" onConfirm={() => onDeleteFailed(role)}><Button size="small" danger>删除记录</Button></Popconfirm>} />}
    <div className="frame-action-row"><Button type="primary" disabled={busy || generating || !config.prompt.trim()} loading={generating} onClick={async () => { if (await onConfig(role, config)) await onGenerate(role); }}>{current ? "重新生成" : "生成"}{title}</Button>
      <Upload accept="image/png,image/jpeg,image/webp" showUploadList={false} beforeUpload={(file) => { void onUpload(role, file); return false; }}><Button disabled={busy || generating}>手动上传{title}</Button></Upload>
      {slot.versions.length > 1 && <Select disabled={busy || generating} value={slot.selectedVersionId} onChange={(versionId) => void onSelectVersion(role, versionId)} options={slot.versions.map((version, index) => ({ value: version.id, label: `版本 ${slot.versions.length - index} · ${version.source === "generated" ? "生成" : "上传"}` }))} />}
    </div>
  </Card>;
}

export function FrameGenerationPanel({ project, shot, busy, onConfig, onGenerate, onGeneratePair, onSelectVersion, onDeleteFailed, onUpload }: {
  project: Project; shot: Shot; busy: boolean;
  onConfig: (role: Role, config: Config) => Promise<Project | null>;
  onGenerate: (role: Role) => Promise<Project | null>;
  onGeneratePair: () => Promise<Project | null>;
  onSelectVersion: (role: Role, versionId: string) => Promise<Project | null>;
  onDeleteFailed: (role: Role) => Promise<Project | null>;
  onUpload: (role: Role, file: File) => Promise<Project | null>;
}) {
  const { modal } = App.useApp();
  const [configs, setConfigs] = useState<Record<Role, Config>>({
    first: { prompt: shot.firstFramePrompt, referenceMode: shot.frames.first.referenceMode, assetIds: shot.frames.first.assetIds },
    last: { prompt: shot.lastFramePrompt, referenceMode: shot.frames.last.referenceMode, assetIds: shot.frames.last.assetIds },
  });
  useEffect(() => setConfigs({
    first: { prompt: shot.firstFramePrompt, referenceMode: shot.frames.first.referenceMode, assetIds: shot.frames.first.assetIds },
    last: { prompt: shot.lastFramePrompt, referenceMode: shot.frames.last.referenceMode, assetIds: shot.frames.last.assetIds },
  }), [project.projectId, shot.id]);

  function changeConfig(role: Role, config: Config) {
    setConfigs((current) => ({ ...current, [role]: config }));
  }

  async function generatePair() {
    for (const role of ["first", "last"] as const) {
      if (!await onConfig(role, configs[role])) return;
    }
    await onGeneratePair();
  }

  return <Card className="frame-generation-panel" title="首尾帧" extra={<Button type="primary" disabled={busy || Object.values(configs).some((config) => !config.prompt.trim())} onClick={() => modal.confirm({ title: "生成首帧和尾帧？", content: "将按顺序生成 2 张图片，成功后用于本镜头。", okText: "开始生成", cancelText: "取消", onOk: generatePair })}>一键生成首尾帧</Button>}>
    <div className="frame-generation-grid">{(["first", "last"] as const).map((role) => <FrameCard key={role} project={project} shot={shot} role={role} config={configs[role]} slot={shot.frames[role]} busy={busy} onConfig={onConfig} onDraftChange={changeConfig} onGenerate={onGenerate} onSelectVersion={onSelectVersion} onDeleteFailed={onDeleteFailed} onUpload={onUpload} />)}</div>
  </Card>;
}
