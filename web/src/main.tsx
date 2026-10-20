import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { Alert, App as AntdApp, Button, ConfigProvider, Drawer, Empty, Layout, Skeleton, Space, Tabs, Typography } from "antd";
import { FinalAssemblyPanel } from "./components/FinalAssemblyPanel";
import { AssetWorkspace } from "./components/AssetWorkspace";
import { NarrationPanel } from "./components/NarrationPanel";
import { ProjectNavigation } from "./components/ProjectNavigation";
import { ProjectOverview } from "./components/ProjectOverview";
import { ShotWorkspace } from "./components/ShotWorkspace";
import { useStudioWorkspace } from "./hooks/useStudioWorkspace";
import { studioTheme } from "./theme";
import "./styles.css";

const { Header, Sider, Content } = Layout;

function Studio() {
  const workspace = useStudioWorkspace();
  const [mobileProjectsOpen, setMobileProjectsOpen] = useState(false);
  const project = workspace.selected;
  const navigation = <ProjectNavigation
    projects={workspace.projects}
    selectedId={workspace.selectedId}
    jobs={workspace.videoJobs}
    busy={workspace.busy}
    loading={workspace.loadingProjects}
    onSelect={(id) => { void workspace.selectProject(id); setMobileProjectsOpen(false); }}
    onCreate={workspace.create}
    onDeleteFailedVideo={workspace.actions.deleteFailedVideo}
  />;

  const tabItems = project ? [
    { key: "overview", label: "项目概览", children: <ProjectOverview project={project} busy={workspace.busy} onRetry={() => void workspace.actions.retryDirector(project.projectId)} /> },
    { key: "assets", label: "资产", children: <AssetWorkspace project={project} busy={workspace.busy}
      onCreate={(payload) => workspace.actions.createAsset(project.projectId, payload)}
      onUpdate={(assetId, payload) => workspace.actions.updateAsset(project.projectId, assetId, payload)}
      onUpload={(assetId, file) => workspace.actions.uploadAssetImage(project.projectId, assetId, file)}
      onDelete={(assetId) => workspace.actions.deleteAsset(project.projectId, assetId)}
    /> },
    { key: "shots", label: `分镜 · ${project.shots.length}`, children: <ShotWorkspace
      project={project} busy={workspace.busy}
      onUpdate={(shotId, draft) => workspace.actions.updateShot(project.projectId, shotId, draft)}
      onUpload={(shotId, role, file) => workspace.actions.uploadFrame(project.projectId, shotId, role, file)}
      onGenerate={(shotId) => workspace.actions.generateVideo(project.projectId, shotId)}
      onCancel={(shotId) => workspace.actions.cancelVideo(project.projectId, shotId)}
      onDeleteFailedVideo={(shotId) => workspace.actions.deleteFailedVideo(project.projectId, shotId)}
      onFrameConfig={(shotId, role, config) => workspace.actions.updateFrameConfig(project.projectId, shotId, role, config)}
      onGenerateFrame={(shotId, role) => workspace.actions.generateFrame(project.projectId, shotId, role)}
      onGenerateFrames={(shotId) => workspace.actions.generateFrames(project.projectId, shotId)}
      onSelectFrameVersion={(shotId, role, versionId) => workspace.actions.selectFrameVersion(project.projectId, shotId, role, versionId)}
      onDeleteFailedFrame={(shotId, role) => workspace.actions.deleteFailedFrameJob(project.projectId, shotId, role)}
      onGenerateAll={() => workspace.actions.generateAllVideos(project.projectId)}
    /> },
    { key: "narration", label: "连续旁白", children: <NarrationPanel
      project={project} busy={workspace.busy}
      onGenerate={() => workspace.actions.generateManuscript(project.projectId)}
      onSave={(manuscript) => workspace.actions.updateNarrationManuscript(project.projectId, manuscript)}
      onSynthesize={(speed) => workspace.actions.generateNarrationAudio(project.projectId, speed)}
      onSelectTake={(takeId) => workspace.actions.selectNarrationTake(project.projectId, takeId)}
    /> },
    { key: "assembly", label: "成片", children: <FinalAssemblyPanel project={project} busy={workspace.busy} onAssemble={() => workspace.actions.assembleProject(project.projectId)} /> },
  ] : [];

  return <Layout className="studio-layout">
    <Sider className="studio-sider" width={276} theme="light" breakpoint="lg" collapsedWidth={0}>
      <div className="brand-lockup"><span className="brand-mark">VS</span><div><Typography.Text strong>video-studio</Typography.Text><Typography.Text className="brand-subtitle">AI 视频制作工作台</Typography.Text></div></div>
      <div className="sider-navigation">{navigation}</div>
      <div className="sider-footer"><Typography.Text type="secondary">Google Agent Platform · MiniMax Speech</Typography.Text></div>
    </Sider>
    <Layout className="studio-main-layout">
      <Header className="studio-header">
        <Button className="mobile-project-trigger" onClick={() => setMobileProjectsOpen(true)}>项目</Button>
        <div className="header-current">
          <Typography.Text className="eyebrow">创作空间</Typography.Text>
          <Typography.Text strong>{project?.title || "新的视频项目"}</Typography.Text>
        </div>
        <Space className="header-meta" size={8}>
          <span className="online-dot" />
          <Typography.Text type="secondary">本地工作区</Typography.Text>
        </Space>
      </Header>
      <Content className="studio-content">
        {workspace.error && <Alert className="workspace-error" showIcon closable type="error" message="操作未完成" description={workspace.error} onClose={() => workspace.setError("")} />}
        {workspace.loadingProject && !project ? <Skeleton active title paragraph={{ rows: 6 }} /> : project ? <>
          <div className="content-intro"><div><Typography.Text className="eyebrow">VIDEO PRODUCTION</Typography.Text><Typography.Title level={3}>{project.title}</Typography.Title></div><Typography.Text type="secondary">从导演大纲到最终成片，在一个工作区完成。</Typography.Text></div>
          <Tabs key={project.projectId} className="workspace-tabs" items={tabItems} />
        </> : <div className="welcome-panel">
          <div className="welcome-copy"><Typography.Text className="eyebrow">AI VIDEO STUDIO</Typography.Text><Typography.Title>把故事，变成一部短片。</Typography.Title><Typography.Paragraph type="secondary">用 Google Agent Platform 设计分镜和生成画面，再用连续旁白与时间线完成剪辑。</Typography.Paragraph><Typography.Text type="secondary">从左侧新建项目，或选择一个已有项目继续制作。</Typography.Text></div>
          <div className="welcome-steps"><div><span>01</span><Typography.Text strong>导演规划</Typography.Text><Typography.Text type="secondary">大纲 · 场景 · 镜头</Typography.Text></div><div><span>02</span><Typography.Text strong>画面与旁白</Typography.Text><Typography.Text type="secondary">生成素材 · 对齐时间</Typography.Text></div><div><span>03</span><Typography.Text strong>合成成片</Typography.Text><Typography.Text type="secondary">镜头 · 音轨 · 导出</Typography.Text></div></div>
          {!workspace.projects.length && <Empty className="welcome-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有项目，请从项目栏创建一个新项目。" />}
        </div>}
      </Content>
    </Layout>
    <Drawer title="项目" placement="left" open={mobileProjectsOpen} onClose={() => setMobileProjectsOpen(false)} width={320} className="mobile-project-drawer">
      {navigation}
    </Drawer>
  </Layout>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider theme={studioTheme}><AntdApp><Studio /></AntdApp></ConfigProvider>
  </StrictMode>,
);
