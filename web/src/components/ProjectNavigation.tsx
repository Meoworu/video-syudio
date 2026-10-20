import { useState } from "react";
import { Button, Drawer, Empty, Form, Input, InputNumber, List, Popconfirm, Select, Space, Tag, Typography } from "antd";
import { fileUrl } from "../api";
import type { CreateProjectInput } from "../hooks/useStudioWorkspace";
import type { Project } from "../types";

type VideoJob = { projectId: string; projectTitle: string; shotId: string; shotTitle: string; status: string; path?: string | null; errorMessage?: string | null };

function videoStatus(status: string) {
  const labels: Record<string, [string, string]> = {
    submitting: ["提交中", "processing"], generating: ["生成中", "processing"], downloading: ["下载中", "processing"],
    complete: ["已完成", "success"], failed: ["生成失败", "error"], cancelled: ["已取消", "default"], idle: ["待生成", "default"],
  };
  return labels[status] || [status, "default"];
}

function CreateProjectDrawer({ open, busy, onClose, onCreate }: {
  open: boolean; busy: boolean; onClose: () => void; onCreate: (payload: CreateProjectInput) => Promise<Project | null>;
}) {
  const [form] = Form.useForm<CreateProjectInput>();

  async function submit(values: CreateProjectInput) {
    const result = await onCreate({ ...values, story: values.story.trim(), style: values.style.trim() });
    if (result) {
      form.resetFields();
      onClose();
    }
  }

  return <Drawer title="创建视频项目" open={open} onClose={onClose} width="min(460px, 100vw)" destroyOnClose>
    <Typography.Paragraph type="secondary">先描述故事，导演会生成大纲与镜头设计。</Typography.Paragraph>
    <Form form={form} layout="vertical" initialValues={{ aspectRatio: "9:16", style: "cinematic animated short film", sceneCount: 3 }} onFinish={(values) => void submit(values)}>
      <Form.Item name="story" label="故事梗概" rules={[{ required: true, whitespace: true, message: "请填写故事梗概" }]}>
        <Input.TextArea rows={6} maxLength={6000} showCount placeholder="人物、目标、冲突和结局……" />
      </Form.Item>
      <Form.Item name="aspectRatio" label="画面比例">
        <Select options={[{ value: "9:16", label: "竖屏 · 9:16" }, { value: "16:9", label: "横屏 · 16:9" }]} />
      </Form.Item>
      <Form.Item name="style" label="视觉风格" rules={[{ required: true, whitespace: true, message: "请填写视觉风格" }]}>
        <Input maxLength={180} placeholder="例如：电影感动画短片" />
      </Form.Item>
      <Form.Item name="sceneCount" label="场景数" rules={[{ required: true, message: "请选择场景数" }]}>
        <InputNumber min={1} max={12} precision={0} style={{ width: "100%" }} />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={busy} block>生成导演大纲与分镜</Button>
    </Form>
  </Drawer>;
}

export function ProjectNavigation({ projects, selectedId, jobs, busy, loading, onSelect, onCreate, onDeleteFailedVideo }: {
  projects: Project[]; selectedId?: string; jobs: VideoJob[]; busy: boolean; loading: boolean;
  onSelect: (id: string) => void; onCreate: (payload: CreateProjectInput) => Promise<Project | null>;
  onDeleteFailedVideo: (projectId: string, shotId: string) => Promise<Project | null>;
}) {
  const [createOpen, setCreateOpen] = useState(false);
  const [jobsOpen, setJobsOpen] = useState(false);
  return <>
    <div className="sidebar-heading">
      <div><Typography.Text className="eyebrow">工作区</Typography.Text><Typography.Title level={5}>我的项目</Typography.Title></div>
      <Button type="primary" onClick={() => setCreateOpen(true)}>新建项目</Button>
    </div>
    {projects.length ? <List
      loading={loading}
      className="project-list"
      dataSource={projects}
      renderItem={(project) => <List.Item key={project.projectId}>
        <Button type={selectedId === project.projectId ? "primary" : "text"} block className="project-nav-item" onClick={() => onSelect(project.projectId)}>
          <span className="project-nav-title">{project.title}</span>
          <span className="project-nav-subtitle">{project.shots.length} 个镜头 · {project.aspectRatio}</span>
        </Button>
      </List.Item>}
    /> : loading ? <div className="sidebar-loading"><Typography.Text type="secondary">正在加载项目…</Typography.Text></div> : <Empty className="sidebar-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有项目" />}
    <Button className="jobs-trigger" block onClick={() => setJobsOpen(true)}>查看视频任务 <span className="task-count">{jobs.length}</span></Button>
    <CreateProjectDrawer open={createOpen} busy={busy} onClose={() => setCreateOpen(false)} onCreate={onCreate} />
    <Drawer title="视频任务" open={jobsOpen} onClose={() => setJobsOpen(false)} width="min(420px, 100vw)">
      {jobs.length ? <List dataSource={jobs} renderItem={(job) => {
        const [label, color] = videoStatus(job.status);
        return <List.Item key={`${job.projectId}-${job.shotId}`} actions={job.status === "failed" ? [<Popconfirm key="delete" title="删除这条失败记录？" description="该镜头将恢复为待生成状态。" okText="删除" cancelText="取消" onConfirm={() => onDeleteFailedVideo(job.projectId, job.shotId)}><Button type="link" danger disabled={busy}>删除</Button></Popconfirm>] : undefined}>
          <Space direction="vertical" size={4} className="job-item">
            <Space wrap><Typography.Text strong>{job.projectTitle}</Typography.Text><Tag color={color}>{label}</Tag></Space>
            <Typography.Text>{job.shotTitle}</Typography.Text>
            {job.errorMessage && <Typography.Text type="danger">{job.errorMessage}</Typography.Text>}
            {job.path && <a href={fileUrl(job.projectId, job.path)} target="_blank" rel="noreferrer">打开生成视频</a>}
          </Space>
        </List.Item>;
      }} /> : <Empty description="暂无视频任务" />}
    </Drawer>
  </>;
}
