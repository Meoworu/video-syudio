# Development Plan: Ant Design 工作台改版

## 1. Requirement Understanding

- Goal: 用项目已安装的 Ant Design 重设计 Web 端，形成清晰、统一、适合视频制作流程的工作台。
- Users / callers: 在浏览器中创建项目、审核分镜、上传首尾帧、生成视频与旁白、合成成片的操作者。
- Scope: 信息架构、视觉规范、响应式布局、表单与状态反馈，以及当前功能在新界面中的完整迁移。
- Non-goals: 更换 React/Vite、修改生成算法或后端接口、加入项目删除等新业务功能、真实调用 Google/MiniMax 验收。
- Success criteria: 现有全部操作可在新界面完成；桌面和窄屏无横向溢出；生成、失败、空状态及禁用原因可理解；`npm run build` 通过；键盘可访问主要操作。

## 2. Assumptions and Open Questions

### Assumptions

- 采用浅色专业制作台风格：中性灰背景、白色内容层、深色文字和克制的蓝色操作色。品牌视觉尚未定义，因此先以 Ant Design 主题变量建立可调整的基线。
- 保持单页应用和现有项目选择方式；不引入路由、状态管理库或图表库。桌面以项目导航 + 工作区为主，窄屏改为抽屉导航。
- 展示语言沿用当前中文。服务商凭据只影响实际生成，不作为界面渲染的前提。

### Open Questions

- 无阻塞问题。颜色和品牌字样可在方案评审时调整，不影响组件边界与接口。

## 3. Repository Reconnaissance

- Rules and docs read: 用户提供的 AGENTS.md 指令、`README.md`、`dev.md`、`docs/acceptance-runbook.md`。
- Relevant subprojects: `web/`（React 19 + Vite + TypeScript），`app/api/projects.py`（现有业务契约）。
- Build / test / lint commands discovered: `web/package.json` 提供 `npm run build`、`npm run dev`；当前没有前端单测或 lint 命令。
- Git status considerations: 工作区已有多处未提交修改，包括 `web/src/main.tsx`、`web/src/styles.css` 和 `web/src/api.ts`；实施时以届时文件为基线，保留这些改动。
- Evidence limits: 本方案依据源码和文档制定，未对运行中的页面做视觉截图或真实服务商调用。

## 4. Existing Architecture

- Observed: `web/src/main.tsx:15-72` 的 `App` 同时管理项目列表、当前项目、表单草稿、任务列表、全局 busy 状态和每 3 秒轮询；`web/src/main.tsx:74-172` 将整条业务流程渲染在一个长页面中。
- Observed: `web/src/styles.css` 使用通用元素选择器和双列布局，缺少统一的组件层级；`web/package.json` 已声明 `antd`，但 `web/src/main.tsx` 没有使用它。
- Observed: `web/src/api.ts` 汇总 `/v1` 请求；`web/src/types.ts` 定义项目、镜头、旁白和剪辑数据；`web/vite.config.ts` 将 `/v1` 代理到 8010 端口。
- Inference: 轮询与编辑草稿同处一个组件，拆分界面时需要明确草稿同步边界，避免后台刷新覆盖未保存输入。

## 5. Relevant Files

| File | Existing or proposed | Responsibility and evidence | Requirement |
|---|---|---|---|
| `web/src/main.tsx` | Existing | 当前唯一页面与全部交互入口 | 拆为入口及页面组合 |
| `web/src/styles.css` | Existing | 当前全局样式和时间线样式 | 响应式布局与语义样式 |
| `web/src/api.ts` | Existing | 所有现有 `/v1` 调用与文件 URL | 保持请求契约，统一错误展示 |
| `web/src/types.ts` | Existing | Project、Shot、Narration 类型 | 组件属性和状态映射 |
| `web/src/theme.ts` | Proposed | Ant Design `ConfigProvider` token | 统一色彩、字级、圆角、间距 |
| `web/src/hooks/useStudioWorkspace.ts` | Proposed | 项目加载、轮询、动作状态 | 展示与数据逻辑分离 |
| `web/src/components/` | Proposed | 导航、概览、分镜、旁白、合成等界面组件 | 按工作流程拆分 |
| `app/domain/models.py`、`app/api/projects.py` | Existing | 创建/编辑/上传约束与失效规则 | 前端校验和提示，计划不改后端 |

## 6. Existing Patterns to Reuse

- Pattern: `web/src/api.ts` 的请求函数和 `fileUrl()`；继续作为唯一 API 入口，不在组件中散写 `fetch`。
- Evidence: `web/src/main.tsx:30-65` 的 `refresh/create/run`，`web/src/types.ts` 的 `Project` 类型，以及 `web/vite.config.ts` 的代理配置。
- How the plan reuses it: 将加载和动作编排抽成 hook，组件接收明确的数据与回调；保留项目自动刷新、视频取消、旁白版本选择和最终视频预览。
- Gaps or differences: 现有 `message` 是页面顶部字符串，后续用 Ant Design `Alert`、`App` 的消息能力承载可读错误；状态标签需映射后端实际枚举。

## 7. Impact Analysis

- Direct code impact: 主要改动 `web/src/main.tsx`、`web/src/styles.css`，新增主题、hook 和展示组件。
- Indirect consumers: `web/src/api.ts` 与 `web/src/types.ts` 被新组件复用；Vite 代理和 Python 服务保持现状。
- API / data / state / configuration: 不改变接口和持久化格式。保留 3 秒轮询，并避免重复请求与未保存草稿被刷新覆盖。
- Tests and generated artifacts: 用 `npm run build` 检查 TypeScript 和打包；按浏览器手动矩阵检查交互。`web/dist/` 仍由 Git 忽略。
- Security / performance / observability: 保留用户文本的 React 转义；视频和图片保持原文件 URL；长镜头列表避免所有详情默认展开，减少初始渲染负担。
- Deployment and operations: 无后端迁移、环境变量或部署配置变化。

## 8. Proposed Architecture

视觉方向为内容优先的浅色工作台：固定高度的顶栏展示产品名、当前项目与任务入口；左侧项目列表保持紧凑；主区按“概览 / 分镜 / 旁白 / 成片”分区。新建项目用抽屉承载表单，避免常驻大表单挤压编辑区。窄屏时项目导航进入抽屉，工作区单列排列。

```text
ConfigProvider(theme) + Antd App
  └─ StudioShell
      ├─ ProjectSidebar / ProjectCreateDrawer / VideoJobsDrawer
      └─ WorkspaceTabs
          ├─ ProjectOverview + EditTimeline
          ├─ ShotWorkspace
          ├─ NarrationPanel
          └─ FinalAssemblyPanel
```

- Ant Design 承载 `Layout`、`Button`、`Form`、`Input`、`Select`、`InputNumber`、`List`、`Tabs`、`Drawer`、`Card`、`Tag`、`Alert`、`Empty`、`Skeleton`、`Collapse`、`Upload`、`Slider`、`Modal` 等标准界面。时间线继续用轻量自定义 DOM/CSS 表示真实时长与跨镜头 cue，避免把普通步骤组件误用为时间轴。
- 定义主题 token 和少量语义 CSS 类，移除会影响 Ant Design 的通用 `button/input/select` 样式。状态同时显示文字和颜色；主操作放在对应流程区域。
- `useStudioWorkspace` 管理服务端数据与请求状态；镜头和旁白草稿留在各自编辑组件，仅在项目切换或成功保存后重置。轮询只刷新服务端快照，不覆盖脏草稿。
- 保持原生 `<audio>`、`<video>` 控件。上传控件应传原始 `File` 与原 MIME，不能改成默认 `multipart/form-data`，因为后端读取的是请求体原始字节。

## 9. Data / API Changes

- Contract changes: None。沿用 `web/src/api.ts` 的端点、JSON 结构和 `fileUrl()`。
- Validation and error behavior: 创建项目校验故事非空、场景数 1–12；镜头标题/提示词非空、时长 3–10 秒；帧图片仅 PNG/JPEG/WebP 且不超过 20 MB（`app/domain/models.py:191-202`、`app/api/projects.py:112-159`）。失败时保留草稿并显示服务端错误。
- Migration / compatibility: 无数据迁移。编辑镜头或替换帧会使既有视频/成片失效（`app/api/projects.py:112-159,234-273`）；界面应在提交前提示影响，返回后及时更新状态。

## 10. Dependency Graph

```text
Task 1 → Task 2 → Task 3
                  ├→ Task 4 ─┐
                  └→ Task 5 ─┴→ Task 6 → Task 7
```

## 11. Implementation Tasks

### Task 1: 分离数据编排与编辑草稿

- 目标：让 UI 改版复用稳定的数据入口。
- 涉及文件：`web/src/main.tsx`；`web/src/hooks/useStudioWorkspace.ts`（Proposed）；`web/src/api.ts`。
- 修改内容：抽出项目获取、任务获取、轮询、动作执行与错误归一化；以项目 ID 为刷新边界，防止旧请求覆盖新选择；保留未保存草稿。
- 依赖：无
- 验收标准：项目切换和 3 秒刷新仍工作；请求失败可重试；后台刷新不覆盖正在编辑的内容。
- 验证方式：`cd web && npm run build`；手动编辑草稿并等待两轮刷新。
- 风险与回滚：异步竞态可能更新错项目；按项目 ID 校验响应，异常时回退到原组件内数据编排。

### Task 2: 建立主题与响应式外壳

- 目标：形成统一的视觉层级和可伸缩工作区。
- 涉及文件：`web/src/main.tsx`、`web/src/styles.css`；`web/src/theme.ts`、`web/src/components/StudioShell.tsx`（Proposed）。
- 修改内容：接入 `ConfigProvider` 和 Ant Design `App`；建立顶栏、项目侧栏容器和主内容区；定义颜色、字体、间距、焦点和断点，移除冲突的全局表单样式。
- 依赖：Task 1
- 验收标准：桌面与 320/768/1024/1440px 宽度布局稳定，键盘焦点可见，无横向滚动。
- 验证方式：`cd web && npm run build`；浏览器逐宽度检查和 Tab 导航。
- 风险与回滚：全局样式可能影响媒体控件；限定新样式作用域，必要时回退单个 token/规则。

### Task 3: 重做项目导航、创建和任务抽屉

- 目标：让用户快速进入项目并理解后台任务状态。
- 涉及文件：`web/src/main.tsx`；`web/src/components/ProjectSidebar.tsx`、`ProjectCreateDrawer.tsx`、`VideoJobsDrawer.tsx`（Proposed）。
- 修改内容：用 `List`/状态标签显示项目；用 `Form` 和抽屉创建项目；用任务抽屉显示视频状态、错误和文件入口；补齐加载、空、失败状态。
- 依赖：Task 2
- 验收标准：新建项目参数与当前请求一致；项目/任务选择可用；无项目和请求失败时有明确指引。
- 验证方式：`cd web && npm run build`；手动检查列表、抽屉、表单边界值与错误反馈。
- 风险与回滚：创建属于真实服务端动作；联调使用专门测试项目，UI 逻辑可回退为原表单。

### Task 4: 重做概览与剪辑时间线

- 目标：让大纲、场景关系和片长在首屏容易扫描。
- 涉及文件：`web/src/main.tsx`、`web/src/styles.css`；`web/src/components/ProjectOverview.tsx`、`EditTimeline.tsx`（Proposed）。
- 修改内容：把导演大纲拆为摘要、角色、场景和风格区；用可折叠信息层级呈现长提示词；依据 `editPlan` 和 `narration.alignment` 绘制有文本标签的双轨时间线。
- 依赖：Task 3
- 验收标准：空大纲、生成中、导演失败/重试均可见；时间线顺序和片长与数据一致，窄屏可水平滚动查看。
- 验证方式：`cd web && npm run build`；用不同镜头数和有/无 cue 的项目人工核对。
- 风险与回滚：长内容易溢出；保留文本详情入口，时间线可退化为纵向列表。

### Task 5: 重做镜头工作区

- 目标：将镜头审核、修改、上传和生成组织为清晰的单镜头操作流。
- 涉及文件：`web/src/main.tsx`、`web/src/styles.css`；`web/src/components/ShotWorkspace.tsx`、`ShotEditor.tsx`（Proposed）。
- 修改内容：镜头列表显示编号、时长、首尾帧与任务状态；编辑区使用 Ant Design 表单、折叠详情和帧预览；上传前校验格式/大小，明确保存、生成、取消及批量生成的条件和影响。
- 依赖：Task 3
- 验收标准：现有镜头字段和操作均可用；请求中禁用冲突动作；编辑或换帧前说明既有视频/成片会失效。
- 验证方式：`cd web && npm run build`；手动检查无帧/单帧/双帧/生成中/失败/完成状态和错误输入。
- 风险与回滚：Ant Design Upload 默认协议与后端不符；通过自定义请求复用 `uploadFrame()` 原始文件上传，异常时保留原文件输入实现。

### Task 6: 重做旁白与成片区

- 目标：清晰展示文稿、时间对齐、语音版本及合成条件。
- 涉及文件：`web/src/main.tsx`、`web/src/styles.css`；`web/src/components/NarrationPanel.tsx`、`FinalAssemblyPanel.tsx`（Proposed）。
- 修改内容：文稿编辑、语速、句子 cue、版本选择、音频试听分区；成片区展示剪辑时长、依赖状态、合成按钮和视频预览；用 `Alert` 说明时间警告和失败原因。
- 依赖：Task 4, Task 5
- 验收标准：生成/保存/切换版本/合成动作与现有 API 一致；缺少视频或音频时明确说明不能合成的原因。
- 验证方式：`cd web && npm run build`；手动检查无文稿、草稿、多个 take、音频缺失和成片存在状态。
- 风险与回滚：轮询可能与文稿输入冲突；仅在项目切换或成功保存时同步编辑器，并保留错误时输入。

### Task 7: 可用性收尾与回归

- 目标：收束视觉细节并验证整个操作链未退化。
- 涉及文件：`web/src/styles.css`、`web/src/main.tsx`、`web/index.html` 及 Task 3–6 新增组件。
- 修改内容：统一按钮优先级、状态文案、间距和媒体尺寸；检查标题层级、表单标签、焦点、抽屉关闭后的焦点恢复、移动端滚动和控制台错误。
- 依赖：Task 6
- 验收标准：主要操作可用键盘完成；无明显布局溢出；所有既有功能都有对应入口且无控制台错误。
- 验证方式：`cd web && npm run build`；按第 12 节矩阵在浏览器走查。
- 风险与回滚：局部样式调整可能影响其他区块；按组件检查并回退对应样式。

## 12. Test Plan

| Level | Scenario | Verification | Evidence / expected result |
|---|---|---|---|
| Build | 类型与打包 | `cd web && npm run build` | 无 TypeScript 或 Vite 错误 |
| UI states | 空项目、加载、失败、导演生成中 | 浏览器手动检查，必要时拦截 `/v1` 响应 | 每种状态有可读说明和下一步 |
| Forms | 故事为空、场景数越界、镜头字段越界、图片类型/大小错误 | 浏览器手动输入 | 提交前阻止无效输入，保留草稿 |
| Workflow | 项目选择、分镜编辑、首尾帧上传、任务状态、旁白与合成入口 | 对照现有 API 和测试项目逐项走查 | 不丢失当前操作，按钮状态与服务端一致 |
| Failure | 4xx/5xx、网络断开、任务取消/失败 | 浏览器手动模拟或使用测试项目 | 错误可见、可重试，媒体与草稿不消失 |
| Responsive / a11y | 320/768/1024/1440px、Tab/Enter/Esc | 浏览器窗口与键盘走查 | 无横向溢出；抽屉与表单可操作，焦点清晰 |

## 13. Risks / Edge Cases

| Risk or edge case | Impact | Mitigation / handling |
|---|---|---|
| 轮询更新时用户正在编辑 | 草稿丢失或闪动 | 服务端快照与局部草稿分开；仅明确保存/切换项目时重置 |
| 编辑镜头或替换帧会清除已有视频/成片 | 用户误以为媒体保留 | 提交前展示影响提示，成功后重新读取项目状态 |
| 长大纲、长提示词、大量镜头 | 信息难扫、渲染拥挤 | 摘要优先、详情折叠、列表按状态和镜头编号扫描 |
| 移动端抽屉与媒体预览 | 操作被遮挡 | 单列布局，控件容器宽度限制，检查焦点与滚动 |
| 后端 409/网络错误 | 动作状态与页面不一致 | 解析错误、保留输入、刷新服务端快照并提供重试 |

## 14. Rollback / Compatibility

- Compatibility constraints: 保持 `/v1` 路径、文件 URL、请求体、轮询频率与项目数据格式；不要求后端发布。
- Rollout / migration order: 按任务逐块替换旧 JSX，每个检查点保留可运行页面；最终移除旧通用样式。
- Rollback steps: 若某区块回归失败，回退该区块组件和调用入口，保留已验证的主题与其他区块；没有数据迁移需要回滚。

## 15. Implementation Order and Checkpoints

1. Task 1 → Task 2 → Task 3；Task 4 与 Task 5 可在 Task 3 后独立实施；完成两者后实施 Task 6 → Task 7。

### Checkpoint 1: Task 1–2

- 页面仍能加载项目和轮询；工作台在 320/1440px 可用；`npm run build` 通过。

### Checkpoint 2: Task 3–4

- 创建、项目切换、任务抽屉和大纲/时间线在空数据及正常数据下可用。

### Checkpoint 3: Task 5–6

- 镜头、旁白和合成所有原有入口完成迁移；关键禁用条件与服务端状态一致。

### Checkpoint 4: Task 7

- 构建通过，响应式、键盘、错误和完整工作流检查完成。

## 16. Approval Gate

- Status: Approved
- Blocking decisions: None
- Application code changed: Yes, implementation is recorded in `web/src/`.
