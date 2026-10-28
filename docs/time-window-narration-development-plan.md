# Development Plan: 画面时间窗、分段配音与实测校准

日期：2026-10-27。状态：已实现并通过静态构建检查。保留工作区已有的分镜 Tab 和旁白超时修复改动；真实 Google/MiniMax 端到端调用需在已配置服务商凭据的环境验收。

## 1. Requirement Understanding

目标：先按实际镜头视频剪出无旁白预览，再按真实画面安排旁白时间窗，分段配音、测量、校准并导出，减少旁白提前、滞后和超时。

目标流程：

```text
全部镜头视频完成 → 生成无旁白剪辑预览与实测时间线
→ 抽帧识别画面、建议旁白时间窗 → 用户检查和修改
→ 分段 MiniMax 配音 → 测量与校准 → 拼装整条旁白音轨
→ 与同一版剪辑预览封装为最终成片
```

范围与验收目标：

- 每个时间窗有明确的起止时间、对应画面、完整旁白和目标时长；允许跨多个镜头，允许部分画面没有旁白。
- 时间线依据真实视频和实际转场构建，最终以预览文件实测片长为准。
- 每段音频的起点、实测长度和校准后终点可查看；语音不越出窗口、不与其他旁白重叠、不截断句子。
- 可以只重新生成失败或编辑过的片段，成功片段可复用；全过程保持统一音色和基础表演设置。
- 使用当前 Google Cloud Agent Platform 和 MiniMax；不更换模型提供方，不接入 WhisperX。
- 原始故事保持原样。自动精简仅针对生成的旁白；用户手工改写的文案默认锁定，未经明确操作不得自动重写。
- 既有项目、整段旁白、音频版本和成片可继续读取与播放。

不在本期范围：逐词强制对齐、自动字幕、口型同步、背景音乐与原片声音混音、完整拖拽视频剪辑器。窗口内部关键词的精确发音时刻仍需试听确认，本期不能承诺逐词对齐。

## 2. Assumptions and Open Questions

### Assumptions

- 默认先沿用已有镜头顺序和转场设置，生成无旁白预览；“剪辑预览”与“最终成片”分别保存。
- 时间窗按完整语义划分，建议覆盖约 6–15 秒，但不硬性要求每窗等长或每镜一窗；短片允许更短窗口。
- 自动画面分析使用已有 Google 文字模型的多模态输入能力，发送从真实预览提取的图片。具体配置模型的图片输入权限须在开发时用小样本联调确认。
- 单靠镜头标题、提示词和动作设计不能证明实际视频出现了对应动作。抽帧分析是建议，用户可以在预览中确认画面并调整时间窗。
- 首期配音任务串行调用，优先稳定性和片段复用；同项目只允许一个影响该时间线的媒体任务运行。
- 本方案提出的默认阈值属于产品与工程策略，不是供应商承诺；阈值集中定义并写入输入签名。

### Open Questions

无阻塞性产品问题。以下能力不作为本期必需条件：自动理解镜头之间的所有动作、MiniMax 任意风格提示的精确遵循、单词级音画同步。

如果配置的 Google 模型无法读取图片，提供“手动标注画面和窗口”的完整路径；界面明确显示分析不可用，不能用纯文字推测冒充真实画面识别。

## 3. Repository Reconnaissance

- 已读取用户提供的 AGENTS.md 规则：中文简洁；不确定的外部事实查官方资料；代码 review 必须使用 `open-code-review-delegate`。
- 已检查 `app/domain/models.py`、`app/api/projects.py`、`app/main.py`、`app/store/project_store.py`、剪辑/旁白/合成服务、Google/MiniMax 客户端，以及前端旁白和成片面板。
- 已检查 `pyproject.toml`、`web/package.json`、`tests/test_narration_service.py`、`tests/test_narration_timing.py` 和已有测试文件分布。
- 已发现验证命令：`.venv/bin/python -m pytest`、`cd web && npm run build`、`git diff --check`。
- Git 状态：已有未提交修改涉及 `app/api/projects.py`、旁白服务/时长校验、旁白测试、`ShotWorkspace.tsx` 和 `styles.css`。实施时保留并在其基础上演进。
- 证据限制：规划阶段不调用收费模型，不检查真实音视频内容，不更改本机密钥、ADC 或账单配置。

## 4. Existing Architecture

以下为已观察到的代码行为：

1. `app/services/editing.py::rebuild_edit_plan` 使用 `shot.durationSeconds` 和固定转场重叠构建预计时间线；`project_duration` 读取该预计时间线。
2. `app/services/assembly_service.py::assemble` 读取实际视频长度并裁剪、拼接、转场，但入口强制要求 `project.narration.audioPath`，不能先输出无旁白预览。
3. 合成时先按固定转场长度计算片长，实际滤镜又会限制重叠长度；需统一为同一份转场决策，防止实际长度与预算不一致。
4. `app/services/narration_service.py::generate_manuscript` 生成完整句列表；工作区已有修复增加预算与一次超时精简，但仍以预计片长控制整篇旁白。
5. `app/services/narration_timing.py::align_narration` 按字数、语速和停顿从零累计时间；`sourceShotIndexes` 用于有效性检查，没有把某句固定到对应画面区间。
6. `NarrationService.synthesize_audio` 一次调用 MiniMax 合成整段文稿，测量总长度后生成一个 take；无法单段重生成或插入独立留白。
7. `AssemblyService` 对整条音轨执行补静音和片长裁切；新流程必须在拼装前拒绝语音越界，不能用末尾裁切解决超长配音。
8. `web/src/components/NarrationPanel.tsx` 编辑整篇文稿，显示的是估算句子时间；`FinalAssemblyPanel.tsx` 要求旁白就绪才能合成。
9. `ProjectStore.lock/save` 提供进程内项目锁与原子 JSON 替换；帧/资产任务已有请求 ID、任务快照、轮询和重启失败标记模式。

设计判断：问题同时涉及真实时间线、语义窗口和音频长度，单独提高语速或延长整段旁白容忍阈值无法实现需求。

## 5. Relevant Files

| 文件 | 状态 | 责任与证据 | 本期改动 |
|---|---|---|---|
| `app/domain/models.py` | Existing | Project/Narration/NarrationTake 等持久模型 | 增加预览、窗口、任务、音频片段和来源签名 |
| `app/services/editing.py` | Existing | 预计时间线与转场常量 | 区分预计计划和实测计划，统一转场计算 |
| `app/services/media_probe.py` | Proposed | 当前探测代码分散在合成和旁白服务 | 提取视频流/音频流校验、实测时长和样本计数 |
| `app/services/preview_service.py` | Proposed | 新的无旁白预览职责 | 按快照渲染、探测并发布预览和时间线 |
| `app/services/assembly_service.py` | Existing | 最终 FFmpeg 合成 | 共用剪辑渲染逻辑，最终封装同一预览与对齐音轨 |
| `app/services/media_job_service.py` | Proposed | 新媒体任务执行与恢复 | 幂等、输入快照、取消、任务互斥与进度 |
| `app/services/timeline_invalidation.py` | Proposed | 当前失效处理散落各写入口 | 统一使预览/配音/最终输出过期，保留历史文件 |
| `app/services/narration_windows_service.py` | Proposed | 当前只有顺序估算对齐 | 抽帧建议窗口、编辑验证、文案预算与版本控制 |
| `app/services/narration_audio_service.py` | Proposed | 新的分段配音职责 | 调用 MiniMax、片段缓存、精简和校准 |
| `app/services/audio_timeline_service.py` | Proposed | 当前只使用整段音轨 | 将实测音频放入指定时间窗，输出完整音轨 |
| `app/services/narration_service.py`、`narration_timing.py` | Existing | 旧整段文案/音频路径 | 保留旧模式，新增模式的整篇估算不再决定摆放 |
| `app/clients/google_text.py` | Existing | JSON 文本生成 | 增加可选带时间标签的图片输入，保留原调用兼容 |
| `app/clients/minimax_speech.py` | Existing | 同步语音生成与重试 | 复用音色配置，允许分段任务禁用不确定请求的自动重投 |
| `app/api/timeline_narration.py` | Proposed | 新接口路由 | 预览、窗口规划/保存、分段合成与取消 |
| `app/api/projects.py`、`app/main.py` | Existing | 原入口/生命周期 | 原接口兼容、项目删除保护与新任务恢复 |
| `app/services/frame_service.py`、`video_service.py` | Existing | 上游素材修改 | 接入统一失效逻辑 |
| `web/src/types.ts`、`api.ts`、`hooks/useStudioWorkspace.ts` | Existing | 类型、请求和轮询 | 暴露任务与窗口操作，保留草稿保护 |
| `web/src/components/NarrationPanel.tsx`、`FinalAssemblyPanel.tsx`、`web/src/main.tsx`、`styles.css` | Existing | 旁白、合成和导航 | 预览优先的操作顺序与分段对齐 UI |
| `tests/`、`docs/acceptance-runbook.md`、`README.md`、`dev.md` | Existing | 回归与操作说明 | 新媒体集成测试与新流程说明 |

## 6. Existing Patterns to Reuse

- **快照任务与请求去重**：参考 `app/services/frame_service.py`、`asset_image_service.py` 的 requestId/inputSnapshot 和状态检查；新建媒体任务模型，不把整项任务伪装成 FrameJob。
- **项目锁和原子文件发布**：复用 `ProjectStore.lock/save` 与 `.part` 校验后替换；长耗时外部请求和 FFmpeg 在锁外执行，回写时核对 jobId 和输入签名。
- **已有 Google/MiniMax 鉴权**：复用两个客户端工厂和错误脱敏，不增加新的服务商凭据。
- **前端轮询与草稿保护**：复用 `useStudioWorkspace` 的刷新版本保护，以及 `NarrationPanel` 的未保存编辑保护。
- **版本选择**：扩展 NarrationTake，整条对齐音轨作为一个 take，片段明细作为其 manifest；保留旧 take 播放能力。
- **原文约束**：继续使用原文、sourceSegments、科普内容策略；画面分析不能引入原文不支持的新事实。

## 7. Impact Analysis

- 直接影响剪辑、旁白生成、配音、合成和前端操作顺序；导演拆解与视频生成模型保持现有职责。
- 新增可选 JSON 字段及独立预览文件；原始镜头视频和旧音频文件不覆盖。
- 上游修改镜头视频、选用首尾帧、修改时长/转场等操作，需同步使下游输出过期；只改旁白不必重新渲染画面。
- 长任务改为后台执行并轮询；同项目任务互斥，跨项目 MiniMax 并发默认 1，防止一次生成所有窗口时突发收费调用。
- Google 抽帧分析和旁白精简会产生文字/图片输入用量，MiniMax 按其账单规则收费；FFmpeg 本地处理无模型 Token 费用。
- 输入路径限定项目目录，媒体探测设置超时，文本与路径不能插入 shell；失败日志记录任务/窗口 ID、耗时与供应商 traceId，不能包含密钥或整段原文。
- 当前是单进程文件存储：本期支持单 worker；多 worker 的任务互斥不由进程内锁保证，需要后续持久任务队列才能开放。

## 8. Proposed Architecture

### 8.1 两阶段输出与真实时间线

先生成 `preview/<previewId>/silent.mp4`，强制输出无音轨，避免生成视频自带对白与后续旁白混杂。

1. 对所用视频做路径、视频流、可解码性和实测长度检查，固定文件内容摘要。
2. 按已有编辑意图确定 sourceIn/sourceOut；sourceOut 超出实际文件时裁到有效终点并在 UI 提示，不自动拉长视频。sourceIn 越界则失败。
3. 将排序、有效裁剪长度、实际重叠长度写成唯一实测计划；滤镜和时间窗使用同一计划，不分别计算总长度。
4. 转场重叠应小于两侧可用片段，单镜头无入场转场；遇无法支持的转场拒绝或明确映射到已有实现，不伪称有新增转场效果。
5. 渲染后 ffprobe 验证预览。长度和计划相差超过一帧加容器舍入容差则失败并保留旧预览；不能把偏差全部摊到最后一个镜头。
6. 记录实际预览片长、每个 clip 在预览中的起止时间及重叠区。新模式以该快照提供预算，旧 `editPlan` 保留为编辑意图，避免被读取时自动重建覆盖。

最终成片直接复用对应版本预览的视频流，再加入新旁白音轨；不得重新按预计时长剪一遍。

### 8.2 时间窗和画面依据

对实际预览在镜头中心、重要边界等位置抽帧，每张标注真实时间戳；默认最多 24 张，长边不超过 768 像素，单张压缩到约 150 KB 以内，总请求预算约 4 MB，超限分批并校验全局顺序。

Google 输入：原文及可引用事实、制作剧本、实测 clip 清单、带时间戳的真实图片。输出建议窗口，不直接写入音频位置。

每个建议窗口包含：`startSeconds`、`endSeconds`、`sourceShotIds`、`visualSummary`、`text`、`anchorNote`、`evidenceFrameIds`。anchorNote 示例：“这句话描述毛毛虫伪装，安排在主体伪装特写出现后”。

- 从完整语义出发，可以跨镜头；同一主题连续画面可以共用窗口。
- 不强制覆盖整片，开头、转场、情绪段可留白；窗口本身不交叠。
- 不能只相信模型提供的 sourceShotIds：服务端用真实时间线求交验证，转场重叠区可以同时关联两个镜头。
- 抽帧不能保证捕获快速动作；画面判断不明确的窗口标为待确认，允许手动补充画面摘要和拖定起止值。
- 用户保存并确认后才允许配音。抽帧服务失败仍可手动创建窗口，不自动回退到纯文字假定画面。

### 8.3 文案预算和人工编辑

窗口长度 `W=end-start`；默认预留 0.15 秒入场和 0.2 秒收尾，可对短窗口同比缩小，语音可用预算必须大于零。预算只用于估计，最终由实际音频决定。

自动生成文案建议使用可用预算的 85% 左右，并计入句间停顿；允许多句完整旁白，禁止为塞进窗口删掉句尾或拆断句子。

用户编辑 text 后置 `textLocked=true`；系统可以提示超时，但不能未经确认精简。按窗提供“允许 AI 精简”操作，得到候选后由用户确认替换。

不要通过修改原始故事、修改镜头视频速度或改变时间窗边界来隐式迁就配音。需要改窗口时应由用户在界面明确保存。

### 8.4 分段 MiniMax 配音与校准

每个配音任务固定整组 voiceId/model/baseSpeed/emotion/采样率；非供应商支持的自由表演文本仅用于记录和试听指导，不声称会被 API 精确执行。先串行合成窗口，按下列顺序校准：

1. 调用 MiniMax，保存不可变原始片段，解码为统一 48 kHz 单声道 PCM，按实际样本数测时长；供应商 audio_length 仅作诊断参考。
2. 在可用预算内则按窗口起点加入场余量放置；剩余时间留白，不把整段音频强行拉长。
3. 生成文案超时，最多允许一次文本精简并再次 TTS；每窗最多两次 TTS。精简需保留原文事实、句子完整性和语义重点。
4. 第二次结果仍小幅超时且所需变速因子不超过 1.08 时，可使用 FFmpeg `atempo` 微调，保持音高；变速后再次测量。超过上限标记 `needs_edit`，不继续重投。
5. 手工锁定文案不走自动精简；若可在微调上限内适配则标记微调结果供试听，否则 `needs_edit`，由用户调整。
6. 不跨出窗口，不裁掉发音，不移动后续片段来吞掉超时。仅容许样本/编码舍入级误差；明确保留实际时间和校准因子。

片段签名包含文案、窗口长度、声音参数、校准策略版本、预览版本和来源信息。缓存复用要求签名一致且文件探测通过；只改时间窗起点、长度不变时可复用同样的语音，但重新生成整体摆放 manifest。

本期以“整段语义能落入画面窗口”为自动校验范围。用户可按预览试听锚点调整起点；无逐词时间戳时不能宣称关键名词已精确对齐动作帧。

### 8.5 拼装音轨和导出

将校准后的 PCM 片段按绝对起点延迟放置，用有限长度的静音底轨补齐到实际预览长度；合成音轨与预览一致，保持预期音量并防止混音自动衰减。

可采用 `adelay`/`amix` 或按样本位置拼接 PCM；实现选择以 FFmpeg 集成验证为准，必须保持明确的开始/结束样本和有限输出时长。不使用 `-shortest` 掩盖语音越界，不用末尾 atrim 截掉句子。

内部保留无损整条音轨与 segment manifest；播放版本可编码为 AAC/MP3。最终 MP4 使用同一 silent.mp4 视频流和该音轨封装，音频编码尾部填充可以裁掉，但已验证的发音样本不能丢失。

全部窗口有效才发布新的 NarrationTake 并选用；单个窗口失败保留成功缓存和上一次完整可用 take。旧成片只在新文件校验完成后替换有效指针。

### 8.6 后台任务、并发与费用边界

预览、画面规划、分段配音和最终封装均采用持久任务：`queued → running → complete / failed / cancelled / interrupted`。业务窗口还可为 `needs_edit`。

- 请求以 requestId 去重，任务 inputSignature 固定；重复请求不重复收费。相同 requestId 携带不同输入返回 409。
- 长任务不在项目锁内调用外部模型或 FFmpeg。回写前检查 jobId、输入签名和当前版本，旧结果不能覆盖新草稿。
- 活动任务期间阻止编辑其输入、覆盖素材、切换关联音轨和删除项目；互斥检查与入队必须在同一项目锁中完成。
- 取消在外部调用返回后和每窗之间检查；已发出的 TTS 无法保证供应商停止计费，界面如实提示。FFmpeg 可终止子进程并清理本任务临时文件。
- MiniMax 分段调用禁用客户端对结果不明确的网络请求自动重投。语义精简重合成是显式业务阶段，与传输重试分别计数，不能叠乘。
- 重启后收费阶段标记 interrupted，不自动重复提交。用户手动继续时复用已验证成功的窗口；未持久化成功结果的窗口明确提示可能已计费后再决定重试。
- 默认同项目互斥、跨项目配音并发 1。长调用设超时，进度按已完成窗口数呈现。

## 9. Data / API Changes

### 9.1 数据契约（新增字段均有兼容默认值）

| 对象 | 主要字段 | 约束 |
|---|---|---|
| `Project.preview` | id、path、durationSeconds、fps、inputSignature、clips、createdAt、status、job | 不覆盖原视频；status 区分 ready/stale；任务另有独立状态 |
| `PreviewClip` | shotId、shotIndex、sourceDigest、sourceIn/sourceOut、timelineStart/timelineEnd、overlapSeconds | 数值有限且非负，duration 与真实裁剪吻合 |
| `Narration.mode` | legacy / windowed，旧记录默认 legacy | 保存新窗口并确认时显式启用 windowed |
| `Narration.windowRevision` | 单调递增整数 | 保存需要匹配当前 revision，避免覆盖编辑 |
| `NarrationWindow` | id、order、previewId、start/end、sourceShotIds、visualSummary、anchorNote、evidenceFrameIds、text、textLocked、estimatedDuration、status | 稳定 ID；严格排序且不重叠；完整句；允许窗口间留白 |
| `SegmentAudio` | id、windowId、inputSignature、rawPath、calibratedPath、measuredDuration、calibratedDuration、placedStart/End、tempoFactor、providerTraceId | 原始/校准文件版本化；时间字段来自测量 |
| `NarrationTake` 扩展 | mode、previewId、windowRevision、inputSignature、segmentManifest、voiceSnapshot | 保存整条混合音轨；旧 take 仍按原字段读取 |
| `MediaJob` | id、kind、requestId、status、inputSnapshot、inputSignature、progress、errorCode/message、createdAt/updatedAt | kind 区分 preview/windows/audio/export；不得存秘密 |
| `Project.finalRender` | path、previewId、narrationTakeId、inputSignature、isCurrent | 为历史与当前输出提供明确版本归属 |

`Narration.sentences/alignment` 在新模式下可由窗口派生作展示，但不能再据其字数重新计算实际音频位置。整篇 manuscript 是窗口文本拼接结果，新模式不提供与窗口脱节的单一文稿保存入口。

所有输入签名使用规范 JSON + SHA-256；视频内容摘要首次探测时生成并缓存。不得仅用路径、模型名称或文件大小判断同一素材。

### 9.2 接口草案

均为拟新增或拟扩展接口，开发前按本表锁定契约。

| 方法与路径（项目路径前缀 `/v1/projects/{id}`） | 入参 | 返回/行为 |
|---|---|---|
| `POST /preview` | requestId | 202 + Project，创建无旁白预览任务 |
| `POST /narration/windows/plan` | requestId、previewId | 202，真实抽帧分析并提出窗口草稿；不直接发起 TTS |
| `PUT /narration/windows` | previewId、expectedRevision、windows | 200，校验后原子保存并确认窗口，启用 windowed |
| `POST /narration/window-audio` | requestId、previewId、expectedRevision、可选 windowIds、baseSpeed、forceRegenerate | 202；按预览和窗口版本校验；相同 requestId 返回原任务；指定窗口强制重做时绕过其缓存，其余有效片段复用；完整后组装新 take |
| `POST /media-jobs/{jobId}/cancel` | 无 | 202，申请取消该项目活动任务 |
| `GET /v1/projects/{id}` | 既有 | 复用轮询，返回进度和片段状态 |
| `POST /assemble` | 既有入口 | windowed 模式要求当前预览和匹配 take，改后台 202；旧模式保留原返回/合成契约 |

单窗“允许 AI 精简”通过窗口草稿确认操作实现，保存后置 textLocked=false，再调用指定 windowIds 的音频任务；不会因全局重生成静默改动锁定文案。

错误约定：无效时间/重叠/空文案为 422；预览缺失、过期、版本冲突或任务运行中为 409；路径/项目/版本不存在为 404；供应商或探测失败在已接受任务中记 failed 并提供可读错误。同步接口保留 400/502 的旧旁白处理方式。不得让校验错误冒泡成不透明 500。

### 9.3 失效规则

| 变更 | 预览 | 窗口/音轨 | 最终输出 |
|---|---|---|---|
| 镜头视频替换、删视频、重生成、时长/裁剪/顺序/转场/画幅变更 | stale | 保留草稿和文件但标过期，禁止导出 | 历史可播，当前无效 |
| 首尾帧替换导致当前镜头视频失效 | stale | 同上 | 同上 |
| 旁白窗口起止或内容变更 | 保留 | revision 增长；按签名复用或失效受影响片段，整轨过期 | 当前无效 |
| 音色、模型、基础语速变更 | 保留 | 关联音频全部过期，文案保留 | 当前无效 |
| 仅切换有效 take | 保留 | 验证 previewId/revision 后切换 | 需要重新封装 |
| 任一生成任务失败 | 保留上次成功版本 | 保留已有完整 take 和成功片段 | 保留上次成功成片 |

旧窗口/音轨不作为新时间线的有效输入；保留历史播放不等于允许跨版本导出。

### 9.4 初始配置建议

- `NARRATION_TIME_WINDOWS_ENABLED`：开发和渐进上线开关；默认上线新流程前关闭，检查点完成后再开启。
- `NARRATION_TTS_MAX_CONCURRENCY=1`：跨项目配音并发。
- `NARRATION_MAX_AUDIO_TEMPO=1.08`：自动校准上限，允许范围建议 1.0–1.15，出厂使用 1.08。
- 抽帧上限、片段最大重合成次数、入场/收尾余量等策略集中于模块常量并版本化，避免暴露过多环境变量。

## 10. Dependency Graph

```text
Task 1 → Task 2 → Task 3 → Task 4 → Task 5
Task 1 + Task 3 → Task 6 → Task 7
Task 4 + Task 7 → Task 8 → Task 9
Task 4 + Task 5 → Task 10
Task 7 + Task 9 + Task 10 → Task 11 → Task 12 → Task 13
```

## 11. Implementation Tasks

### Task 1: 固定版本化数据契约

- 目标：旧项目可读，新预览、时间窗与片段能持久化。
- 涉及文件：`app/domain/models.py`、`web/src/types.ts`、Proposed `tests/test_time_window_models.py`。
- 修改内容：实现第 9 节模型、兼容默认值、有限数值和版本字段；约定稳定 ID 与 manifest。
- 依赖：无
- 验收标准：旧 JSON 不补造新音轨，新对象可往返序列化；NaN、非法状态和无效窗口被拒绝。
- 验证方式：模型单测覆盖旧记录与新记录 round-trip。
- 风险与回滚：默认 legacy，新增字段可忽略；禁止破坏旧文件或重写旧媒体路径。

### Task 2: 统一媒体探测与实测剪辑计划

- 目标：预览预算与实际滤镜共用同一时间线。
- 涉及文件：`app/services/editing.py`、Proposed `app/services/media_probe.py`、`app/services/assembly_service.py`、Proposed `tests/test_measured_timeline.py`。
- 修改内容：探测真实视频、固定裁剪与重叠规则、建立来源摘要；保留预计 editPlan 的语义。
- 依赖：Task 1
- 验收标准：短于/长于计划的源视频、叠化和单镜头均得到一致有效长度；非法源区间失败。
- 验证方式：用本地 FFmpeg 生成不同长度的临时测试视频，验证 clip 时段和总时长。
- 风险与回滚：实测计划存于独立 preview 对象，不覆盖旧预计计划。

### Task 3: 输出可播放的无旁白剪辑预览

- 目标：无音频输入也能完成画面剪辑。
- 涉及文件：Proposed `app/services/preview_service.py`、`app/services/assembly_service.py`、Proposed `tests/test_preview_service.py`。
- 修改内容：抽取现有视频滤镜构造逻辑，渲染无音轨预览，探测校验后发布新版本。
- 依赖：Task 2
- 验收标准：不存在任何 narration.audioPath 仍可预览；文件无音频流，失败不覆盖上次成功结果。
- 验证方式：真实 FFmpeg 集成验证硬切、叠化、画幅和渲染失败清理。
- 风险与回滚：与旧 final.mp4 分目录存储，旧合成入口暂不切换。

### Task 4: 建立媒体后台任务与恢复入口

- 目标：耗时渲染和收费配音不占用长时间项目锁，也不重复启动。
- 涉及文件：Proposed `app/services/media_job_service.py`、Proposed `app/api/timeline_narration.py`、`app/main.py`、`app/config.py`、Proposed `tests/test_media_jobs.py`。
- 修改内容：实现 requestId 幂等、任务互斥、取消、快照回写、预览接口和重启 interrupted 策略。
- 依赖：Task 3
- 验收标准：重复入队只产生一个任务；项目查询不被渲染阻塞；取消和重启不自动重投收费阶段。
- 验证方式：假任务模拟并发、取消、过期回写与崩溃恢复，检查不触发外部调用。
- 风险与回滚：仅单 worker 上线；关闭功能开关后停止新任务，保留历史元数据。

### Task 5: 接通素材变更和项目删除保护

- 目标：输入改变时旧音画结果不会被当作当前有效输出。
- 涉及文件：Proposed `app/services/timeline_invalidation.py`、`app/api/projects.py`、`app/services/frame_service.py`、`app/services/video_service.py`、`tests/test_projects.py`。
- 修改内容：统一失效函数接入现有全部相关写入口；活动媒体任务纳入项目删除/修改保护。
- 依赖：Task 4
- 验收标准：更换首尾帧、视频或转场使关联预览和配音过期；活动任务拒绝删除；失败任务保留旧文件。
- 验证方式：接口回归及全部失效入口的矩阵检查。
- 风险与回滚：标过期只影响使用资格，不删除历史媒体；任一入口漏接都会导致错配，需要逐项取证。

### Task 6: 根据实际画面提出时间窗

- 目标：时间窗建议有真实画面和时间戳依据。
- 涉及文件：`app/clients/google_text.py`、Proposed `app/services/narration_windows_service.py`、Proposed `tests/test_narration_windows.py`。
- 修改内容：可选多模态 JSON 输入、真实预览抽帧、事实约束、采样预算、引用校验和手动标注降级。
- 依赖：Task 1, Task 3
- 验收标准：旧纯文本客户端调用兼容；窗口引用能追溯到真实抽帧；模型越界/虚构时间戳不能直接入库。
- 验证方式：模拟 Google 响应测试，人工小样本确认配置模型支持图片输入；付费联调单独执行。
- 风险与回滚：抽帧可能漏动作，保持人工确认；模型不可用时提供手动窗口流程。

### Task 7: 保存窗口与校验语义预算

- 目标：用户能确认时间窗、编辑完整旁白并保护手写内容。
- 涉及文件：Proposed `app/api/timeline_narration.py`、Proposed `app/services/narration_windows_service.py`、`app/services/narration_timing.py`、Proposed `tests/test_narration_windows_api.py`。
- 修改内容：实现规划/保存 API，校验时间边界、非交叠、镜头求交、revision 和 textLocked；保存新模式并使旧音轨失效。
- 依赖：Task 6
- 验收标准：可以跨镜头并留白；非法输入不产生部分写入；过期 previewId 或 revision 返回 409。
- 验证方式：接口测试覆盖同一窗口跨镜头、叠化区、空项目和并发保存。
- 风险与回滚：不通过单一 manuscript PUT 改写新窗口；旧模式接口继续可用。

### Task 8: 分段配音与有界校准

- 目标：成功片段复用，超长语音受控修正。
- 涉及文件：Proposed `app/services/narration_audio_service.py`、`app/clients/minimax_speech.py`、Proposed `app/api/timeline_narration.py`、Proposed `tests/test_narration_audio.py`。
- 修改内容：串行窗口配音、声音快照、PCM 实测、一次精简和最多两次 TTS、atempo 上限与 needs_edit；接入窗口重生成任务。
- 依赖：Task 4, Task 7
- 验收标准：每窗不超预算，锁定文案不自动重写；网络结果未知不自动重投；已成功片段不会因其他窗口失败重复计费。
- 验证方式：假 TTS 返回短音频、长音频、损坏数据和网络错误，断言调用次数、缓存与状态。
- 风险与回滚：分段音色可能不连续，通过同一声音快照和试听处理；保留原始音频，不能用校准覆盖源文件。

### Task 9: 拼装绝对时间音轨并封装最终成片

- 目标：音轨位置按实测窗口固定，最终画面与预览完全一致。
- 涉及文件：Proposed `app/services/audio_timeline_service.py`、`app/services/assembly_service.py`、Proposed `app/services/media_job_service.py`、Proposed `tests/test_windowed_assembly.py`。
- 修改内容：按样本位置放置片段、有限静音补齐、校验无越界、生成完整 take 与 manifest，复制预览视频流封装。
- 依赖：Task 8
- 验收标准：窗口间静音正确，时长与预览相符；最后一句没有被裁断；只有完整可用结果更新当前选择。
- 验证方式：真实 FFmpeg 使用不同频率的短音调作为窗口音频，检测样本起止与静音间隔；校验输出视频流和轨道时长。
- 风险与回滚：MP3/AAC 编码填充不能当作发音时长；使用 PCM 中间件验证，失败保留上一完整版本。

### Task 10: 前端先剪辑预览再配音

- 目标：用户能完成无旁白预览并进入配音阶段。
- 涉及文件：`web/src/components/FinalAssemblyPanel.tsx`、`web/src/main.tsx`、`web/src/api.ts`、`web/src/hooks/useStudioWorkspace.ts`、`web/src/styles.css`。
- 修改内容：明确“剪辑预览 → 旁白配音 → 导出成片”，预览按钮只依赖视频素材；增加预览播放器、实测片长、过期与任务进度。
- 依赖：Task 4, Task 5
- 验收标准：没有旁白也可生成预览；运行任务不会错误开启重复提交；预览过期时显示重建入口。
- 验证方式：前端 build 与浏览器检查空素材、成功预览、失败和窄屏状态。
- 风险与回滚：旧成片继续显示并标识历史版本，功能开关关闭可回旧操作流。

### Task 11: 前端窗口编辑与同步试听

- 目标：用户能在真实画面上调整旁白时间并只重生成指定段。
- 涉及文件：`web/src/components/NarrationPanel.tsx`、`web/src/api.ts`、`web/src/hooks/useStudioWorkspace.ts`、`web/src/styles.css`。
- 修改内容：窗口卡片展示起止、画面摘要、文案、预算/实测/变速状态；支持确认、锁定文案、单段试听、重生成和整条预览。
- 依赖：Task 7, Task 9, Task 10
- 验收标准：点击窗口能跳到视频对应时间；整条试听由同一个预览视频与选定音轨共同播放/暂停/跳转；浏览器不支持时使用本地封装的带配音预览，避免两个独立播放器漂移。
- 验证方式：浏览器验证播放控制、草稿保护、失败重试、跨镜头窗口和 320/768/1440 宽度。
- 风险与回滚：UI明确区分估算与实际位置，未保存草稿不被轮询覆盖；窗口试听结束自动停止。

### Task 12: 旧旁白与版本选择兼容收口

- 目标：旧项目可以逐步迁入新流程，历史音频不会被误认为已按窗对齐。
- 涉及文件：`app/services/narration_service.py`、`app/api/projects.py`、`web/src/components/NarrationPanel.tsx`、`tests/test_narration_service.py`、`tests/test_projects.py`。
- 修改内容：旧接口 mode 分流、显式迁移入口、有效 take 校验、历史播放，以及新模式异步 /assemble 契约。
- 依赖：Task 11
- 验收标准：旧 JSON/旧 take 可读可播；windowed 模式拒绝选用旧时间线音轨作为当前结果；转换失败不丢旧数据。
- 验证方式：旧项目回归、切换模式和陈旧版本选择接口测试。
- 风险与回滚：不将旧整条音频按估算句子切开冒充新片段；迁移必须建立新预览和新音轨。

### Task 13: 集成验收与文档更新

- 目标：用真实时间线完整走通新流程，并明确本期精度边界。
- 涉及文件：Proposed `tests/test_time_window_workflow.py`、`docs/acceptance-runbook.md`、`README.md`、`dev.md`。
- 修改内容：串联预览、窗口、假配音与导出回归；补充手动收费联调和操作说明。
- 依赖：Task 12
- 验收标准：假服务自动回归不收费；人工确认关键语义与画面在同一窗口，超时/失败/重启路径可恢复，历史结果仍可播放。
- 验证方式：`.venv/bin/python -m pytest`、`cd web && npm run build`、`git diff --check`；确认后用一个临时项目做真实模型联调。
- 风险与回滚：真实生成成本单列；功能开关完成最终检查后启用，不在开发中暗中升级账单或购买配额。

## 12. Test Plan

| 层级 | 场景 | 验证方式 | 预期 |
|---|---|---|---|
| 模型/单元 | 旧项目缺少 preview/windows，新模式 round-trip | 新模型测试 | 默认 legacy，无强制迁移 |
| 时间线 | 视频实际长度与预设不同，叠化、短片段 | 临时本地视频 + 探测 | 渲染与计划使用相同重叠长度 |
| 无旁白渲染 | 无任何 narration 数据 | FFmpeg 集成 | 可生成无音轨预览 |
| 画面分析 | 样本引用错误、模型幻觉、图片权限不足 | 假 Google 响应 | 不发布非法窗口，可手工标注 |
| 窗口验证 | 跨镜头、留白、交叠、越界、NaN、空句 | 单元与 API | 合法窗口保存，非法全部拒绝 |
| 实测校准 | 短音频、微超时、明显超时、手写锁定 | 假 TTS + PCM | 留白/有界精简/微调或 needs_edit |
| 费用与重试 | 请求重复、超时未知、片段失败后继续 | 调用计数断言 | 无隐式重投，成功缓存复用 |
| 音轨摆放 | 12–18 秒窗口、相邻窗口、片尾语音 | 不同频率测试音 + 样本检测 | 起止误差不超过目标 PCM 一个样本；编码后使用编解码延迟容差 |
| 最终封装 | 音轨与预览来自不同版本 | API 与 FFmpeg | 拒绝错配，不偷偷重剪画面 |
| 生命周期 | 取消/重启/删除/陈旧结果回写 | 假任务并发测试 | 无覆盖新输入，无活动任务误删 |
| 历史版本 | 改文案、改视频、旧 take 选择 | 回归 | 历史可播，过期不能导出当前成片 |
| 前端 | 草稿编辑、轮询、seek、试听、窄屏 | 浏览器真实交互 | 草稿不丢、单一播放时钟、状态清晰 |
| 真实联调 | 同一短片先预览后配音 | 一个临时项目人工检查 | 语义大致对齐，记录实际成本和剩余偏差 |

本期不以逐词对齐误差作为验收项。自动测试保证媒体位置和完整性，语义准确、音色连贯和听感需人工验收。

## 13. Risks / Edge Cases

| 风险或边界 | 影响 | 处理 |
|---|---|---|
| 实际生成画面与导演提示不符 | 旁白指向不存在动作 | 使用实际抽帧，允许手工纠正，原文事实仍是内容边界 |
| 快速动作落在采样帧之间 | 锚点时间不精确 | 标记需确认，预览跳转检查；本期不承诺动作帧级对齐 |
| 每段 TTS 语气不连续 | 拼接听感断裂 | 完整语义分段、统一音色参数、边界留白并人工试听 |
| 微调仍超时或手写文本太长 | 无法放入窗口 | needs_edit，提供调整文案/窗口入口，不截断或无限重试 |
| 供应商 429、网络结果未知 | 重复计费、任务失败 | 并发 1、有界请求、不确定结果不自动重投 |
| 新时间线使窗口过期 | 旧配音错位 | previewId + revision + inputSignature 三重约束 |
| 旧项目使用可变视频路径 | 摘要与内容不符 | 快照绑定内容摘要，任务期间阻止覆写，发布前复核 |
| 文件写完但状态未提交就崩溃 | 产生孤立媒体或重复请求风险 | 版本化目录、manifest 和完成标记；恢复先验证本地结果，禁止直接重投 |
| FFmpeg 时长或音频采样率舍入 | 累计漂移 | PCM 样本位置拼装，固定输出参数，端到端探测 |
| 无旁白窗口或全静音作品 | 空列表和轨道校验失败 | 允许窗口间留白；整片无旁白通过“仅导出画面”明确操作，不能误报配音完成 |
| 多 worker 部署 | 锁和任务去重失效 | 本期限制单 worker，部署文档说明；持久任务队列后续单列 |

## 14. Rollback / Compatibility

- 旧项目默认 legacy，旧旁白/成片保持读取和播放；用户生成预览并确认新窗口后才转为 windowed。
- 新旧文稿入口分流。新模式不接受旧整篇保存 API 静默覆盖窗口，返回明确 409 并引导窗口编辑。
- 同一预览和文案修订可以保留多个声音版本；选择时严格校验 manifest，不允许只因音频总时长相同就视为兼容。
- 每阶段只增加可选字段与新目录，不批量删除历史文件。不做自动迁移全部项目、不升级模型版本、不安装 WhisperX。
- 回滚先停止新任务并关闭功能开关，保留 windowed 作品的播放器；禁止旧合成算法对 windowed 项目直接再导出。需要继续编辑时使用支持新字段的版本或另存 legacy 副本。
- `Project.finalVideoPath` 继续作为当前有效结果投影；历史路径由 finalRender/take 记录持有。新任务失败时不清除上一个同输入版本的有效结果；输入变化时历史文件可播但标为过期。

## 15. Implementation Order and Checkpoints

依次实施 Task 1–13；具备对应依赖后可以独立验收，不以完成 UI 作为提前启用新模式的依据。

### Checkpoint 1: Task 1–3 完成

- 无旁白输入也能渲染预览，实测时间线与最终画面时长一致；旧记录可读。

### Checkpoint 2: Task 4–5 完成

- 任务幂等、取消、恢复和全部素材失效入口通过验证；长任务不阻塞项目读取。

### Checkpoint 3: Task 6–7 完成

- 实际抽帧可定位、窗口可人工确认、越界与交叠不可保存；多模态不可用时手工路径可用。

### Checkpoint 4: Task 8–9 完成

- 假配音片段按指定样本位置合成；超时有界处理；失败缓存保留；最终使用同一预览画面。

### Checkpoint 5: Task 10–12 完成

- 浏览器完成预览、窗口编辑、配音试听、重生成、历史播放；新旧接口正确分流。

### Checkpoint 6: Task 13 完成

- 回归、前端构建和单个真实项目人工验收通过，再启用新流程；记录不能保证逐词对齐的边界。

## 16. Approval Gate

- Status: Implementation in progress
- Blocking decisions: None；默认采用本方案参数，配置模型多模态权限通过 Task 6 验证，失败有手工路径。
- Application code changed: Yes. 首阶段已增加兼容数据契约、无声预览、后台任务、窗口规划与保存、分段 TTS 校准、绝对时间 PCM 拼装、对应预览封装和前端流程。仍需继续逐项核对验收及旧项目边界。

官方资料（2026-10-27 核对）：

- [Google Agent Platform 图片理解](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/image-understanding)：支持向多模态请求提供实际图片；配置模型可用性需实际权限验证。
- [MiniMax 同步语音合成](https://platform.minimax.io/docs/api-reference/speech-t2a-http)：支持 voice_setting，返回音频数据、长度元数据和 trace_id；这些能力不等同于保证按指定秒数发音。
- [FFmpeg Filters](https://www.ffmpeg.org/ffmpeg-filters.html)：提供 atempo、adelay、apad、amix 等媒体处理能力。变速阈值、窗口预算与校准策略是本项目设计。

Plan generated and waiting for review; application code has not been changed.
