# 资产管理与首尾帧生成：落地开发需求及技术方案

日期：2026-10-20。状态：待评审。本次只编写方案。

## 1. Requirement Understanding

### 目标与流程

补齐项目内的参考资产管理，让用户上传一次人物、场景参考图，即可在相关镜头中复用，并直接生成首尾帧。

```text
创建项目 → 导演规划 → 上传资产 → 自动关联镜头参考图
         → 调整首/尾帧提示词 → 生成首尾帧 → 生成镜头视频 → 旁白及成片
```

### P0 功能范围

| 编号 | 需求 | 用户可见行为 |
|---|---|---|
| R1 | 增加资产 Tab | 导航为「项目概览 / 资产 / 分镜 / 连续旁白 / 成片」；资产属于当前项目 |
| R2 | 资产只通过上传产生 | 支持角色、场景、其他参考图；预列导演规划中的角色和场景上传位；支持替换、删除；不提供资产 AI 生成按钮 |
| R3 | 资产自动关联 | 上传到角色/场景位置后，相关镜头的首帧、尾帧参考区自动显示缩略图与名称 |
| R4 | 首尾帧可直接生成 | 单独生成首帧、单独生成尾帧，以及「一键生成本镜头首尾帧」；调用 Google 图片模型 |
| R5 | 支持重复生成 | 同一位置可重新生成；成功后使用新图，失败保留原可用图片；历史成功版本可预览、重新选用 |
| R6 | 提示词可调整 | 首帧、尾帧分别编辑和保存提示词；默认使用现有导演生成的 firstFramePrompt、lastFramePrompt |
| R7 | 与视频生成衔接 | 实际首尾帧均就绪后才可生成视频；图片生成不会自动提交视频 |
| R8 | 明确状态与错误 | 首帧、尾帧分别显示待生成、排队中、生成中、生成失败；错误后可重试、删除失败记录 |

### 成功标准

- 同一角色出现在多个镜头时，只上传一次角色图，这些镜头的首、尾帧参考区均自动出现该图。
- 上传场景参考图只影响对应场景的镜头；未关联的资产不会被发送给模型。
- 页面刷新、切换项目后，资产、提示词、生成状态、选中图片均能恢复。
- 一键生成两帧时，部分失败可单独重试；重新生成失败不丢失原图。
- 图片请求继续走 Google Cloud Agent Platform，并使用当前 Cloud 项目与 API Key。

不纳入本期：跨项目资产库、自动画角色/场景资产、训练角色模型、自动识别人脸或图片语义、全项目一键生成全部图片、独立分布式任务系统。现有手动上传首尾帧仍保留为可选操作。

## 2. Assumptions and Open Questions

### Assumptions

- 「资产」指人物外观、场景和其他参考图片；「首尾帧」是基于参考图生成的镜头画面。两者分别展示，上传资产不会直接变成最终首尾帧。
- 角色与场景是自动关联的主要依据：已有 `visibleCharacters`、`locationName`；上传时选择对应实体，无需靠文件名猜测。
- 每个角色/场景位置有一张当前参考图；替换上传更新该位置。不同造型可新增「其他参考」，再指定适用镜头。
- 首尾帧默认引用同一组镜头资产；允许分别改为手动选择，支持某角色只在首帧或尾帧出现。
- 首版以当前本地、单后端进程部署为基准；进程内锁与限流不能宣称支持多 worker。
- 本镜头两帧一键生成按首帧、尾帧顺序执行；尾帧额外参考本次成功首帧以提高连续性。

### Open Questions

无必须由用户先回答的架构问题。以上默认行为纳入方案评审；目标 Cloud 项目对图片模型的权限、配额和实际赠金抵扣仍需开发联调验证。

## 3. Repository Reconnaissance

- 规则：本轮用户提供的 AGENTS.md 指令；`coding-plan` 技能及其计划契约、模板。项目目录扫描未发现独立 AGENTS.md / CLAUDE.md 文件。
- 已查阅：`dev.md`、`docs/agent-platform-api-key-development.md`；下文所列后端、前端、存储及相关测试。
- 工程：FastAPI + Pydantic；本地 JSON/文件存储；React + Ant Design + Vite；Python `google-genai>=2.29.0`。
- 现有检查命令：`.venv/bin/python -m pytest -q`、`.venv/bin/python scripts/check_provider_boundaries.py`、`cd web && npm run build`，来自 `dev.md`、`pyproject.toml`、`web/package.json`。
- 前端当前没有独立测试脚本；交互验收先用浏览器，构建负责类型检查。
- 工作区已有 Google Agent Platform 接入、失败视频删除等未提交修改；实施时保留并基于这些修改继续，不覆盖或回退。
- 取证边界：已阅读源码并查询官方文档；本次未调用真实生成接口，未读取或输出密钥。

## 4. Existing Architecture

以下为已观察到的行为：

- `app/services/director_service.py::DirectorService._build_project` 已保存角色、场景信息、首尾帧描述和图像提示词，没有资产实体和生图调用。
- `app/domain/models.py::Shot` 通过 `uploads.firstFrame/lastFrame` 保存最终用于视频的图片路径；`UpdateShotRequest` 目前不能单独修改首尾帧提示词。
- `app/api/projects.py::upload_frame` 接收原始图片 body，保存上传帧，并清除镜头视频与成片引用；文件接口当前只允许 frames/videos/audio/final。
- `app/services/video_service.py::VideoService._run` 读取上述两个路径后提交视频；`app/main.py` 只恢复导演/视频任务。
- `app/store/project_store.py::ProjectStore` 使用项目锁与临时 JSON 原子替换，但锁只在当前进程有效。
- `web/src/components/ShotWorkspace.tsx` 提供首尾帧上传、预览和视频按钮；图像提示词当前只作为导演设计文字显示。
- `web/src/main.tsx` 管理四个 Tab；`useStudioWorkspace.ts` 每三秒刷新项目，并用版本号防止旧请求覆盖新选择。

推断：可以在现有模型和存储上增量扩展，无需引入数据库。不能仅新增前端按钮，后台任务状态、参考图绑定和视频失效规则需要同时补齐。

## 5. Relevant Files

路径均相对项目根目录；标为「新增」的文件目前不存在。

| 文件 | 状态 | 责任与改动 |
|---|---|---|
| `app/domain/models.py` | 现有 | 资产、首尾帧、版本、任务和请求模型 |
| `app/store/project_store.py` | 现有 | 新旧数据兼容、资产/图片文件存储 |
| `app/services/director_service.py` | 现有 | 导演完成后创建角色/场景资产位置 |
| `app/services/asset_service.py` | 新增 | 实体目录、上传资产、确定性引用解析 |
| `app/services/frame_service.py` | 新增 | 生图任务、版本选择、结果发布、依赖失效 |
| `app/clients/google_image.py` | 新增 | 带参考图的 Google 生图适配 |
| `app/clients/google_client.py` | 现有 | 复用 Cloud 客户端工厂及错误脱敏 |
| `app/config.py`、`.env.example` | 现有 | 图片模型、超时和并发配置 |
| `app/api/project_assets.py` | 新增 | 资产及首尾帧 API，避免继续扩张 projects.py |
| `app/api/projects.py`、`app/main.py` | 现有 | 文件白名单、写入互斥、路由注册、重启处理 |
| `app/services/video_service.py` | 现有 | 验证两帧可用与图像任务互斥 |
| `web/src/types.ts`、`web/src/api.ts` | 现有 | 资产与帧任务类型、请求封装 |
| `web/src/hooks/useStudioWorkspace.ts` | 现有 | 资产和帧操作、刷新、错误回传 |
| `web/src/components/AssetWorkspace.tsx` | 新增 | 资产列表、上传、替换、删除、引用范围 |
| `web/src/components/FrameGenerationPanel.tsx` | 新增 | 两帧参考区、提示词、生成和历史版本 |
| `web/src/components/ShotWorkspace.tsx`、`web/src/main.tsx`、`web/src/styles.css` | 现有 | 集成新 Tab 与镜头面板、响应式布局 |
| `tests/test_assets.py`、`tests/test_frame_service.py`、`tests/test_google_image.py` | 新增 | 绑定、任务发布与 Google 边界测试 |
| `tests/test_projects.py`、`tests/test_video_service.py`、`tests/test_google_client.py` | 现有 | 上传、互斥、旧数据和端点回归 |
| `pyproject.toml`、`dev.md`、`docs/acceptance-runbook.md` | 现有 | 图片解码依赖与操作、验收说明 |

## 6. Existing Patterns to Reuse

- 沿用 `ProjectStore.lock/save`：短锁读取快照、网络调用在锁外完成、重新读取最新项目后合并结果；禁止用调用前的整个 Project 覆盖新数据。
- 沿用 `build_google_client/safe_google_error`：图片客户端复用 Cloud 项目、Key、global 区域与脱敏。
- 沿用 `upload_frame` 的原始图片 body 上传方式；新增图片解码校验与统一存储帮助函数，而不是再引入一套 multipart 流程。
- 沿用 `useStudioWorkspace.run/refresh` 的错误与项目切换保护；新增局部任务状态，不能让异步生图长期锁死整个工作区。
- `VideoService` 的任务登记可作参考，但图片 GenerateContent 没有可恢复的远端任务 ID，不直接套用视频恢复逻辑。

## 7. Impact Analysis

- 数据：增加项目内资产、帧任务与成功版本；保留现有上传路径契约。
- API：增加资产和帧配置/生成接口；现有视频/手动上传接口补图像任务互斥。
- 前端：新增资产 Tab；分镜下新增参考资产与生成图两层区域，避免把参考图误认为首尾帧已就绪。
- 配置：增加独立图片模型，不复用文字/视频模型 ID；增加 Pillow 做实际图片解码、格式和像素限制校验。
- 安全：后端读取 Key；图片从本项目安全路径读取并作为字节发送，不接受任意 URL/路径。
- 性能：图片请求异步执行；复用三秒轮询；图片只返回 URL 与元数据，Project JSON 中不存 Base64。
- 运行：项目删除必须覆盖图片任务保护；重启中断的生图标失败，不自动再次付费生成。

## 8. Proposed Architecture

### 8.1 资产 Tab

- 显示角色、场景、其他参考三个分组；角色和场景来自导演大纲，卡片展示名称、描述、当前图片、已关联镜头数量。
- 未上传时显示「上传角色参考图」「上传场景参考图」。其他参考通过「新增参考」填写名称并指定镜头范围。
- PNG/JPEG/WebP，单图最大 6,000,000 字节；实际解码并限制 40 MP。拒绝损坏、动画与不匹配格式；清除元数据后保存规范图片，并再次校验大小。
- 每个位置只有一张当前图片；替换创建新文件版本。删除清空图片及其自动引用，保留角色/场景位置便于重传；其他参考可删除整条记录。
- 资产替换/删除更新引用与「参考已更新」提示，不自动触发生图或清空已生成图片/视频。生成任务使用中的资产禁止替换/删除，返回 409。

### 8.2 自动关联规则

1. 对角色/场景名称做 Unicode NFKC、去首尾空白与大小写归一，再进行**完整名称匹配**；不使用文件名、子串或额外模型猜测。
2. 角色资产关联 `shot.visibleCharacters`；场景资产关联 `shot.locationName`。实体 ID 在项目内稳定，上传不要求手动逐镜头绑定。
3. 其他参考依据指定镜头 ID 列表关联；首帧、尾帧默认使用镜头自动引用集合。
4. 每个帧位置可切换为「手动参考」并保存明确 assetIds；可恢复自动模式。手动模式不再自动追加新上传资产。
5. 缺图的角色/场景显示名称占位和「去资产页上传」，不伪造参考图。引用名称在大纲中不存在时显示未匹配，并允许用户手动选图或创建其他参考。
6. 生成前列出实际发送的图。匹配到但未上传的必需资产阻止生成；无任何可用参考时也阻止。手动模式可以明确排除当前帧无需出现的实体。
7. 最多 13 张资产参考；为尾帧附加首帧保留一个输入位置。超限需手动精简，不静默截断。

### 8.3 分镜中的首尾帧面板

每帧位置由上到下：参考资产缩略图及名称 → 可编辑提示词 → 当前生成图 → 状态/错误 → 生成、重新生成、历史版本、手动上传。

- 首帧和尾帧提示词独立，默认导演给定值；支持保存、恢复导演默认值；空白或超过 8000 字不提交。
- 「生成」会先保存当前提示词和引用，再提交任务；「保存提示词」本身不调用模型。
- 有原图时仍可重新生成；任务期间保留可见旧图，成功后自动选用新版本；失败显示「生成失败」与错误，并保留旧图。
- 简单历史抽屉展示成功版本缩略图、时间、来源和提示词，支持选用。首版不提供历史批量管理。
- 单帧重生成相互独立。尾帧可参考当前首帧；首帧更新后，已有尾帧标「首帧已更新，可重新生成尾帧」，不自动覆盖它。
- 「一键生成首尾帧」先提示将生成 2 张；顺序生成，首帧失败则尾帧标失败并说明依赖失败。尾帧失败时保留首帧成功结果。
- 状态分开表达：当前图片是否可用、最近一次生成是否失败。重生成失败且旧图可用时，仍可明确选择使用旧图生成视频。
- 视频生成期间禁止本镜头的帧生成、选版本、手动换帧；帧任务期间禁止本镜头的视频生成，其他镜头仍可操作。

### 8.4 Google 图片模型与边界

- 默认新增 `GOOGLE_IMAGE_MODEL=gemini-3.1-flash-image`，`GOOGLE_IMAGE_RESOLUTION=1K`，`GOOGLE_IMAGE_TIMEOUT_SECONDS=180`，`GOOGLE_IMAGE_MAX_CONCURRENCY=2`。独立配置允许以后换模型。
- 使用现有 Cloud 客户端工厂，调用 `client.models.generate_content`；传入文本和本地参考图片字节，请求 IMAGE/TEXT 输出及项目画面比例。不得调用视频 Interactions 接口生成图片。
- 官方模型卡确认该模型支持图像输入输出、global、9:16/16:9、1K，最多 14 张输入图、inline 单文件 7 MB；上述 6 MB / 13 张是本项目更保守的限制。[模型卡](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-flash-image)
- 图像能力与调用方式依据 [Cloud 图片生成文档](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/image-generation) 和 [图片编辑文档](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/gemini-edit-images)。复用 [Cloud API Key 认证](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/api-keys?usertype=standard)，实际项目可用性和赠金抵扣需联调确认。
- 提示词组装：项目风格、帧描述、用户可编辑提示词、连续性约束、每张参考图的实体标签及对应图片。尾帧追加选定首帧及「保持身份、服装和场景连续」说明。
- 遍历候选内容的图片部分；只接受解码成功的图片结果，忽略 thought 中间图。没有最终图片、安全拦截、仅返回文字均标失败，不伪造成功；多张最终图只采用第一张并记录数量。
- 不自动重试可能已执行的图片生成请求；限制 SDK 自动重试。超时标明结果未知，由用户手动重新生成，避免透明重复付费。

### 8.5 任务、安全发布与失效规则

- API 短锁内校验、登记 jobId、冻结输入快照后立即返回 202；后台执行网络调用。每个帧位置最多一个 queued/generating 任务，同镜头两帧由任务服务协调。
- 客户端提交 requestId；同一 requestId 与相同输入返回已有任务，不重复提交，输入不一致返回 409；其他 requestId 遇到同一帧执行中也返回 409。
- worker 在网络调用前读取并校验引用字节；资产和提示词写入在相关任务期间返回 409，避免请求输入被替换。
- 全进程最多并行 2 个图片调用；排队任务状态持久化。首尾成组提交在一个锁内登记，UI 重复点击不能登记第二组。
- 成组提交时先冻结两帧的配置与资产快照；尾帧依赖首帧任务 ID。首帧成功后，再将该成功版本写入尾帧输入快照并发起调用，不提前引用旧首帧。
- 结果写入独立 jobId 临时文件，解码校验后原子更名。发布时重新读取最新项目，核对 jobId 和输入快照签名；过期回调不能覆盖当前选择。
- 只有「选中最终帧发生变化」（生成成功自动选用、选择历史、手动上传）才清除该镜头 video 引用和 project.finalVideoPath；保留其他镜头、音频及历史图片。
- 改提示词/参考、提交任务、生成失败不会清除现有视频；输入变化标记 stale。生成期间暂时禁用视频提交，避免使用正在变更的帧。
- 项目删除遇到排队/执行图片任务返回 409；删除失败图片任务只清除错误记录。重启将 queued/generating 标失败，保留旧成功图，不自动重新提交。
- 单进程部署限制写进 dev.md；若未来多 worker，需持久化任务队列和跨进程锁后再开放。

## 9. Data / API Changes

### 数据模型（拟新增）

| 模型/字段 | 核心字段与约束 |
|---|---|
| `Project.schemaVersion` | 新版本为 2；无字段的旧项目按版本 1 兼容 |
| `Project.assets: Asset[]` | `id/kind/name/description/entityName/scopeShotIds/image/revision`；kind 为 character/location/reference；image 可空 |
| `Asset.image` | `imageId/path/mimeType/size/width/height`；每次上传新文件名，避免缓存和覆盖在用字节 |
| `Shot.frames.first/last: FrameSlot` | `referenceMode/assetIds/selectedVersionId/versions/job`；auto 模式引用由后端解析，不保存一份易过期副本 |
| `Shot.firstFramePrompt/lastFramePrompt` | 沿用现有字段作为当前草稿；新增 `directorFirstFramePrompt/directorLastFramePrompt` 保存恢复默认值 |
| `FrameVersion` | `id/path/source/generatedAt/model/promptSnapshot/inputSignature/referenceSnapshots/firstFrameVersionId`；source 为 generated/upload/legacy |
| `FrameJob` | `id/requestId/groupId/status/errorMessage/createdAt/startedAt/finishedAt/inputSnapshot`；状态 queued/generating/complete/failed |
| `inputSnapshot` | 保存有效提示词、风格、比例、模型、资产 ID/图片版本/名称和尾帧参考的首帧版本；不存 Key 或 Base64 |
| `Shot.uploads` | 兼容现有视频接口的投影，由 selectedVersionId 推导；新逻辑不直接把它当第二个独立状态源 |
| 帧响应派生数据 | `resolvedAssets/missingReferences/stale/hasUsableImage`；后端统一计算，前端不再实现另一套自动匹配算法 |

新项目导演完成时创建空资产目录。旧项目加载时纯内存升级：稳定生成实体 ID；现有上传帧导入 legacy 版本，不调用生图、不丢视频；首次合法写操作再保存新格式。`get/list` 必须使用同一迁移函数，避免项目从列表消失；schemaVersion 区分旧格式与新版刻意清空的帧。

### API（均位于 `/v1/projects/{project_id}`）

| 方法 / 路径 | 行为 |
|---|---|
| `POST /assets` | 新建其他参考元数据：name、description、scopeShotIds；角色/场景位置自动提供 |
| `PUT /assets/{asset_id}` | 修改其他参考名称、描述、镜头范围；角色/场景身份只读 |
| `POST /assets/{asset_id}/image` | 原始图片 body 上传/替换，Content-Type 指定格式；返回最新 Project |
| `DELETE /assets/{asset_id}` | 删除当前图片，其他参考同时删记录；返回最新 Project |
| `PUT /shots/{shot_id}/frames/{role}/config` | 保存 prompt、referenceMode、assetIds；可指定 restoreDefaultPrompt；不清视频 |
| `POST /shots/{shot_id}/frames/{role}/generate` | requestId；冻结已保存配置，创建单帧任务，202 返回最新 Project |
| `POST /shots/{shot_id}/generate-frames` | requestId；一次登记首尾任务，202 返回最新 Project |
| `POST /shots/{shot_id}/frames/{role}/versions/{version_id}/select` | 选用当前镜头、当前位置的成功版本，返回 Project |
| `DELETE /shots/{shot_id}/frames/{role}/failed-job` | 仅清理 failed 状态的最新任务，保留成功图片、提示词和参考 |
| 现有 `POST /shots/{shot_id}/frames/{role}` | 保留手动上传；纳入 FrameVersion 与统一选择/失效服务 |
| 现有 `GET /files/{relative_path}` | 白名单增加 assets；所有新文件路径必须限制在本项目目录 |
| 现有 `GET /{project_id}` | 包含资产、帧与任务状态，沿用轮询，无须新增实时连接 |

验证：role 仅 first/last；prompt 去空白后 1–8000 字；assetIds 去重、只限本项目有效图片；shotIds 必须存在；路径、数量和缺图均在云调用前校验。400/422 表示输入错误，404 表示资源不存在，409 表示任务冲突，413 表示体积超限；后台云端错误写入帧任务并返回脱敏文案。图片解码在锁外完成，提交前重新校验关联状态。

文件布局：`assets/{asset_id}/{image_id}.{ext}`；`frames/{shot_id}/{role}/{version_id}.{ext}`；临时文件不通过文件 API 暴露。删除或替换资产时，仅删除不再被成功版本/任务快照引用的旧文件，保留历史所需图片；整项目删除统一清理。

## 10. Dependency Graph

```text
Task 1 → Task 2 → Task 4 → Task 5
Task 1 → Task 3 → Task 4
Task 1 → Task 6
Task 2 + Task 6 → Task 7
Task 4 + Task 7 → Task 8
Task 5 + Task 8 → Task 9 → Task 10
```

## 11. Implementation Tasks

### Task 1: 数据契约与旧项目兼容

- 目标：建立单一帧状态源，旧项目无需重新创建。
- 涉及文件：`app/domain/models.py`、`app/store/project_store.py`、`web/src/types.ts`、`tests/test_projects.py`。
- 修改内容：新增资产/帧/任务/版本模型；统一读取迁移；uploads 投影；现有图片导入 legacy 版本。
- 依赖：无
- 验收标准：旧项目 get/list/save 往返不丢帧、视频和旁白；新版清空状态不会被旧字段复活。
- 验证方式：pytest 模型与存储回归；类型构建。
- 风险与回滚：新增字段默认兼容；升级前备份项目 JSON，回退优先使用备份。

### Task 2: 上传资产与自动引用

- 目标：上传一次，所有匹配镜头均能引用。
- 涉及文件：新增 `app/services/asset_service.py`、新增 `app/api/project_assets.py`、`app/services/director_service.py`、`pyproject.toml`、新增 `tests/test_assets.py`。
- 修改内容：实体上传位、实际解码、稳定 ID、引用解析、替换/删除保护；增加 Pillow；提供派生参考和缺图信息。
- 依赖：Task 1。
- 验收标准：同角色多镜头自动引用；场景不串用；自定义参考只影响指定镜头；无任意 URL/路径入口。
- 验证方式：pytest 覆盖完整匹配、空图、替换、删除、损坏图与路径边界。
- 风险与回滚：名称不一致显示缺引用并允许手动选择；独立资产 API 可停用。

### Task 3: Cloud 图片客户端

- 目标：通过现有 Cloud Key 调用带参考图的 Google 图片生成。
- 涉及文件：新增 `app/clients/google_image.py`、`app/config.py`、`.env.example`、`tests/test_google_client.py`、新增 `tests/test_google_image.py`。
- 修改内容：独立模型配置、请求构造、图片结果解析/校验、脱敏、超时与禁止透明重复提交。
- 依赖：Task 1。
- 验收标准：离线 HTTP 拦截证实主机为 aiplatform.googleapis.com，路径带目标项目，Key 在 Header；正确传入图片和比例。
- 验证方式：真实 SDK 加模拟 HTTP；覆盖仅文本、安全拦截、空候选、thought 图片、超时和错误脱敏。
- 风险与回滚：账号可用性未由离线测试保证；模型 ID 可配置，禁止自动换端点。

### Task 4: 首尾帧后台生成服务

- 目标：完成单帧和成组生成，并可靠保留成功结果。
- 涉及文件：新增 `app/services/frame_service.py`、`app/api/project_assets.py`、`app/store/project_store.py`、新增 `tests/test_frame_service.py`。
- 修改内容：持久任务、requestId 幂等、短锁快照、并发限制、版本文件、成组顺序和原子发布；统一选择与 stale 计算。
- 依赖：Task 2, Task 3。
- 验收标准：重复点击只提交一次；尾帧使用该组成功首帧；部分失败可单独重试；过期结果不能覆盖新状态。
- 验证方式：可控假客户端覆盖并发、迟到回调、首帧失败、尾帧失败、重生成失败保留旧图。
- 风险与回滚：任务不支持跨进程；停止新任务后可继续用已有帧和视频。

### Task 5: 视频互斥、上传兼容与重启处理

- 目标：帧切换正确影响视频，重启后无永久生成中任务。
- 涉及文件：`app/api/projects.py`、`app/services/video_service.py`、`app/main.py`、`tests/test_projects.py`、`tests/test_video_service.py`。
- 修改内容：路由注册、assets 文件白名单、任务互斥、项目删除保护；手动上传转为版本；启动把中断图片任务标失败。
- 依赖：Task 4。
- 验收标准：成功选用新图才清本镜头视频和成片；提示词修改/失败不清视频；重启不重新付费提交。
- 验证方式：pytest 上传、删除、启动恢复、视频生成边界回归。
- 风险与回滚：集中使用帧服务，防止旧接口绕过状态；保留历史媒体以支持恢复。

### Task 6: 前端接口与局部操作状态

- 目标：前端可操作新接口，异步任务不长期锁死全站。
- 涉及文件：`web/src/api.ts`、`web/src/hooks/useStudioWorkspace.ts`、`web/src/types.ts`。
- 修改内容：资产/帧操作、requestId 生命周期、异步提交与轮询；按镜头/帧维护短请求 busy，轮询期间保留未保存草稿。
- 依赖：Task 1。
- 验收标准：切换项目不会被旧响应覆盖；重试 HTTP 沿用 requestId，用户主动重新生成使用新 requestId。
- 验证方式：npm run build；浏览器模拟慢请求、切换项目与草稿编辑。
- 风险与回滚：复用现有版本号保护；新增操作可独立撤除。

### Task 7: 资产 Tab

- 目标：交付完整资产上传与引用范围界面。
- 涉及文件：新增 `web/src/components/AssetWorkspace.tsx`、`web/src/main.tsx`、`web/src/styles.css`。
- 修改内容：角色/场景上传位、其他参考表单、图片预览、替换/删除、关联镜头提示和空态。
- 依赖：Task 2, Task 6。
- 验收标准：新 Tab 位于概览之后；上传后自动出现在对应镜头参考区；不出现 AI 生成资产入口。
- 验证方式：使用 Task 2 接口进行浏览器上传/替换/删除与移动端检查。
- 风险与回滚：上传只到当前项目；组件可从 Tab 移除，不损害现有数据。

### Task 8: 分镜首尾帧生成界面

- 目标：在镜头内完成参考选择、提示词编辑和重复生成。
- 涉及文件：新增 `web/src/components/FrameGenerationPanel.tsx`、`web/src/components/ShotWorkspace.tsx`、`web/src/main.tsx`、`web/src/styles.css`。
- 修改内容：首尾参考区、提示词保存/恢复、单帧/成组按钮、独立状态、失败删除、历史选用、旧图保留。
- 依赖：Task 4, Task 7。
- 验收标准：参考与结果清楚分区；可分别改提示词；一键生成两帧；失败可重试；旧图可继续选用。
- 验证方式：浏览器分别覆盖首次生成、重复生成、部分失败、历史切换、手动上传及窄屏操作。
- 风险与回滚：不改旁白和成片布局；可回退到手动上传操作。

### Task 9: 集成验收与故障回归

- 目标：验证资产到帧再到视频的整条流程。
- 涉及文件：`tests/test_assets.py`、`tests/test_frame_service.py`、`tests/test_google_image.py`、`tests/test_projects.py`、`docs/acceptance-runbook.md`。
- 修改内容：补跨服务边界场景；执行最小真实 Cloud 图片联调并记录模型、项目、结果，不记录 Key。
- 依赖：Task 5, Task 8。
- 验收标准：下节正常、错误、兼容与并发场景通过；真实图像能作为首尾帧进入现有视频流程。
- 验证方式：现有 pytest、服务商边界检查、前端构建和浏览器；真实生成属于执行期验收，记录实际调用情况。
- 风险与回滚：真实调用会消耗 Cloud 额度；先验证单帧成功，再验证首尾成组，不批量消耗。

### Task 10: 操作说明与交付

- 目标：用户能按页面顺序完成制作。
- 涉及文件：`dev.md`、`README.md`、`docs/acceptance-runbook.md`、本方案文档。
- 修改内容：补图片配置、资产上传规则、生成流程、失败重试、历史选择及单进程限制；记录实施结果与差异。
- 依赖：Task 9。
- 验收标准：文档与实际按钮及接口一致；说明资产参考图与视频首尾帧的区别。
- 验证方式：按操作说明完成一次上传资产、生成首尾帧、生成视频的流程。
- 风险与回滚：文档随功能交付更新，旧手动上传流程保留说明。

## 12. Test Plan

| 层级 | 场景 | 预期 |
|---|---|---|
| 模型/存储 | 旧项目、无资产、已有手动帧；保存往返 | 不丢数据、不重复迁移、不触发云调用 |
| 资产单元/API | 同角色跨镜头、多个场景、同名归一冲突、手动引用 | 自动引用确定且不串项目；冲突明确报错 |
| 上传与文件 | 过大、损坏、伪 MIME、动画、超大像素、符号链接、路径穿越 | 在上传或读取边界拒绝；临时文件不可访问 |
| Google 客户端 | 实际 SDK 的模拟 HTTP、纯文字输出、安全拦截、多个候选 | Cloud 项目路径/Key 正确；只采用合法最终图片 |
| 任务单元 | 幂等、并发、组内依赖、过期回调、重启 | 无重复登记，无旧结果覆盖，无透明重提 |
| 依赖回归 | 改提示词/参考、生成失败、成功换图、选历史 | 前三项保留视频；换选中图才清本镜头视频及成片 |
| API 互斥 | 帧与视频并行、替换正在使用资产、删项目、非法版本选择 | 返回 409/404；不能跨镜头选版本 |
| 浏览器 | 上传后自动出现、草稿编辑期间轮询、慢请求切项目 | 状态正确；草稿不被刷新覆盖；响应不串项目 |
| 浏览器 | 部分失败、重复生成、旧图选用、移动端 | 状态可理解、可重试、图片不丢失、按钮可用 |
| 真实集成 | 当前 Cloud 项目单帧→首尾→镜头视频 | 真实图片落盘、两帧用于视频；记录赠金抵扣核查结果 |

执行命令沿用项目现有配置：`.venv/bin/python -m pytest -q`、`.venv/bin/python scripts/check_provider_boundaries.py`、`cd web && npm run build`。本次规划不执行应用测试或真实生成。

## 13. Risks / Edge Cases

| 风险/边界 | 处理 |
|---|---|
| 大纲角色名与镜头引用不同 | 展示缺失匹配；手动参考修正，不依靠语义猜测静默关联 |
| 角色只在一端出现 | 首、尾帧各自可手动排除/选择参考，提示词同时说明该角色是否入画 |
| 资产不足、参考超限 | 在提交前明确列出缺图/数量；不静默跳过必要资产 |
| 相同角色多套造型 | 自动位置保留一张主参考；其他造型作为其他参考，指定镜头或手动选择 |
| 参考一致性无法完全保证 | 在 UI 支持预览和重生成；模型参考是约束输入，不能承诺身份绝对一致 |
| 重生成失败但旧图可用 | 同时展示失败与旧图可用，保留旧选中版本和视频 |
| 首帧成功、尾帧失败 | 保留首帧，尾帧单独重试；首帧失败时不发起该组尾帧调用 |
| 新首帧与旧尾帧不再连续 | 标记尾帧参考已变更，提醒重生成；不自动收费生成 |
| 生成中服务重启/超时 | 标失败或结果未知，不自动重发；旧图可用，用户可手动重试 |
| 文件发布后 JSON 保存失败 | 临时文件与版本文件保持可识别；启动清理无引用临时文件，未提交版本不得成为当前图片 |
| 旧媒体缓存 | 所有新图片使用版本文件名；新版本 URL 改变 |
| 资产历史增长 | 只保留被资产当前图/帧版本/任务快照引用的文件；整项目删除回收，不在本期自动删成功历史 |
| 多 worker 竞态 | 本期明确单进程；上线多进程前另做共享队列与锁 |
| Cloud 模型权限、赠金限制 | 以目标项目实际调用及账单核查为准，不把配置就绪等同于免费可用 |

## 14. Rollback / Compatibility

- 数据升级前备份 `downloads/projects/`。纯新增模型默认值兼容现有项目；新选中帧继续投影到 uploads，维持视频调用契约。
- 旧 `update_shot`、`upload_frame` 需统一通过帧服务维护模型，不能仅改 uploads 而遗留 selectedVersionId。
- 灰度顺序：旧数据读写 → 资产上传/自动引用 → 单帧模型联调 → 成组与重新生成 → 前端完整开放。
- 回退先停止创建新任务并等待在途任务结束；移除新入口后仍能读取已有投影帧。需要退回旧后端版本时恢复备份，避免旧模型保存时丢弃新字段。
- 不覆盖/删除本次实施前已有媒体；回滚不要求重新调用云服务。

## 15. Implementation Order and Checkpoints

按 Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10 实施。依赖图允许提前推进前端契约，但真实端到端验收须后端就绪。

### Checkpoint 1: Task 1–3 后

旧项目无损加载；上传资产可自动解析为镜头参考；Google 图片 SDK 请求的项目与认证经离线验证。

### Checkpoint 2: Task 4–5 后

单帧/成组生成、失败保留旧图、历史选用、互斥及重启处理通过后端验收。

### Checkpoint 3: Task 6–8 后

浏览器完成「资产 Tab 上传 → 分镜显示参考 → 改提示词 → 生成/重生成 → 选用历史」，切换项目和轮询不覆盖草稿。

## 16. 实施状态

截至 2026-10-20，Task 1–8 与 Task 10 的代码和操作文档已落地：旧帧迁移、资产上传和自动关联、Agent Platform 图片客户端、单帧/首尾帧任务、帧版本与手动上传兼容、资产 Tab、分镜生成面板及开发/联调说明均已加入。

Task 9 尚未验收。本次没有执行自动化测试、前端构建、浏览器流程或真实 Google 图片调用；因此项目级回归、Cloud 项目权限/赠金适用性和真实图片模型输出仍需后续联调确认。后台图片任务使用进程内并发限制，服务重启时将中断任务标记为失败，不会自动重发。

### Checkpoint 4: Task 9–10 后

现有检查通过；最小 Cloud 实际联调完成；操作及配置文档同步后交付。

## 17. Implementation record

- Status: Implementation complete; integration acceptance pending.
- Blocking decisions: 无用户决策阻塞；Cloud 模型权限和赠金适用性需在联调时确认。
- Application code changed: Yes. Implementation spans the backend, web UI, configuration, and operational documentation listed above.
- Automated tests, frontend build, browser checks, and real Cloud image calls were not run in this implementation turn.
