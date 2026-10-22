# 项目类型与项目删除开发方案

## 1. Requirement Understanding

- 目标：新建项目时选择内容类型；科普项目不设计人物角色；网页支持删除项目及其本地素材。
- 使用者：通过网页创建、生成和管理视频项目的用户。
- 本期类型：`story`（普通故事）、`science`（科普）。类型影响导演大纲、分镜、首尾帧、视频提示词和连续旁白。
- 科普验收：导演角色数组和镜头角色数组为空，不自动创建角色资产，生成提示词明确禁止人物、主持人及拟人角色；网页不展示角色区域。
- 删除验收：有明确入口和二次确认；成功后项目与本地素材消失；活动任务项目不能删除；删除后不会被旧轮询响应重新显示。
- 本期范围外：修改已有项目类型、自定义类型模板、回收站、批量删除、远端生成记录删除、自动视觉审核及联网事实核查。

## 2. Assumptions and Open Questions

### Assumptions

- “等等”先按可扩展的类型字段设计，首版只实现明确提出的两类，不增加尚未定义行为的类型选项。
- 新建默认普通故事，已有项目缺少类型时也视为普通故事，不根据原始文本猜测类型。
- 科普采用无人物讲解：不用出镜主持人、旁观者、手部演示或拟人化向导；自然物、真实动物、器官模型、实验装置及微观示意可作为知识展示主体，但不包装成故事角色。
- 科普内容可以保留画外连续旁白；“无人物”不表示无声音。
- 项目类型创建后固定；输入框继续使用 API 字段 `story`，科普界面将其显示为“科普主题与内容”。
- 删除沿用现有永久本地删除语义，不发起 Google/MiniMax 远端删除请求；确认框说明本地文件不可恢复。
- 模型画面遵循指令仍需人工检查；本期通过结构校验和执行时提示词约束落实，不宣称能自动证明所有生成像素均无人物。用户上传的参考图也需自行选择无人物素材。

### Open Questions

- 无阻塞项。若后续需要产品介绍、风景纪录等类型，需另行定义各自的生成规则和验收标准后再增加枚举。

## 3. Repository Reconnaissance

- 已读取用户提供的 AGENTS.md 指令；使用 `coding-plan` 工作流，仅编写本方案。
- 已查看 `app/domain/models.py`、项目 API/Store、导演/首尾帧/视频/旁白服务、网页创建/导航/工作区状态及相关测试。
- 后端为 FastAPI + Pydantic，本地每项目目录存储 `project.json` 与媒体；前端为 React + TypeScript + Ant Design。
- 已发现命令：`.venv/bin/python -m pytest -q`、`.venv/bin/python scripts/check_provider_boundaries.py`（`README.md`、`dev.md`）；前端 `npm run build` 执行 `tsc -b && vite build`（`web/package.json`）。
- Git 状态：已有 Omni 1.1、资产上传界面等未提交修改，涉及 21 个文件；后续实现需在当前工作区上增量修改，不覆盖这些内容。
- 证据限制：前端未配置自动化测试脚本，界面交互与轮询竞态需浏览器验证；本次不运行真实模型调用，不安装依赖。

## 4. Existing Architecture

### Observed

1. `web/src/components/ProjectNavigation.tsx:CreateProjectDrawer` 只收集故事、比例、风格与场景数，调用 `useStudioWorkspace.create` → `web/src/api.ts:createProject`。
2. `app/api/projects.py:create_project` 使用 `DirectorService.start_project` 先落盘，再后台执行 `run_project`；原始创建参数保存在 `directorRequest`，重试和启动恢复会读取它。
3. `DirectorService._generate_outline` 强调人物动机；`_generate_shots` 的示例包含角色列表；`_build_project` 固定拼接人物身份、服装连续性要求。单独增加下拉框不会改变这些行为。
4. `Project.create_entity_asset_slots` 根据大纲的 `characters`、`locations` 自动创建资产；`ProjectOverview` 总是提供角色折叠区域；`AssetWorkspace` 根据资产列表展示角色/场景卡片。
5. `FrameService._snapshot/_prompt` 保存生图输入快照并拼接参考图要求；当前要求至少一张参考资产；`VideoService._run` 最终将镜头提示词发送给视频客户端。
6. `NarrationService.generate_manuscript` 使用统一的电影旁白提示词，目前不了解项目类型。
7. 后端 **已有** `DELETE /v1/projects/{project_id}`，成功返回 `{"projectId":"…","deleted":true}`；项目锁内检查导演、图片、视频活动状态，并调用 `ProjectStore.delete_project` 删除整个目录。
8. `ProjectStore.delete_project` 校验 ID、根目录范围与符号链接；`tests/test_projects.py` 已覆盖删除媒体、404、无效 ID、活动任务和符号链接保护。
9. 网页没有项目删除 API 包装及入口；`useStudioWorkspace` 每三秒轮询，使用 `selectionVersionRef`、`dataVersionRef` 防止旧响应覆盖新状态；其 `run()` 专用于返回 `Project` 的操作。
10. 旁白生成、语音生成和合成路由在项目锁内同步执行（`app/api/projects.py`），删除请求会等待这些写操作释放锁。

### Inference

- 类型必须同时持久化到 `Project` 和创建请求快照，才可在生成期间、失败重试、服务重启后保持一致。
- 删除应复用现有后端保护，新增独立前端操作，不能把删除返回值当作 `Project` 塞入通用 `run()`。

## 5. Relevant Files

| 文件 | 状态 | 责任与依据 | 计划改动 |
|---|---|---|---|
| `app/domain/models.py` | 已有 | `CreateProjectRequest`、`Project`、资产槽派生 | 类型字段、旧数据默认值、科普角色资产保护 |
| `app/services/project_type_policy.py` | 拟新增 | 小型公共内容规则模块 | 两类规则与科普视觉约束，供生成服务复用 |
| `app/services/director_service.py` | 已有 | 两阶段生成、后台落盘与重试 | 类型传递、科普大纲/分镜规则和结构校验 |
| `app/services/frame_service.py` | 已有 | 生图输入快照与提示词组装 | 类型快照、无人物视觉约束、主体连续性措辞 |
| `app/services/video_service.py` | 已有 | 视频执行前参数提取 | 科普最终视频提示词补充约束 |
| `app/services/narration_service.py` | 已有 | 连续旁白生成 | 科普解释式旁白规则 |
| `app/api/projects.py`、`app/store/project_store.py` | 已有 | 现有删除接口和目录安全检查 | 优先复用，只有测试证明确有缺口才修改 |
| `web/src/types.ts`、`web/src/api.ts` | 已有 | 页面数据、创建 API、请求错误处理 | 类型契约、删除包装、可识别 HTTP 状态的错误 |
| `web/src/hooks/useStudioWorkspace.ts` | 已有 | 创建、选择、轮询、操作状态 | 类型输入、独立删除操作和旧响应失效 |
| `web/src/components/ProjectNavigation.tsx` | 已有 | 创建表单与项目列表 | 类型选择、动态文案、类型标签、删除确认 |
| `web/src/components/ProjectOverview.tsx` | 已有 | 项目元信息和角色展示 | 类型展示、科普隐藏角色区 |
| `web/src/components/AssetWorkspace.tsx` | 已有 | 资产卡片与上传 | 科普隐藏角色资产、调整无角色文案 |
| `web/src/main.tsx`、`web/src/styles.css` | 已有 | 工作区接线、导航布局 | 删除回调、独立按钮布局与小屏可用性 |
| `tests/test_director_service.py`、`tests/test_projects.py`、`tests/test_narration_service.py`、`tests/test_video_service.py` | 已有 | 离线模型替身与 API/持久化回归 | 类型规则、兼容、删除回归 |
| `tests/test_project_type_policy.py`、`tests/test_frame_project_type.py` | 拟新增 | 当前未有独立类型/图片类型测试 | 关键结构约束及执行快照边界 |
| `README.md`、`docs/acceptance-runbook.md` | 已有 | 使用和验收说明 | 新建类型与永久删除说明 |

## 6. Existing Patterns to Reuse

- Pydantic `Literal` + 默认值：类型用 `story/science` 枚举，旧 JSON 无字段仍可读取；不更改现有资产 schemaVersion 的含义。
- 导演已有两次结构纠错尝试：科普返回角色时作为校验错误进入现有纠错流程，不另加无限生成重试。
- 资产槽派生和引用关联：科普保留场景资产及“其他参考”，不引入新资产种类；仍先上传参考图，再生成首尾帧。
- FrameJob 输入快照与签名：把类型纳入快照及签名，以记录执行约束，不读取可能变化的界面瞬时状态。
- 删除复用项目锁、路径校验、活动任务检测与现有接口，不重复建设删除服务。
- 前端复用 Ant Design Select、Tag、Popconfirm 和现有错误提示；删除沿用工作区版本控制机制。

## 7. Impact Analysis

- 直接影响：创建契约、项目持久化、两阶段导演与媒体提示词、旁白、项目导航与删除状态处理。
- 间接影响：项目概览、角色资产展示、失败重试/重启恢复、镜头编辑后的后续生成。
- 数据变化：增加默认 `story` 的 `projectType`；`directorRequest` 自动保存该字段。无需数据库迁移或环境变量。
- 接口变化：创建请求与项目响应增加类型；复用现有 DELETE 路由及返回体；前端错误对象增加状态码而保持 `Error.message` 兼容。
- 安全与成本：目录删除保留后端约束；科普校验复用有限纠错次数；类型选择和删除确认本身不触发模型请求。
- 性能：无新增轮询；删除成功先更新本地列表再刷新，继续复用当前版本号保护。
- 部署：先发布兼容新字段的后端，再发布前端；不修改 Google/MiniMax 认证、模型配置和现有付费提交策略。

## 8. Proposed Architecture

### 8.1 项目类型与创建体验

| 类型 | 表单文案 | 导演重点 | 角色与画面规则 | 旁白 |
|---|---|---|---|---|
| `story` 普通故事 | 故事梗概；人物、目标、冲突、结局 | 动机、冲突、故事推进 | 允许人物/拟人角色，保留当前资产流程 | 连贯故事讲述 |
| `science` 科普 | 科普主题与内容；现象、原理、演示过程、结论 | 提问 → 观察 → 机制 → 结论，可按镜头数拆分 | 无人物角色，使用对象、场景、过程演示 | 清晰解释机制和条件，避免虚构人物及编造数据 |

- 表单顶部新增必选类型，默认普通故事；切换类型只调整说明与占位文案，不清空用户已输入的文本或视觉风格。
- 保留 `sceneCount`、比例、用户风格；不强制科普改成某种画风。
- 导航和项目概览显示中文类型标签；旧项目回退普通故事。
- 类型本期只在创建时选择，不新增运行中类型修改接口。

### 8.2 科普生成规则

1. 大纲仍使用现有 JSON 结构，`characters` 必须为 `[]`；地点/场景可表示自然环境、实验空间、宏观/微观演示空间。复用 `dramaticGoal/conflict/turningPoint/outcome` 字段承载讲解目标、待解释问题、机制变化、结论，不要求科普创造戏剧冲突。
2. 分镜 `visibleCharacters` 必须为 `[]`；禁止将科学对象当成有性格、台词或动机的角色。首尾帧通过物理状态、位置、光线或过程阶段体现变化。
3. 对模型返回的角色字段做后端结构校验，非空即要求修正；两次仍失败则按现有导演失败状态展示，不能仅清空数组后把含人物的设计当成功。
4. 在 `_build_project` 和后台缓存大纲复用/重试边界再次执行类型校验；生成中 `Project.projectType`、`directorRequest.projectType` 与最终成品项目保持一致。科普资产槽只派生地点资产，不派生角色。
5. 普通故事保留原规则；科普镜头提示词改用“主体形态、比例、环境和过程连续”，避免固定拼接“人物身份、服装”等要求。
6. 首尾帧执行快照纳入类型；`FrameService._prompt` 在可编辑提示词之外追加科普无人物约束。视频在 `VideoService._run` 最终提交前按项目类型追加同样约束，覆盖手动编辑镜头提示词后的生成路径。
7. 科普旁白使用知识解释规则，来源仍是用户输入、大纲和分镜，不额外编造实验结论或统计数字；保留现有语速、时长对齐和连续语音流程。
8. `ProjectOverview` 隐藏科普角色折叠项；资产页隐藏角色卡片并提示上传场景/实验对象等参考图。后端保持角色字段为空，不能用界面隐藏代替数据约束。

### 8.3 项目删除

- 项目列表每项提供独立“删除”按钮，不能嵌套在负责选择项目的 Button 内；点击删除和确认不触发项目切换。
- 确认文案：“删除项目「项目名」？本地资产、首尾帧、视频、旁白和成片将永久删除，无法恢复。”明确这是本地删除。
- 活动状态项目显示禁用原因“项目仍有运行中的任务”；全局 `busy` 时也禁用删除，后端继续作最终判定。前端判定覆盖导演、queued/generating 图片、submitting/generating/downloading 视频。
- 成功删除当前项目：清空 `selected`、`selectedId`、`selectedIdRef`、加载状态，递增选择/数据版本，进入欢迎页；删除其他项目保留当前选择。
- 从项目列表与任务列表移除目标项目。删除请求开始及成功时使旧读取响应失效，避免轮询或先前选择请求把项目恢复；删除不通过要求返回 `Project` 的通用 `run()`。
- 删除操作纳入 `pendingActionsRef`/busy，失败时恢复按钮并显示后端原因；409 不移除项目。404 表示其他窗口可能已删除，提示后清理过期本地项并刷新。
- HTTP 错误需保留状态码供删除区分 404/409：在 `web/src/api.ts` 增加兼容 `Error` 的 HTTP 错误类型，现有调用仍读取 `.message`。
- 不强制删除执行中的任务，不在点击删除时隐式取消远端任务；只有现有后端检查允许时才永久移除目录。

## 9. Data / API Changes

### 项目类型

```json
POST /v1/projects
{
  "projectType": "science",
  "story": "介绍水循环中的蒸发、凝结与降水，通过自然环境变化展示，不出现人物。",
  "aspectRatio": "16:9",
  "style": "cinematic scientific visualization",
  "sceneCount": 3
}
```

- Python：`CreateProjectRequest.projectType`、`Project.projectType`，使用共享 `Literal["story", "science"]` 定义，默认 `story`。
- TypeScript：共享 `ProjectType` 类型，贯穿 `Project`、`CreateProjectInput` 和 API 创建参数，避免重复定义漂移。
- 非法枚举创建返回 FastAPI 422；省略字段创建普通故事。GET/列表返回明确类型。
- `directorRequest` 在新建时保存类型；旧快照缺字段回退故事。后台重试/恢复核对快照与 Project 类型，不允许静默改变已持久化类型。
- 科普大纲/分镜规则不满足时沿用现有有限纠错及失败展示；不把用户手动上传图片当作已通过视觉审核的保证。

### 项目删除

- 路由和响应不变：`DELETE /v1/projects/{project_id}` → 200 `{"projectId":"…","deleted":true}`。
- 404 项目不存在；409 存在活动任务；非法 ID/目录沿用当前 400 或路由层 404 行为。
- 删除影响仅目标项目目录；项目列表、文件访问和任务列表后续不再返回该项目。

## 10. Dependency Graph

```text
Task 1 类型契约 ─→ Task 2 导演策略 ─→ Task 3 图片/视频执行约束
       │                  └─────→ Task 4 旁白和类型展示
       └───────────────────────→ Task 5 创建表单
Task 6 删除状态与API ─→ Task 7 删除入口
Task 2 + Task 3 + Task 4 + Task 5 + Task 7 ─→ Task 8 联调验收与文档
```

## 11. Implementation Tasks

### Task 1: 建立类型契约与兼容默认值

- 目标：创建、读取、列表、原始请求快照统一携带项目类型。
- 涉及文件：`app/domain/models.py`、`app/services/director_service.py`、`web/src/types.ts`、`web/src/api.ts`、`web/src/hooks/useStudioWorkspace.ts`。
- 修改内容：增加两类枚举及默认值；start/build 项目显式传递类型，保留 directorRequest；同步前端创建输入和请求类型。
- 依赖：无
- 验收标准：新科普项目在生成中就能读到 science；普通创建和旧 JSON 缺字段均为 story；非法值返回 422。
- 验证方式：模型/Store 往返与创建 API 替身验证；前端构建检查。
- 风险与回滚：新增字段使用默认值兼容旧记录；回滚时不批量删除用户 JSON 中的类型信息。

### Task 2: 实现科普导演策略和结构校验

- 目标：科普大纲/分镜不会建立角色模型及角色资产。
- 涉及文件：拟新增 `app/services/project_type_policy.py`、`app/services/director_service.py`、`app/domain/models.py`、`tests/test_director_service.py`、拟新增 `tests/test_project_type_policy.py`。
- 修改内容：两阶段按类型调整指令；校验角色数组为空；复用两次纠错；缓存大纲重用与构建边界校验；科普资产派生保护。
- 依赖：Task 1。
- 验收标准：角色违约不会被静默接受；science 最终角色/镜头角色均空，仅保留场景及参考资产；故事模式保持原行为。
- 验证方式：模型替身覆盖首次正确、先错后对、持续违约、重试复用缓存和旧类型默认值。
- 风险与回滚：避免仅清空角色字段而遗留有人物的提示词；更改限于类型策略和生成边界。

### Task 3: 将科普约束落实到图片和视频执行

- 目标：编辑提示词、重复生成后仍携带科普无人物规则。
- 涉及文件：`app/services/frame_service.py`、`app/services/video_service.py`、`app/services/project_type_policy.py`（由 Task 2 新增）、`tests/test_video_service.py`、拟新增 `tests/test_frame_project_type.py`。
- 修改内容：生图快照/签名纳入类型；首尾帧和视频最终提示词追加统一科普约束；切换连续性措辞；快照缺类型回退 story。
- 依赖：Task 2。
- 验收标准：科普首帧、尾帧、单镜头及批量视频提交均包含无人物规则；故事不受影响；原有首尾帧参考图要求不变。
- 验证方式：模型替身捕获最终 prompt 和输入快照；覆盖手改提示词、成组生成、重复生成和旧快照兼容。
- 风险与回滚：不修改 SDK 重试、模型/认证配置；不改变已完成媒体。生成画面仍需人工验收。

### Task 4: 适配科普旁白及项目展示

- 目标：科普项目显示正确类型并使用解释式旁白，角色区域不出现。
- 涉及文件：`app/services/narration_service.py`、`tests/test_narration_service.py`、`web/src/components/ProjectOverview.tsx`、`web/src/components/AssetWorkspace.tsx`。
- 修改内容：旁白按类型选取规则；项目概览展示类型并隐藏科普角色区域；资产页使用科普参考素材说明，不展示角色卡片。
- 依赖：Task 2。
- 验收标准：科普旁白提示词无虚构人物要求；仍支持音频生成/时间对齐；科普页无“角色 0”等空角色区域。
- 验证方式：旁白模型替身验证与现有时间对齐回归；浏览器检查两种类型概览/资产页。
- 风险与回滚：保持旁白 JSON 和 MiniMax 接口不变；沿用已有资产上传行为。

### Task 5: 完成新建项目类型选择

- 目标：用户可在创建时选择科普或普通故事。
- 涉及文件：`web/src/components/ProjectNavigation.tsx`、`web/src/styles.css`。
- 修改内容：新增类型 Select 和类型说明；依据类型改变输入标签/示例；列表显示类型；切换时保留输入。
- 依赖：Task 1。
- 验收标准：默认故事、可选科普、提交值正确；关闭/成功创建后的表单重置行为一致；窄屏表单可使用。
- 验证方式：`web` 目录 `npm run build`；浏览器检查创建请求、切换类型、校验和提交失败保留输入。
- 风险与回滚：不自动覆盖用户风格或文本；旧项目类型标签回退故事。

### Task 6: 接入删除 API 与工作区状态清理

- 目标：项目删除能正确处理当前选择、轮询及任务列表。
- 涉及文件：`web/src/api.ts`、`web/src/hooks/useStudioWorkspace.ts`、`tests/test_projects.py`。
- 修改内容：新增删除包装和带状态码的错误；独立 remove 操作管理 busy、版本号、选择引用及本地列表；复用现有 DELETE，不新增重复路由。
- 依赖：无
- 验收标准：当前项目删除后清空；非当前删除不影响选择；旧响应不能重新显示已删除项；404 清理过期项，409 保留项目和原因。
- 验证方式：现有删除 API 回归；浏览器网络延迟下检查删除与轮询/切换并发；核对磁盘目标目录及其他项目。
- 风险与回滚：删除返回体不是 Project，不通过通用 run；不能清空其他项目的状态，失败不得先行移除真实项目。

### Task 7: 增加删除入口和确认交互

- 目标：桌面和移动项目列表均可发现并安全触发删除。
- 涉及文件：`web/src/components/ProjectNavigation.tsx`、`web/src/main.tsx`、`web/src/styles.css`。
- 修改内容：接入删除回调，列表项使用独立删除按钮和 Popconfirm；显示活动任务禁用原因；适配列表宽度与键盘操作。
- 依赖：Task 6。
- 验收标准：确认框显示项目名和永久本地删除范围；取消不发请求；点击删除不切换项目；活动任务不能删除；重复点击仅提交一次有效操作。
- 验证方式：前端构建与浏览器验收当前项目、非当前项目、末个项目、导演失败项目、视频失败项目、运行中项目及移动抽屉。
- 风险与回滚：复用后端真实活动判定；前端禁用不是删除授权依据；不加入强制删除选项。

### Task 8: 完成回归与使用文档

- 目标：验证类型到媒体提示词的完整链路和删除状态一致性。
- 涉及文件：`tests/test_director_service.py`、`tests/test_projects.py`、`README.md`、`docs/acceptance-runbook.md`。
- 修改内容：补齐跨边界用例和手工验收说明，记录科普参考素材要求、类型固定和删除范围。
- 依赖：Task 2, Task 3, Task 4, Task 5, Task 7。
- 验收标准：本节关键用例通过；类型在刷新/重试/重启后保留；普通故事流程无回归；未对已有项目进行迁移或删除。
- 验证方式：执行现有 pytest、provider 边界检查、前端构建；使用隔离测试项目完成浏览器验收，不默认发起付费模型请求。
- 风险与回滚：手工删除仅用临时测试项目；真实模型无人物效果作为独立人工验收记录，不用离线替身结果代替画面效果。

## 12. Test Plan

| 层级 | 场景 | 验证方法 | 预期 |
|---|---|---|---|
| 模型/Store/API | 类型传递、旧 JSON 和旧 directorRequest、非法值 | pytest + 模型替身 | story 默认兼容；science 持久化；非法值 422 |
| 导演 | science 角色违约、有限纠错、缓存大纲重试 | 捕获文本请求并注入结构化响应 | 两类角色字段为空；违约最终失败且可重试 |
| 媒体参数 | 首尾帧、单/批量视频、修改提示词、旧快照 | 捕获执行参数 | 科普约束始终附加；故事行为一致 |
| 旁白 | 故事/科普指令、语音参数和时间对齐 | 现有替身测试 | 知识解释式规则生效且时长机制无回归 |
| 删除 API | 全目录清理、404、无效 ID、符号链接、活动图片/视频/导演 | `tests/test_projects.py` | 仅目标可删除项目被移除；活动或非法目录拒绝 |
| 浏览器 | 选择类型、角色区域、列表标签、删除确认/取消 | 本地隔离项目 | 创建值与展示一致；取消无请求；失败可见 |
| 并发/浏览器 | 删除时慢轮询、切换选择、另一个窗口已删除、删除最后一个项目 | 网络限速与双窗口操作 | 不恢复已删项目、不清空其他项目、无永久加载状态 |
| 构建/回归 | Python、提供方边界、TS 与 Vite | `.venv/bin/python -m pytest -q`；`.venv/bin/python scripts/check_provider_boundaries.py`；`cd web` 后 `npm run build` | 通过且不调用远端付费生成 |

## 13. Risks / Edge Cases

| 风险或边界 | 影响 | 处理 |
|---|---|---|
| 科普原文带人物故事 | 模型仍可能按人物驱动 | 类型规则优先，用客观过程讲解；结构校验及执行约束，不把人物写入资产 |
| characters 为空但自然语言仍提到主持人 | 仅结构校验不足 | 两阶段明确无人物规则、最终 prompt 追加限制；人工验收画面，不依赖粗暴关键词黑名单 |
| 参考图有真人 | 模型复制人物 | 资产页说明和无人物生成约束；不承诺自动审图，用户替换素材后重生成 |
| 科普没有参考图 | 首尾帧仍不可生成 | 保持现有必须上传参考素材流程，使用场景/实验对象参考；不偷偷引入无参考图生成 |
| 已持久化的类型与请求快照不一致 | 重试变成其他内容类型 | 重试边界检查一致性并给出明确错误；不静默覆盖 |
| 删除项目仍有远端或本地活跃任务 | 写回/远端费用风险 | 复用现有状态/活动 job 和项目锁保护；不自动取消或强制删除 |
| 请求已失败但远端状态未知 | 删除本地记录不代表远端停止 | 确认说明本地删除范围；不声称能清理或退费远端任务 |
| 删除期间旧 GET 返回 | 已删项目重新显示 | 数据与选择版本失效、本地剔除、刷新闭环 |
| 多窗口同时删除 | UI 遇到 404 | 识别 HTTP 状态并清理过期本地项，不继续无限查询已删除选择 |
| 旁白/合成正在同步执行 | DELETE 等待项目锁 | 前端 busy 时禁用；锁内按最新状态执行，保留同步写操作串行化 |

## 14. Rollback / Compatibility

- 新字段有默认值，旧记录不需批量修改；旧类型缺失统一按普通故事。
- 首先交付后端类型读取、持久化和策略，再上线创建和展示页面。未部署完整科普策略前不开放 science 入口。
- 删除后端已存在，前端通过现有 API 接入；不改变成功/失败返回码与目录校验语义。
- 回滚前备份包含新类型的项目数据；回滚到不识别类型的旧版时，暂停科普项目的新生成，避免将其按故事模式继续制作。已生成本地媒体仍可保留读取。
- 永久删除不可通过代码回滚恢复；验证仅删除专用临时项目。

## 15. Implementation Order and Checkpoints

1. Task 1 → Task 2 → Task 3：类型和核心生成边界。
2. Task 4 → Task 5：旁白、展示与新建表单。
3. Task 6 → Task 7：删除状态闭环与入口。
4. Task 8：回归、浏览器验收、文档。

### Checkpoint 1: Task 1–3 完成后

- science 能持久化，角色/资产符合规则，最终媒体提示词保留约束；旧项目和普通故事均通过回归。

### Checkpoint 2: Task 4–5 完成后

- 新建两种类型均可走通；科普概览/资产无角色区，旁白按科普规则生成；前端构建通过。

### Checkpoint 3: Task 6–7 完成后

- 删除当前/非当前/最后一个临时项目正确；409 不丢状态；慢请求和跨窗口删除不会恢复已删除项。

### Checkpoint 4: Task 8 完成后

- 回归、边界检查、构建与浏览器验收完成，文档描述与最终行为一致；真实模型效果未验收时明确记录限制。

## 16. Approval Gate

- Status: Code implementation complete; manual browser acceptance pending
- Blocking decisions: 无；按两类项目、科普无人物、永久本地删除和活动任务拒绝删除的假设实施。
- Application code changed: Yes
- 方案已落实到代码；自动化回归与构建通过，手工浏览器验收尚待进行。
