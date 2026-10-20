import { useState } from "react";
import { Alert, App, Button, Card, Empty, Form, Input, Modal, Popconfirm, Select, Space, Tag, Typography, Upload } from "antd";
import { fileUrl } from "../api";
import type { Project, ProjectAsset } from "../types";

type AssetPayload = { name: string; description?: string; scopeShotIds: string[] };

export function AssetWorkspace({ project, busy, onCreate, onUpdate, onUpload, onDelete }: {
  project: Project; busy: boolean;
  onCreate: (payload: AssetPayload) => Promise<Project | null>;
  onUpdate: (assetId: string, payload: AssetPayload) => Promise<Project | null>;
  onUpload: (assetId: string, file: File) => Promise<Project | null>;
  onDelete: (assetId: string) => Promise<Project | null>;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm<AssetPayload>();
  const [editing, setEditing] = useState<ProjectAsset | null>(null);
  const entities = project.assets.filter((asset) => asset.kind !== "reference");
  const references = project.assets.filter((asset) => asset.kind === "reference");

  function upload(asset: ProjectAsset, file: File) {
    if (!/[.](png|jpe?g|webp)$/i.test(file.name) || !["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      message.error("请选择 PNG、JPG 或 WebP 图片");
    } else if (file.size > 6_000_000) {
      message.error("图片不能超过 6 MB");
    } else void onUpload(asset.id, file);
    return false;
  }

  async function submit(values: AssetPayload) {
    const payload = { ...values, name: values.name.trim(), description: values.description?.trim() };
    const result = editing?.id ? await onUpdate(editing.id, payload) : await onCreate(payload);
    if (result) {
      setEditing(null);
      form.resetFields();
    }
  }

  const entityCard = (asset: ProjectAsset) => <Card className="asset-card" key={asset.id}>
    <div className="asset-card-heading"><div><Typography.Text strong>{asset.name}</Typography.Text><Tag>{asset.kind === "character" ? "角色" : "场景"}</Tag></div>
      <Typography.Paragraph type="secondary">{asset.description || "导演规划中的视觉参考"}</Typography.Paragraph>
    </div>
    <div className="asset-image-preview">{asset.image ? <img src={fileUrl(project.projectId, asset.image.path)} alt={`${asset.name}参考图`} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未上传参考图" />}</div>
    <div className="asset-related"><Typography.Text type="secondary">自动关联 {project.shots.filter((shot) => asset.kind === "character" ? shot.visibleCharacters.includes(asset.entityName || asset.name) : shot.locationName === (asset.entityName || asset.name)).length} 个镜头</Typography.Text>
      <Upload accept="image/png,image/jpeg,image/webp" showUploadList={false} beforeUpload={(file) => upload(asset, file)}><Button disabled={busy}>{asset.image ? "替换参考图" : "上传参考图"}</Button></Upload>
      {asset.image && <Popconfirm title="删除这张参考图？" description="相关镜头下次生成时将不再使用它。" okText="删除图片" cancelText="取消" onConfirm={() => void onDelete(asset.id)}><Button danger disabled={busy}>删除图片</Button></Popconfirm>}
    </div>
  </Card>;

  return <div className="asset-workspace">
    <div className="section-heading"><div><Typography.Title level={4}>项目资产</Typography.Title><Typography.Text type="secondary">上传角色和场景参考图，系统会自动关联到对应镜头。</Typography.Text></div>
      <Button type="primary" onClick={() => { form.resetFields(); setEditing({ id: "", kind: "reference", name: "", description: "", entityName: null, scopeShotIds: [], image: null, revision: 0 }); }} disabled={!project.shots.length}>新增其他参考</Button>
    </div>
    {!project.shots.length ? <Alert type="info" showIcon message="导演完成分镜后，可在这里上传角色、场景和其他参考图。" /> : <>
      <div className="asset-grid">{entities.length ? entities.map(entityCard) : <Empty description="导演规划没有角色或场景资产" />}</div>
      <div className="section-heading asset-subheading"><div><Typography.Title level={5}>其他参考</Typography.Title><Typography.Text type="secondary">例如道具、服装或特定镜头需要的视觉元素。</Typography.Text></div></div>
      {references.length ? <div className="asset-grid">{references.map((asset) => <Card className="asset-card" key={asset.id}>
        <div className="asset-card-heading"><Typography.Text strong>{asset.name}</Typography.Text><Typography.Paragraph type="secondary">适用镜头：{asset.scopeShotIds.map((id) => project.shots.find((shot) => shot.id === id)?.title || id).join("、")}</Typography.Paragraph></div>
        <div className="asset-image-preview">{asset.image ? <img src={fileUrl(project.projectId, asset.image.path)} alt={`${asset.name}参考图`} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未上传参考图" />}</div>
        <Space wrap><Upload accept="image/png,image/jpeg,image/webp" showUploadList={false} beforeUpload={(file) => upload(asset, file)}><Button disabled={busy}>{asset.image ? "替换参考图" : "上传参考图"}</Button></Upload><Button disabled={busy} onClick={() => { setEditing(asset); form.setFieldsValue({ name: asset.name, description: asset.description, scopeShotIds: asset.scopeShotIds }); }}>编辑范围</Button><Popconfirm title="删除这个资产？" okText="删除" cancelText="取消" onConfirm={() => void onDelete(asset.id)}><Button danger disabled={busy}>删除</Button></Popconfirm></Space>
      </Card>)}</div> : <Empty description="还没有其他参考资产" />}
    </>}
    <Modal title={editing?.id ? "编辑其他参考" : "新增其他参考"} open={!!editing} onCancel={() => setEditing(null)} onOk={() => void form.submit()} confirmLoading={busy} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={(values) => void submit(values)}>
        <Form.Item name="name" label="资产名称" rules={[{ required: true, whitespace: true, message: "请填写名称" }]}><Input maxLength={120} /></Form.Item>
        <Form.Item name="description" label="说明"><Input.TextArea rows={2} maxLength={1000} /></Form.Item>
        <Form.Item name="scopeShotIds" label="关联镜头" rules={[{ required: true, message: "至少选择一个镜头" }]}><Select mode="multiple" options={project.shots.map((shot) => ({ value: shot.id, label: `${shot.index + 1}. ${shot.title}` }))} /></Form.Item>
      </Form>
    </Modal>
  </div>;
}
