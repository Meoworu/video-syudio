import { useState } from "react";
import { Button, Drawer, Empty, Form, Input, InputNumber, List, Popconfirm, Select, Space, Tag, Tooltip, Typography } from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import { fileUrl } from "../api";
import type { CreateProjectInput } from "../hooks/useStudioWorkspace";
import type { Project } from "../types";
import { getVideoStylePrompt, VIDEO_STYLE_PRESETS, type VideoStylePreset } from "../videoStyles";

type VideoJob = { projectId: string; projectTitle: string; shotId: string; shotTitle: string; status: string; path?: string | null; errorMessage?: string | null };
type CreateProjectFormValues = Omit<CreateProjectInput, "style"> & { stylePreset: VideoStylePreset; customStyle?: string };

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
  const [form] = Form.useForm<CreateProjectFormValues>();
  const projectType = Form.useWatch("projectType", form) || "story";
  const stylePreset = Form.useWatch("stylePreset", form) || "cinematic_realism";

  async function submit(values: CreateProjectFormValues) {
    const style = values.stylePreset === "custom" ? values.customStyle?.trim() || "" : getVideoStylePrompt(values.stylePreset);
    const result = await onCreate({
      projectType: values.projectType || "story",
      story: values.story,
      aspectRatio: values.aspectRatio,
      sceneCount: values.sceneCount,
      style,
    });
    if (result) {
      form.resetFields();
      onClose();
    }
  }

  return <Drawer title="创建视频项目" open={open} onClose={onClose} width="min(460px, 100vw)" destroyOnClose>
    <Typography.Paragraph type="secondary">故事原文会完整保留，再拆解为制作剧本和分镜。</Typography.Paragraph>
    <Form form={form} layout="vertical" initialValues={{ projectType: "story", aspectRatio: "9:16", stylePreset: "cinematic_realism", sceneCount: 3 }} onFinish={(values) => void submit(values)}>
      <Form.Item name="projectType" label="项目类型" rules={[{ required: true }]}>
        <Select options={[{ value: "story", label: "普通故事" }, { value: "science", label: "科普" }]} />
      </Form.Item>
      {projectType === "science" && <Typography.Paragraph type="secondary">科普项目不生成出镜人类；原文中的真实动物和昆虫可以作为生物主体呈现。</Typography.Paragraph>}
      <Form.Item name="story" label={projectType === "science" ? "科普原文" : "故事原文"} rules={[
        { required: true, whitespace: true, message: "请输入原文内容" },
        { validator: (_, value: string | undefined) => !value || Array.from(value).length <= 6000 ? Promise.resolve() : Promise.reject(new Error("原文超过 6000 个字符，请拆分后创建项目；输入内容已保留。")) },
      ]}>
        <Input.TextArea rows={6} showCount={{ formatter: ({ value }) => Array.from(value || "").length }} placeholder={projectType === "science" ? "粘贴需要制作的视频原文，系统会按原文拆解……" : "粘贴完整故事或剧本，系统不会改写原文……"} />
      </Form.Item>
      <Form.Item name="aspectRatio" label="画面比例">
        <Select options={[{ value: "9:16", label: "竖屏 · 9:16" }, { value: "16:9", label: "横屏 · 16:9" }]} />
      </Form.Item>
      <Form.Item name="stylePreset" label="视频风格" rules={[{ required: true, message: "请选择视频风格" }]}>
        <Select options={[...VIDEO_STYLE_PRESETS.map(({ value, label }) => ({ value, label })), { value: "custom", label: "自定义" }]} />
      </Form.Item>
      <Typography.Paragraph type="secondary">风格会转换为统一的画面提示词，应用于导演规划和首尾帧生成。</Typography.Paragraph>
      {stylePreset === "custom" && <Form.Item name="customStyle" label="自定义风格提示词" rules={[{ required: true, whitespace: true, message: "请填写自定义风格提示词" }]}>
        <Input.TextArea maxLength={500} showCount rows={3} placeholder="描述画面质感、色彩、光线或动画形式" />
      </Form.Item>}
      <Form.Item name="sceneCount" label="目标镜头数" rules={[{ required: true, message: "请选择目标镜头数" }]}>
        <InputNumber min={1} max={12} precision={0} style={{ width: "100%" }} />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={busy} block>拆解原文并生成分镜</Button>
    </Form>
  </Drawer>;
}

export function ProjectNavigation({ projects, selectedId, jobs, busy, loading, onSelect, onCreate, onDeleteFailedVideo, onDeleteProject }: {
  projects: Project[]; selectedId?: string; jobs: VideoJob[]; busy: boolean; loading: boolean;
  onSelect: (id: string) => void; onCreate: (payload: CreateProjectInput) => Promise<Project | null>;
  onDeleteFailedVideo: (projectId: string, shotId: string) => Promise<Project | null>;
  onDeleteProject: (projectId: string) => Promise<boolean>;
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
      renderItem={(project) => {
        const active = project.status === "generating" || project.shots.some((shot) =>
          ["submitting", "generating", "downloading"].includes(shot.video?.status || "") ||
          Object.values(shot.frames).some((frame) => frame.job && ["queued", "generating"].includes(frame.job.status))
        ) || jobs.some((job) => job.projectId === project.projectId && ["submitting", "generating", "downloading"].includes(job.status));
        return <List.Item key={project.projectId} actions={[<Popconfirm key="delete" title={`删除项目“${project.title}”？`} description="项目及其本地图片、视频和音频将永久删除；不会取消远端任务。此操作不可恢复。" okText="永久删除" cancelText="取消" okButtonProps={{ danger: true }} onConfirm={() => onDeleteProject(project.projectId)}>
          <Tooltip title={active ? "项目有任务正在运行，暂时不能删除" : "删除项目及其本地文件"}><span><Button aria-label={`删除项目 ${project.title}`} type="text" danger icon={<DeleteOutlined />} disabled={busy || active} /></span></Tooltip>
        </Popconfirm>] }>
          <Button type={selectedId === project.projectId ? "primary" : "text"} block className="project-nav-item" onClick={() => onSelect(project.projectId)}>
            <span className="project-nav-title">{project.title}</span>
            <span className="project-nav-subtitle">{project.shots.length} 个镜头 · {project.aspectRatio} · {project.projectType === "science" ? "科普" : "普通故事"}</span>
          </Button>
        </List.Item>;
      }}
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
