# Development Plan: Gemini Omni 1.1 视频 API Key 接入

日期：2026-10-22。状态：实现与离线验收完成；真实 Gemini API 联调待配置视频 Key。本方案接替现有视频 OAuth 接入设计；文字与首尾帧图片继续使用当前 Agent Platform 接入。

## 1. Requirement Understanding

- 目标：视频使用 Gemini Developer API，以服务端 API Key 调用 `gemini-omni-1.1-flash`。
- 用户：已有资产、首尾帧和分镜的视频工作台用户。
- 范围：视频凭据、客户端、模型配置、提交/轮询/取消/下载、历史任务兼容、健康检查和文档。
- 非目标：迁移导演规划或图片模型、自动开通服务或结算、修改 MiniMax、创建或收集用户密钥、修改本轮已有资产界面改动。
- 成功标准：视频请求只到 `generativelanguage.googleapis.com`，无需 ADC；首尾帧和镜头时长正确传入；成功视频通过 ffprobe；旧 Cloud 任务 ID 不发送到新接口；凭据不进入前端、项目 JSON 或日志。
- 费用边界：用户选择的是 Gemini API 单独结算渠道。Google Cloud $300 试用赠金不能抵扣 AI Studio Gemini API 费用，不能沿用此前的赠金抵扣预期。[官方规则](https://docs.cloud.google.com/free/docs/free-cloud-features)

## 2. Assumptions and Open Questions

### Assumptions

- 本次仅切换视频。现有 `GOOGLE_API_KEY` 及其别名继续服务于文字/图片，视频引入独立 `GOOGLE_VIDEO_API_KEY`，避免把 Cloud Key 误发到 Gemini 服务。
- 用户会自行准备可访问目标模型、已配置适用结算和额度的 Gemini API Key。当前限制为 Agent Platform API 的 Key 不能直接视作可用的 Gemini API Key。
- 保留既有分镜的 3–10 秒约束和 9:16 / 16:9 画幅；在客户端协议检查阶段核对目标模型实际约束，不静默截断或改变时长。
- 参考 2026-10-22 官方文档：Gemini API 使用的模型 ID 是 `gemini-omni-1.1-flash`，不同于 Cloud 的 `gemini-omni-1.1-flash-preview`。[Omni 指南](https://ai.google.dev/gemini-api/docs/omni)

### Open Questions

- 无阻塞本地设计的决策。真实 Key 的服务限制、地域、模型权限、可用配额及收费结果需要用户环境联调确认。
- SDK 2.29.0 是否完整兼容当前模型的异步响应及 Files 下载，实施时先做离线协议校验；如有明确缺口，再确定必要的 SDK 最低版本。

## 3. Repository Reconnaissance

- 已读：`app/config.py`、`app/clients/google_client.py`、`app/clients/google_omni_video.py`、`app/services/video_service.py`、`app/domain/models.py`、`app/api/projects.py`、`app/api/health.py`、`app/main.py`、相关现有测试与接入文档。
- 仓库检索未发现本地 `AGENTS.md` / `CLAUDE.md`；遵循会话中的用户规则。
- 子项目：FastAPI 后端 `app/`；React/Vite 前端 `web/`。
- 现有命令：`.venv/bin/python -m pytest -q`、`.venv/bin/python scripts/check_provider_boundaries.py`、`cd web && npm run build`。
- SDK：本机 `google-genai==2.29.0`，构造器支持 `enterprise`、`vertexai`、`api_key` 和 `credentials`；依赖声明位于 `pyproject.toml`。
- 开始规划时工作区已有 OAuth、文档和资产粘贴上传等未提交修改。本次仅新增本文档，实施时基于当前内容修改，保留界面改动。
- 证据限制：未读取或打印真实密钥，未提交付费模型任务，未验证真实视频质量。

## 4. Existing Architecture

Observed：

1. `Settings.google_omni_model` 默认仍为 `gemini-omni-flash-preview`；`.env` 可覆盖默认值。
2. `build_google_client()` 是 Agent Platform Key 工厂，供 `GoogleTextClient` 和 `GoogleImageClient` 使用；不能直接改成 Gemini 工厂，否则文字和图片也会换平台。
3. `GoogleOmniVideoClient.client` 当前调用未提交的 `build_google_oauth_client()`，走 ADC 和 Cloud 项目路径。
4. `create_interaction()` 上传两张内联图片，使用来源标记指定首尾帧；设置 `background=True`、`store=True`，随后凭 Interaction ID 轮询。
5. 当前 `save_video()` 只接受内联 Base64，遇到 URI 直接失败；`_find_video()` 递归搜索整个响应，可能不区分输入视频和输出视频。
6. `ShotVideo.provider` 默认 `google_agent_platform`；`VideoService._run()` 和 `cancel()` 也硬编码只允许该 provider。
7. 单镜头通过 `mark_submitting()` 建任务，批量接口在 `app/api/projects.py:generate_all_videos` 独立构造 `ShotVideo`，两条路径都必须迁移。
8. `app/main.py:resume_video_tasks` 将活动视频交给 `VideoService.run()` 恢复；服务保留远端 ID、项目锁和本进程重复执行保护。
9. `/health` 和 `/ready` 目前只有共享 Google Key/Cloud 项目状态，不能表达独立视频 Key 是否配置。

## 5. Relevant Files

| 文件 | 状态 | 责任与修改点 |
|---|---|---|
| `app/config.py` | 已有 | 视频专用 SecretStr Key、空值处理、模型默认值 |
| `app/clients/google_client.py` | 已有 | 新增 Gemini 视频客户端工厂和专用 Key 脱敏 |
| `app/clients/google_omni_video.py` | 已有 | 使用视频工厂；1.1 协议和输出下载适配 |
| `app/domain/models.py` | 已有 | 新 provider 枚举；旧记录解码默认语义保持兼容 |
| `app/services/video_service.py` | 已有 | 新任务身份、旧任务隔离、恢复与取消 |
| `app/api/projects.py` | 已有 | 单镜头/批量入口一致创建任务 |
| `app/main.py` | 已有 | 启动恢复按新旧 provider 分流 |
| `app/api/health.py` | 已有 | 独立视频配置状态 |
| `tests/test_google_client.py` | 已有 | 分平台工厂、真实 SDK 请求路由与脱敏检查 |
| `tests/test_google_omni_video.py` | 已有 | 1.1 请求协议、内联/URI 下载与异常 |
| `tests/test_video_service.py`、`tests/test_health.py` | 已有 | 新旧 provider、恢复、就绪状态 |
| `.env.example`、`README.md`、`dev.md` | 已有 | 双 Key 配置和操作说明 |
| `docs/agent-platform-api-key-development.md`、`docs/acceptance-runbook.md` | 已有 | 当前接入边界及人工验收流程 |
| `pyproject.toml` | 已有，条件修改 | 仅有 SDK 兼容证据时提高依赖下限 |

## 6. Existing Patterns to Reuse

- 复用 `Settings` 的 `SecretStr`、空白校验和 `safe_google_error()`；扩展视频 Key 的脱敏范围。
- 复用 `GoogleOmniVideoClient` 的客户端注入、异步 Interaction 生命周期、Base64 处理与 ffprobe 验证。
- 复用项目锁、视频状态机、原子替换和临时文件清理；远端调用保持在项目锁之外。
- 复用现有 FakeInteractions 和 HTTP 拦截模式，验证真实 SDK 组装结果而非只验证手写字典。
- 复用 provider 隔离思路；区别是本次要把活动 provider 从 Cloud 切到新的 Gemini 1.1 身份。

## 7. Impact Analysis

- 视频平台、认证、模型和下载渠道变更；文字与图片维持当前 Cloud 客户端。
- REST 路由和现有按钮交互保持兼容；新增配置状态字段属于增量 API 变化。
- 项目数据增加新 provider 字面量，本地历史帧和成片不迁移；旧远端任务不能跨平台自动接续。
- 前端不接收 Key；如现有界面直接展示旧平台文案，只做与视频渠道相关的文字修正，不重做布局。
- 视频 Key 应只允许 Gemini 服务；不作为 Cloud Key 的自动回退，避免再次出现 API_KEY_SERVICE_BLOCKED。
- SDK 和依赖只按实际协议兼容需求调整。Google OAuth 工厂的移除仅在全仓确认无调用后进行，不影响文字和图片工厂。

## 8. Proposed Architecture

### 8.1 凭据与客户端分离

```text
文字/图片 → build_google_client → 原 Cloud Key → aiplatform.googleapis.com
视频 → build_google_video_client → GOOGLE_VIDEO_API_KEY → generativelanguage.googleapis.com
```

- 新增 `google_video_api_key: SecretStr | None`，映射 `GOOGLE_VIDEO_API_KEY`，不设置真实默认值。
- 新视频工厂显式传入 `enterprise=False`、`vertexai=False` 和视频 Key；不传 `project`、`location` 或 ADC `credentials`。
- 显式选平台，避免系统残留的 `GOOGLE_GENAI_USE_ENTERPRISE` 等环境配置将视频请求导回 Cloud。
- 视频缺 Key 时在创建任务前返回可操作错误；应用本身仍能启动。只配置 Cloud Key 时视频不可提交，不自动复用它。
- `GOOGLE_OMNI_MODEL` 默认更新为 `gemini-omni-1.1-flash`。旧 `.env` 值不会自动受默认值影响，部署检查必须明确修改该项；本次目标客户端拒绝旧 preview 配置并提示更新。
- 错误脱敏覆盖全部 Cloud Key 和视频 Key；Key 不写进 URL、项目快照、健康响应和错误日志。

### 8.2 视频协议与任务状态

- 使用 Gemini Interactions：两张图片顺序不变，保留官方首尾帧来源标记、画幅与时长语义。
- 保留后台提交和任务存储，以便持久 ID、轮询与重启恢复。`response_format` 的对象/列表形态、时长字段、get/cancel 签名以当前真实 SDK 序列化与 Gemini 文档共同校验，不能照搬 Cloud 请求断言。
- 创建请求不做自动重试，SDK 提交尝试数设为 1；拿到 ID 后立即持久化。若响应超时且未获 ID，标明提交结果未知，不自动重复付费提交。
- 已有 ID 的查询遇到暂时性错误可在总截止时间内退避；401/403 不循环重试，不降级到 ADC 或其他模型。
- 新 provider 使用 `google_gemini_omni_1_1`，写入模型 `gemini-omni-1.1-flash`。所有新建入口显式赋值，不依赖模型默认 provider。
- 保存的任务模型是该任务的快照；恢复不修改其 provider/model，不因环境配置变化重建远端任务。

### 8.3 输出保存

- 优先请求 Files URI 输出，支持内联 Base64 作为兼容返回。理由：官方为大于 4MB 的视频提供 URI 下载路径，不能继续只接受内联数据。
- 先读取 `interaction.output_video`，再兼容明确的 `model_output` 视频内容。禁止无差别递归选取用户输入中的视频。
- URI 仅允许经验证的 Gemini Files 资源或官方 HTTPS 主机/路径；拒绝 GCS、第三方域名、含用户信息或异常端口的地址。不截取任意 URL 最后一段当可信文件 ID。
- 用视频专用客户端查询文件状态：ACTIVE 才下载，FAILED 明确失败，处理中受总截止时间限制。
- SDK 下载到同目录 `.part.mp4`，校验有效视频流和时长后原子替换；超时、解码失败、取消或 ffprobe 失败都清理临时文件。
- 下载前后及可控分块处检查取消。若 SDK 整次下载不能即时中断，在其返回后丢弃并清理；不承诺已取消就能撤销远端已发生的费用。

### 8.4 历史任务

- 保留现有 `google_vertex`、`google_gemini`、`google_agent_platform` 的读取能力；新增 provider 不覆盖旧值。
- `ShotVideo.provider` 的解码默认值继续保持现状，防止缺字段的旧数据被误当作新 Gemini 任务。新任务必须显式写新 provider。
- 启动恢复、手动恢复、取消均核对 provider。旧活动任务不发送到新接口，保留远端 ID并提示在原认证环境处理。
- 已完成的本地视频可继续播放和合成；旧失败任务经用户手动重试后建立新的 Gemini 任务，不能原地换 provider 复用旧 ID。

## 9. Data / API Changes

| 项目 | 方案 |
|---|---|
| `GOOGLE_VIDEO_API_KEY` | 新增，仅视频 Gemini API 使用，不回退到 Cloud Key |
| `GOOGLE_OMNI_MODEL` | 默认 `gemini-omni-1.1-flash`；部署时处理旧 `.env` 覆盖 |
| `GOOGLE_API_KEY` 及别名 | 继续作为文字/图片 Cloud Key |
| `ShotVideo.provider` | 增加 `google_gemini_omni_1_1`，新建显式设置 |
| `/health` | 增加视频 Key 是否配置、目标模型/平台名称；不联网鉴权 |
| `/ready` | 增加视频 Key 就绪项；现有 Cloud 项目检查仍用于文字和图片 |
| 视频路由 | 不改 URL；提交前缺视频 Key 或旧模型配置返回 409 和中文提示 |

无数据库迁移工具；项目 JSON 由现有模型兼容读取。Key 的存在只代表本地配置齐备，不保证线上权限或余额。

## 10. Dependency Graph

```text
Task 1 → Task 2 → Task 3 → Task 4 → Task 6
Task 1 → Task 5 → Task 6
```

## 11. Implementation Tasks

### Task 1: 视频专用 Key 与工厂

- 目标：独立且确定地路由视频凭据。
- 涉及文件：`app/config.py`、`app/clients/google_client.py`、`.env.example`、`tests/test_google_client.py`、`pyproject.toml`（条件修改）。
- 修改内容：新增 SecretStr 视频 Key、1.1 默认模型、Gemini 工厂、缺值/旧模型提示和脱敏；先核对 SDK 兼容，保留文字图片 Cloud 工厂。
- 依赖：无
- 验收标准：视频无需 ADC 或 Cloud 项目参数；Cloud 和视频请求使用各自 Key/主机；全局平台环境变量不改变选择。
- 验证方式：配置和真实 SDK HTTP 拦截，覆盖缺值、空白、不同 Key、URL 无 Key 和异常脱敏。
- 风险与回滚：误用共享 Key 会破坏原图片/文字链路；回滚新工厂与配置字段即可，不更换用户原 Key。

### Task 2: 1.1 提交与轮询协议

- 目标：首尾帧任务可以在 Gemini 1.1 正确提交、查询和取消。
- 涉及文件：`app/clients/google_omni_video.py`、`tests/test_google_omni_video.py`、`tests/test_google_client.py`。
- 修改内容：切换视频工厂，验证请求格式、来源标记、时长、画幅、后台参数与响应；提交禁止 SDK 自动重试，查询在截止时间内退避。
- 依赖：Task 1。
- 验收标准：模型 ID 和服务主机准确；失败不转用 ADC；提交超时不自动重投；实际序列化契约有证据。
- 验证方式：FakeInteractions 和真实 SDK HTTP 拦截，覆盖 401/403/429、错误响应、缺 ID、查询超时与取消。
- 风险与回滚：Cloud 和 Gemini 参数形状存在差异；先完成契约验证，不把改模型字符串视为迁移完成。

### Task 3: 内联与 Files 下载

- 目标：视频成功生成后可可靠保存。
- 涉及文件：`app/clients/google_omni_video.py`、`tests/test_google_omni_video.py`。
- 修改内容：支持 output_video、限定 model_output、URI 校验、Files 状态轮询、专用 Key 下载及取消/超时清理。
- 依赖：Task 2。
- 验收标准：内联和合法 Files 输出均保存为有效 MP4；输入视频不被误认成输出；第三方 URI 被拒绝；失败无残缺成品。
- 验证方式：覆盖 ACTIVE/PROCESSING/FAILED、恶意 URI、无效 Base64、下载失败、取消、ffprobe 失败和最终替换。
- 风险与回滚：下载可能长时间阻塞；限定请求和总时限，保留临时文件方案；不回退为只支持内联而宣称完成。

### Task 4: 新旧任务身份与恢复

- 目标：单镜头、批量、重试、恢复和取消使用一致的任务身份。
- 涉及文件：`app/domain/models.py`、`app/services/video_service.py`、`app/api/projects.py`、`app/main.py`、`tests/test_video_service.py`。
- 修改内容：增加新 provider；统一新任务构造；修正恢复与取消判定；提交前配置检查；旧活动任务给出原平台处理提示。
- 依赖：Task 3。
- 验收标准：所有新任务显式记录新 provider/model；旧 ID 无新端点请求；重启不重复提交；历史本地成片可用。
- 验证方式：覆盖单/批量入口、三种旧 provider、缺 provider 历史记录、重启、取消失败和手动重试。
- 风险与回滚：改解码默认值会污染历史任务；保持旧默认值，新增任务显式标识；回滚前停止新任务并备份项目数据。

### Task 5: 就绪状态与操作文档

- 目标：用户能明确区分 Cloud Key 与 Gemini 视频 Key。
- 涉及文件：`app/api/health.py`、`tests/test_health.py`、`README.md`、`dev.md`、`docs/agent-platform-api-key-development.md`。
- 修改内容：新增视频配置检查和路由说明；记录服务限制、计费渠道、旧模型覆盖和旧任务处理步骤；移除视频必须 ADC 的当前操作指导。
- 依赖：Task 1。
- 验收标准：只有 Cloud Key 时视频未就绪；只缺视频 Key 不影响应用启动；文档不会要求把现有 Cloud Key 直接替换成 Gemini Key。
- 验证方式：health/ready 响应检查及文档配置对照，不通过健康检查调用收费模型。
- 风险与回滚：全局 ready 可能由新增视频检查变为 false；保留细分检查项以定位缺失配置，不泄露凭据。

### Task 6: 回归与最小真实联调

- 目标：验证端到端可交付，并区分离线结果与真实服务结果。
- 涉及文件：`docs/acceptance-runbook.md`、前述已存在的客户端和视频服务测试文件。
- 修改内容：执行定点回归、更新验收记录；使用用户本地新 Key，通过工作台提交一个短镜头并确认文件可播放及费用记录。
- 依赖：Task 4, Task 5。
- 验收标准：离线检查通过；真实调用成功，或明确记录外部权限/配额/结算阻塞；不把 Key 配置成功当作模型调用成功。
- 验证方式：现有 pytest、provider boundary 命令；按需前端构建；人工通过已有界面触发一次短视频，不在启动或测试中自动生成付费视频。
- 风险与回滚：真实生成及重复生成会收费；失败保留 ID 和错误，不自动批量重试；回滚不能代替远端取消。

## 12. Test Plan

| 层级 | 场景 | 验证 | 预期 |
|---|---|---|---|
| 配置/工厂 | 两套 Key、缺视频 Key、环境平台变量冲突 | 扩展 `test_google_client.py` | 视频 Gemini、文字图片 Cloud，凭据不串用 |
| 协议 | 双帧、1.1、时长、后台、get/cancel | SDK HTTP 拦截 | 主机、认证和实际请求体正确 |
| 输出 | output_video、model_output、内联/Files | 扩展 `test_google_omni_video.py` | 合法视频通过校验，任意外部 URI 不访问 |
| 异常 | 401/403、暂时错误、提交结果未知、下载失败 | 故障注入 | 提示明确、提交不重复、错误已脱敏 |
| 数据/状态 | 新旧 provider、单/批量、重启和取消 | `test_video_service.py` | 不跨端点复用 ID、不自动重投、不损坏历史素材 |
| 健康 | 视频 Key 配置有无 | `test_health.py` | 状态准确且无外网调用 |
| 集成 | 一个首尾帧短视频 | 用户本地界面联调 | MP4 可播放、画幅/时长符合要求、实际账单渠道明确 |

实施阶段使用已有 `.venv/bin/python -m pytest -q` 和 `.venv/bin/python scripts/check_provider_boundaries.py`；前端仅在代码或 API 消费发生变化时运行已有 `npm run build`。本次规划未执行应用测试或收费请求。

## 13. Risks / Edge Cases

| 风险 | 影响 | 处理 |
|---|---|---|
| Cloud Key 错当视频 Key | 403 SERVICE_BLOCKED | 独立字段，错误提示指向 Gemini 服务与 Key 限制 |
| `.env` 仍指定旧 preview | 请求退役模型 | 配置检查拒绝旧值，操作文档明确更新 |
| Key 更换到别的项目 | 已有任务无法查询/取消 | 保留 ID，不自动重建任务；要求使用原归属项目有权的 Key |
| 新模型/SDK 输出形状变化 | 下载失败或选错视频 | output_video 优先、明确输出步骤、协议先验收 |
| 新接口配额/地域/结算不满足 | 仍不能生成 | 实际错误提示，不承诺换 Key 即可解决全部权限问题 |
| 大视频只返回 Files URI | 当前代码会失败 | URI 下载作为必做任务，不拖为未实现的后续项 |
| 远端提交成功但本地未获 ID | 重试可能重复收费 | 禁止自动重投，保留结果未知提示 |
| 仍期待 Cloud 赠金抵扣 | 超预期费用 | 文档和接入说明明确 Gemini API 独立结算 |

## 14. Rollback / Compatibility

- 上线前停止创建新视频任务，在原 Cloud 环境完成或取消旧活动任务；备份项目 JSON 和本地素材。
- 先发布可读新旧数据的代码，再配置视频专用 Key和模型。只修改 `.env` 对应项目，不覆盖其余原值，也不把 `.env` 纳入提交。
- 回滚恢复旧视频客户端及环境配置。新 provider 的记录在老版本模型中可能无法解析，需恢复对应备份或保留新枚举读取兼容；不能直接把新任务交给旧客户端。
- 回滚前先处理新 Gemini 端点中仍在运行的任务；本地回滚不会取消远端请求或费用。
- 旧本地帧、旁白和已完成视频不做重生成或删除。

## 15. Implementation Order and Checkpoints

1. 先完成 Task 1–2，锁定认证和协议。
2. 完成 Task 3–4，打通下载和新旧任务兼容。
3. Task 5 可在 Task 1 后进行，最后执行 Task 6。

### Checkpoint 1: Task 1–2 后

- 视频请求经真实 SDK 组装后仍使用 Gemini 主机和独立 Key；不触发 ADC；1.1 双帧请求格式通过协议验证。

### Checkpoint 2: Task 3–4 后

- Files/内联保存、取消清理及重启恢复可用；旧 Cloud ID 不会触发任何 Gemini 调用。

### Checkpoint 3: Task 5–6 后

- 双 Key 配置、ready 和文档一致；一个真实短镜头结果已记录，或明确保留外部阻塞说明。

## 16. Approval Gate

- Status: Approved
- Blocking decisions: 无。真实视频 Key、模型权限和结算条件属于真实联调前提。
- Application code changed: Yes. 视频独立 Key/客户端、Gemini 1.1 协议和 Files 下载、新 provider 与旧任务隔离、health/ready、配置及操作文档已实现。
- 本轮未配置 `GOOGLE_VIDEO_API_KEY`，因此没有真实模型调用。把可访问 Gemini API 的 Key 配置到本地 `.env` 后再手动联调；真实付费调用不会在启动或自动测试中发起。

官方参考：

- [Gemini API Key 类型与服务限制](https://ai.google.dev/gemini-api/docs/api-key)
- [Omni 1.1 视频生成、首尾帧与 Files 输出](https://ai.google.dev/gemini-api/docs/omni)
- [Interactions 生命周期与后台任务](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Google Cloud 试用赠金范围](https://docs.cloud.google.com/free/docs/free-cloud-features)
