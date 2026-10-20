# Development Plan: Google API Key 调用迁移

编写日期：2026-10-19。状态：实现完成；真实服务联调仍待执行。

## 1. Requirement Understanding

- 目标：将导演规划、旁白文稿与 Omni 视频的 Google 调用统一迁移至 Gemini Developer API，通过服务端 API Key 认证。
- 用户：本地开发者和视频工作台使用者。
- 范围：配置、Google 客户端工厂、视频提交/查询/取消/下载、任务恢复、健康检查、测试及接入文档。
- 非目标：增加前端密钥输入页面、修改 MiniMax、重做导演/旁白业务、自动开通云服务、自动修改 IAM 或结算。
- 成功标准：清空 ADC 与项目/区域配置后，有效 Gemini API Key 可以完成文本 JSON 生成及一个首尾帧视频闭环；旧本地项目可读，旧 Vertex 远端任务不会被发到新端点；日志与响应不含密钥。

## 2. Assumptions and Open Questions

### Assumptions

- 推荐接入的是 Google AI Studio/Gemini Developer API 的 Key，目标服务为 `generativelanguage.googleapis.com`。不是只给现有 Vertex 端点加一个 Key，也不是 Vertex Express Mode。
- 当前文本与视频模型 ID 保持可配置，迁移初期保留 `gemini-3.6-flash`、`gemini-omni-flash-preview`，避免把认证迁移和模型升级混在一起。官方 Interactions 参考仍列出这两个 ID，但特定账号可用性需要真实验证。[Interactions API](https://ai.google.dev/api/interactions-api.md)
- API Key 不等于绕过权限：Key 所属项目仍需具备 Gemini API 服务、模型权限、配额与适用的结算条件；创建 Key 本身也可能需要管理员授权。当前 `ai-move` 的权限问题不能通过改代码保证解决。[API Key 官方说明](https://ai.google.dev/gemini-api/docs/api-key)

### Open Questions

- 无阻塞设计决策。真实 Key、模型可访问性及费用条件尚未验证，列为上线验证门槛；文档不收集真实 Key。

## 3. Repository Reconnaissance

- 已读：`README.md`、`dev.md`、`.env.example`、`docs/acceptance-runbook.md`、`pyproject.toml`、Google 客户端、健康检查、视频服务与恢复入口、相关测试。
- 项目根目录检索未发现本地 `AGENTS.md` / `CLAUDE.md`；遵循本会话用户规则。
- 子项目：FastAPI 后端 `app/`，React/Vite 前端 `web/`。
- 已有检查：`python scripts/check_provider_boundaries.py`、`python -m pytest -q`（验收手册）；前端 `npm run build`（`web/package.json`）。
- Git：开始规划时工作区干净；本次只新增本文档。
- 本地已安装 `google-genai==2.29.0`；`Client` 构造签名包含 `enterprise`、`vertexai`、`api_key`、`credentials`、`project`、`location`。`pyproject.toml` 当前仅限制 `google-genai>=2.0`。
- 证据限制：未读取真实 `.env` 值，未调用收费模型，未验证线上凭据和历史远端任务可访问性。

## 4. Existing Architecture

**Observed：**

1. `app/config.py:Settings` 读取项目、区域和可选凭据文件，不读取 Google API Key。
2. `app/clients/google_vertex.py:load_vertex_runtime` 要求项目配置，加载显式凭据文件或 `google.auth.default()`；`build_vertex_client` 创建 `vertexai=True` 的客户端。
3. `google_text.py:GoogleTextClient.generate_json` 通过 `models.generate_content` 获取 JSON；已有客户端注入、瞬时错误重试和退避逻辑。
4. `google_omni_video.py` 用 Interactions API 提交首尾帧、异步轮询和取消；输出解析仅覆盖部分 `steps` 结构，保存支持 Base64 或依赖 ADC 的 `gs://` 下载，并通过 `.part.mp4`、ffprobe 与原子替换保证文件完整。
5. `app/domain/models.py:ShotVideo.provider` 只允许 `google_vertex`；`remoteJobId` 存在时，`app/main.py:resume_video_tasks` 会自动恢复。`VideoService` 目前未按 provider 区分远端端点。
6. `/v1/health` 返回 `googleProjectConfigured`；`/v1/ready` 强制检查项目、ADC 和 global 区域。
7. `scripts/check_provider_boundaries.py` 把 `GOOGLE_CLOUD_API_KEY` 当作禁止项；`tests/test_google_vertex.py` 明确断言没有 API Key 配置。

**Inference：**仅新增环境变量并替换客户端构造，会遗漏下载、任务恢复和就绪检查，无法完成迁移。

## 5. Relevant Files

| File | Existing or proposed | Responsibility and evidence | Requirement |
|---|---|---|---|
| `app/config.py`, `.env.example` | Existing | 认证配置入口 | Key 别名、旧配置退场 |
| `app/clients/google_vertex.py` | Existing | ADC 工厂 | 删除旧生产调用入口 |
| `app/clients/google_client.py` | Proposed | 统一 Gemini 客户端工厂 | 显式选择 API Key 和端点 |
| `app/clients/google_text.py` | Existing | JSON 文本生成 | 切换工厂与错误提示 |
| `app/clients/google_omni_video.py` | Existing | Interactions 与视频落盘 | API 参数、输出与 Files 下载 |
| `app/domain/models.py`, `app/services/video_service.py`, `app/main.py` | Existing | 远端任务标识与恢复 | provider 隔离及旧任务迁移 |
| `app/api/health.py`, `tests/test_health.py` | Existing | 健康与就绪契约 | Key 配置就绪 |
| `tests/test_google_vertex.py`, `tests/test_google_omni_video.py`, `tests/test_video_service.py` | Existing | Google 与任务测试 | 替换 ADC 断言及扩充回归 |
| `tests/test_google_client.py`, `tests/test_google_text.py` | Proposed | 工厂/文本边界测试 | 无 ADC、重试和脱敏 |
| `scripts/check_provider_boundaries.py`, `pyproject.toml` | Existing | 边界检查和依赖 | 允许 Key，去除 GCS 直接依赖 |
| `README.md`, `dev.md`, `docs/acceptance-runbook.md` | Existing | 启动和联调 | 新配置说明和迁移步骤 |

## 6. Existing Patterns to Reuse

- 保留 `Settings` + `get_settings()` 缓存；更新 `.env` 后重启后端。
- 复用 Google 客户端 `client=` 注入进行离线测试，不在单元测试调用真实服务。
- 保留 `create_interaction/get_interaction/cancel_interaction/wait_for_completion/save_video` 的业务方法边界，减少服务层变化。
- 保留文本 JSON 校验与退避策略，以及视频临时文件、ffprobe、原子替换和失败清理机制。
- 复用 `ProjectStore.lock()` 更新任务，保证恢复与取消不会无锁覆盖状态。

## 7. Impact Analysis

- 直接影响：Google 认证、视频下载和健康检查。
- 间接影响：导演与旁白文稿沿用原业务调用；MiniMax 和成片合成不改变。
- 数据：`ShotVideo.provider` 新增 `google_gemini`，兼容读取 `google_vertex`，默认值改为新 provider。
- HTTP：业务生成路由与前端页面不变；健康字段按第 9 节迁移。
- 依赖：保留 `google-genai`；删除不再直接使用的 `google-cloud-storage` 与 `google-auth` 声明，SDK 的传递依赖由安装器管理。按本地 API 能力将最低 `google-genai` 版本提高至经过验证的 2.29.0，不盲目升级最新版。
- 安全：Key 只驻留后端环境；不返回前端、不写项目 JSON；SDK 异常进入日志/任务错误前统一脱敏。
- 性能：视频下载优先 Files SDK；文件处理轮询支持取消，SDK 单次请求超时默认 120 秒且可配置。
- 运维：不用本机 gcloud 登录获取 ADC；已有云权限、Key 所属项目和配额仍是外部前提。

## 8. Proposed Architecture

```text
后端环境 Key → Settings → google_client.build_google_client
                           ├─ GoogleTextClient → generate_content → JSON
                           └─ GoogleOmniVideoClient → Interactions → Files/内联数据
                                                                    ↓
                                                      临时文件 → ffprobe → 最终 MP4
```

### 8.1 认证与配置

- 主配置 `GOOGLE_API_KEY`；兼容 `GEMINI_API_KEY`、`GOOGLE_CLOUD_API_KEY`。后者只是本项目迁移别名，不是 SDK 标准名称。
- 优先级：`GOOGLE_API_KEY` > `GEMINI_API_KEY` > `GOOGLE_CLOUD_API_KEY`；选择第一个非空白值，多值时不输出其内容。使用字段校验保证纯空白按未配置处理，避免空主配置挡住有效别名。
- Key 使用 `SecretStr` 或等价脱敏类型保存，只在构造 SDK 时解出；错误仅提示需配置 Key。
- 工厂显式指定 Developer API 模式；本地 SDK 同时支持 `enterprise` 与 `vertexai`，实施时显式设为 false，测试残留 `GOOGLE_GENAI_USE_VERTEXAI` / `GOOGLE_GENAI_USE_ENTERPRISE` 不会改变端点。只传 API Key，不传项目、区域、ADC。SDK 官方支持 API Key 初始化。[SDK 文档](https://googleapis.github.io/python-genai/)
- 删除生产代码对旧 ADC 工厂的依赖。旧 `.env` 的项目/区域/凭据字段因 `extra="ignore"` 可继续存在，但不作为 Key 或健康条件，也不自动回退 ADC。

### 8.2 文本和视频协议

- 文本保留 `models.generate_content`、JSON 输出设置和现有业务校验；必须用目标模型验证该接口的结构化输出能力。模型不可用时展示可操作错误，不静默改模型。
- 视频保留 Interactions 异步生命周期及持久 ID。逐项核对当前 SDK 的 `input`、`response_format`、`generation_config`、`get/cancel` 参数：`background` 放在请求层，移除未经契约确认的文本内容字段；首尾帧顺序和角色通过官方支持的输入/提示词表达。
- 输出解析新增 SDK `output_video`，同时保留 REST `steps[].content[]`。优先内联 Base64；出现官方 Files URI 时，用同一 API Key 客户端等待文件 ACTIVE 再下载，FAILED 或超时终止；保留取消检查。
- 不对任意返回 URL 携带 Key 发 HTTP 请求；Files URI 校验官方来源及文件路径，使用 SDK 下载，不把 Key 放入查询串。
- 新流程遇到 `gs://` 明确提示旧输出不兼容，不触发 ADC。官方 Omni 文档列出首尾帧插值、内联输出与 Files URI，并提示查询响应可能仍返回 Base64；两种输出均须处理。[Omni 指南](https://ai.google.dev/gemini-api/docs/omni.md)

### 8.3 任务恢复与历史兼容

- 新 `ShotVideo` 标记 `google_gemini`；旧 JSON 中 `google_vertex` 继续反序列化，本地完整 MP4、旁白及成片继续播放。
- 启动恢复、手动重试与取消都检查 provider；旧 Vertex ID 不发送给 Developer API。
- 旧活动任务转为可操作失败提示，保留原 ID、模型与错误用于追查；服务不能证明旧远端任务已取消，不显示“远端已取消”。迁移前建议先在原环境结束/取消活动任务。
- 用户重试旧任务时，明确创建新的 `ShotVideo(provider="google_gemini")` 并清除旧 ID，再提交一次。普通失败重试沿用现有幂等边界，不能遇到轮询失败就自动重新创建收费任务。

## 9. Data / API Changes

| 配置/字段 | 迁移决策 |
|---|---|
| `GOOGLE_API_KEY` | 新标准配置，后端必需 |
| `GEMINI_API_KEY`, `GOOGLE_CLOUD_API_KEY` | 兼容别名，非空优先级见上文 |
| `GOOGLE_TEXT_MODEL`, `GOOGLE_OMNI_MODEL` | 保留配置和现有默认值 |
| 项目/区域/凭据文件 | 从活动认证配置移除，旧环境值可保留但不使用 |
| `ShotVideo.provider` | `google_vertex` / `google_gemini`，新建默认后者 |
| `/v1/health` | 用 `googleApiKeyConfigured` 替代 `googleProjectConfigured`；保留 ok/service/minimaxConfigured |
| `/v1/ready` | 用 `googleApiKey` 替代 googleProject/googleAdc/googleVideoLocationGlobal；其余检查保留 |

健康字段是内部契约调整：当前已读前端未见这些字段的消费方，更新测试和验收手册；外部脚本需同步。`/ready` 只检查配置是否齐备，不调用收费模型，也不承诺 Key 有效。空 Key 允许服务启动和浏览历史项目，生成时给出缺失配置错误。

错误分类：缺 Key 为配置错误；无效 Key/无模型权限等 400/401/403 不进行认证重试；429 与适用的 5xx/网络故障沿用退避。统一清除 Key、认证 Header 和 URL 查询凭据后才展示/持久化错误。

## 10. Dependency Graph

```text
Task 1 → Task 2 → Task 3 → Task 4 → Task 6
   └────────────→ Task 5 ─────────→ Task 6
```

## 11. Implementation Tasks

### Task 1: API Key 配置与客户端工厂

- 目标：无 ADC 环境可明确构造 Developer API 客户端。
- 涉及文件：`app/config.py`、`.env.example`、`app/clients/google_client.py`（Proposed）、`tests/test_google_client.py`（Proposed）。
- 修改内容：增加 Key/别名/脱敏与空值校验；显式关闭两种 Vertex/Enterprise 模式；配置 SDK 单请求超时；缺 Key 在调用边界报错；固定经过验证的参数契约。
- 依赖：无
- 验收标准：三种名称与冲突优先级符合约定；无项目/ADC 仍可构造；SDK 初始化不触发凭据加载。
- 验证方式：新增工厂离线测试，覆盖环境干扰、空白、别名、日志与 repr 脱敏。
- 风险与回滚：模式环境变量可能污染路由；保留迁移前版本作为整体回滚基线。

### Task 2: 文本与视频适配

- 目标：Google 生成与视频落盘全程使用 Key。
- 涉及文件：`app/clients/google_text.py`、`app/clients/google_omni_video.py`、`tests/test_google_text.py`（Proposed）、`tests/test_google_omni_video.py`。
- 修改内容：切换工厂、校验请求字段、适配 output_video/steps、Files 下载和处理状态、错误脱敏，移除 GCS 下载路径。
- 依赖：Task 1
- 验收标准：文本 JSON、首尾帧提交、轮询、取消、内联和 Files 下载均有契约覆盖；错误落盘不含 Key，下载失败无残缺成品。
- 验证方式：注入 Fake 客户端模拟实际 SDK 对象形状及 REST 字典，覆盖超时、FAILED、无输出、无效 Base64 和恶意 URI。
- 风险与回滚：SDK 参数与文档可能有差异；仅调整适配层，不改变镜头生成业务契约。

### Task 3: provider 兼容和旧任务恢复

- 目标：新旧任务 ID 绝不跨端点复用。
- 涉及文件：`app/domain/models.py`、`app/services/video_service.py`、`app/main.py`、`tests/test_video_service.py`、`tests/test_projects.py`。
- 修改内容：新增 provider 枚举值与默认值，恢复/取消前校验，旧活动任务安全失败，旧任务重试明确新建任务。
- 依赖：Task 2
- 验收标准：旧 JSON 可读、完整素材可用；启动与取消均不查询旧 Vertex ID；重试只创建一个新任务并持久新 provider/ID。
- 验证方式：历史项目样本、模拟重启、远端取消失败、重复点击和恢复测试。
- 风险与回滚：旧任务可能仍在云端运行；提示人工追查，不伪造取消成功；回滚必须使用切换前数据备份。

### Task 4: 健康契约和旧依赖收敛

- 目标：就绪检查反映 Key 配置，项目不再依赖 ADC/GCS 工厂。
- 涉及文件：`app/api/health.py`、`tests/test_health.py`、`app/clients/google_vertex.py`、`tests/test_google_vertex.py`、`pyproject.toml`。
- 修改内容：替换健康字段；删除旧工厂及禁止 API Key 的旧测试；调整 SDK 最低版本与不再直接使用的依赖。
- 依赖：Task 3
- 验收标准：缺 Key 服务可运行但 ready=false；有 Key 且其他条件齐备 ready=true；无旧工厂生产引用。
- 验证方式：health/ready 测试、依赖安装解析检查、静态引用检索。
- 风险与回滚：外部健康脚本需同步；依赖收敛失败时恢复原依赖声明，不恢复隐式 ADC 路由。

### Task 5: 开发接入与服务商边界规则

- 目标：配置说明与边界检查匹配新实现。
- 涉及文件：`README.md`、`dev.md`、`docs/acceptance-runbook.md`、`scripts/check_provider_boundaries.py`。
- 修改内容：说明 Key 来源/别名、模型与费用前提、重启要求、旧任务限制；移除 ADC 必需和禁用 Key 的表述，修正边界规则只禁止未授权服务商。
- 依赖：Task 1
- 验收标准：文档中不会再要求新流程先启用 aiplatform 或登录 ADC；不承诺 Key 能绕过项目权限；边界脚本允许新配置。
- 验证方式：文档与配置逐项对照，运行现有 provider boundary 命令。
- 风险与回滚：错误指南易让用户选错 Key；明确 Developer API 与 Vertex Key 的区别。

### Task 6: 回归和最小真实闭环

- 目标：确认认证迁移可交付。
- 涉及文件：`docs/acceptance-runbook.md`，前述测试文件按失败位置定点修正。
- 修改内容：记录离线回归与人工联调结果、Key 所属环境的模型可用性，不记录 Key；确认一次文本生成和一个短视频从提交到文件校验的闭环。
- 依赖：Task 4, Task 5
- 验收标准：全部离线检查通过；真实闭环通过，或明确记录外部权限/结算/配额阻塞，不能将离线通过写成真实调用通过。
- 验证方式：现有 `python -m pytest -q`、`python scripts/check_provider_boundaries.py`；必要时在 web 目录 `npm run build`；真实调用使用用户在本地配置的有效 Key。
- 风险与回滚：真实视频可能收费，不在启动/健康检查/自动化测试中隐式触发；失败先定位权限或协议，避免重复提交。

## 12. Test Plan

| Level | Scenario | Verification | Evidence / expected result |
|---|---|---|---|
| 配置单元 | 缺值/空白/别名冲突/旧环境残留 | Task 1 的配置和 SDK 构造测试 | 确定性选 Key，禁用 ADC 和 Vertex 路由 |
| 客户端契约 | JSON 解析、无效 Key、429/5xx | 注入文本客户端 | 永久错误不重试，瞬时错误退避，错误脱敏 |
| 视频契约 | 创建、get/cancel、output_video、steps | 扩充现有 FakeInteractions | 双帧、画幅、时长和模型参数正确 |
| 文件边界 | 内联/Files、ACTIVE/FAILED/超时/恶意 URI | 模拟 Files SDK + ffprobe | 失败清理 .part，不向第三方传 Key |
| 数据恢复 | 旧 provider、新 provider、重启与重试 | 现有服务/路由测试补充样本 | 旧 ID 不跨端点，新 ID 正确持久化 |
| API | health/ready，无 Key 启动 | FastAPI TestClient | 配置状态准确，不调用模型 |
| 回归 | 导演、旁白、视频、合成 | 项目现有 pytest 与边界脚本 | 原业务测试通过 |
| 人工集成 | 文本 JSON + 一个首尾帧视频 | 有效 Key 的本机工作台 | 视频可播放且 ffprobe 有效；记录费用环境和结果 |

## 13. Risks / Edge Cases

| Risk or edge case | Impact | Mitigation / handling |
|---|---|---|
| ai-move 仍无 Gemini 服务或 Key 权限 | 换代码后仍 403 | 解释具体服务、Key 项目和授权前提，不误导用户反复登录 ADC |
| 相同模型名在账号下不可用 | 文本/视频失败 | 保留模型配置，先验证 ID 与功能，不静默升级 |
| 旧任务仍计费 | 用户误以为任务已结束 | 原环境先结束任务；失败提示保留 ID 便于追查 |
| Key 更换到另一项目 | 当前任务无法 get/cancel | 提示同项目有效 Key 要求；不自动清 ID 重投，不保存 Key 或其可逆信息 |
| SDK 输出结构变化 | 找不到已生成视频 | 覆盖 output_video 与 steps；不要递归把用户输入视频当生成结果 |
| 大文件处理超时 | 请求线程一直等待 | 文件状态轮询也纳入超时/取消策略 |
| Key 泄漏到 SDK 异常 | 项目 JSON 和 API 暴露凭据 | 集中脱敏、仅后端存储、添加失败路径测试 |

## 14. Rollback / Compatibility

- 切换前停止新提交，结束或取消原 Vertex 活动任务，并备份项目 JSON 与环境配置；不把真实配置提交 Git。
- 先部署客户端与数据兼容，再更新本地环境为 API Key 并重启；检查 ready 后做最小真实验证。
- 完整本地素材不迁移；新旧 provider 都可读取，只有新 provider 可进入新远端调用。
- 整体回滚恢复迁移前代码、依赖、ADC 环境及切换前数据备份；原版本无法读取新的 `google_gemini` 字面量，不能直接把新任务数据交给旧代码。
- API Key 不写入项目备份；新端点遗留任务应在其原认证环境下处理，回滚不能替代远端取消。

## 15. Implementation Order and Checkpoints

1. 先 Task 1、Task 2，完成配置与生成适配。
2. 再 Task 3、Task 4，完成恢复兼容、健康契约和依赖收敛。
3. Task 5 可在 Task 1 后编写；最后 Task 6 汇总验证。

### Checkpoint 1: Task 1–2 后

- 无项目配置和 ADC 时，客户端离线测试通过，视频下载不再调用 GCS。

### Checkpoint 2: Task 3–4 后

- 旧项目可读，旧 ID 不跨端点，健康检查不访问模型。

### Checkpoint 3: Task 5–6 后

- 规则、文档、自动检查一致，真实调用结果与外部阻塞有明确记录。

## 16. Approval Gate

- Status: Approved; implementation complete
- Blocking decisions: None for local code changes. A real Gemini API key and account/model access are required for provider integration testing.
- Application code changed: Yes
- Verification before review fixes: 27 automated tests passed; provider boundary check and frontend production build passed.
- Review fixes: dependency minimum raised to 2.29.0; URI validation accepts official resource names; single request timeout is configurable; download polling checks cancellation; secret masking trims configured keys.
- Verification after review fixes: not run yet.
- Not verified: No paid Google or MiniMax calls were made; model access, quota, billing, and real video output remain integration checks.
