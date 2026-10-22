# 原文保留与剧本拆解分镜开发方案

## 1. Requirement Understanding

- 目标：用户输入的故事作为唯一剧情依据，完整保留内容和顺序，停止现有导演层自动改写故事的行为。
- 使用者：上传完整故事、剧本或科普内容，希望按原文制作视频的用户。
- 推荐流程：原文保存 → 忠实原文的结构化剧本拆解 → 分镜设计 → 资产上传 → 首尾帧 → 视频。
- “直接进入下一步”：提交后自动进入制作流程，不再创作新的故事大纲，也不增加强制确认页面；剧本拆解是内部制作步骤。
- 验收：原文字段逐字符相等；剧本和镜头可追溯到原文；不新增剧情、人物关系、台词、冲突或结局；数量或类型约束冲突时明确失败。
- 本期范围：导演两阶段、原文引用、资产提取、创建与概览页面、失败重试和启动恢复。
- 范围外：模型升级、自动扩写故事、多 Agent 自由创作、完整剧本编辑器、新配音/口型系统，以及自动证明生成画面完全忠实于文字。

## 2. Assumptions and Open Questions

### Assumptions

- 按用户最新补充，采用“先拆解制作剧本，再拆镜头”的两阶段设计；原文始终独立保存。
- 制作剧本组织场景、原文行动、原文台词、角色/场景引用；摄影、光线、景别、首尾帧和运动节拍在分镜阶段补充。
- 原文未写的剧情信息不补充；技术性视觉选择可以补充，但不得改变原文明示的外观、动作、时间、地点和因果。
- 故事和科普都执行原文保护。科普无人物规则与原文明示内容冲突时失败并说明原因，不自动删人物或改写内容。
- 当前 `sceneCount` 请求字段继续使用，页面改称“目标镜头数”。剧本实际场景数由原文决定，镜头数按用户设置校验。
- 已完成旧项目保留原有结果；新建及允许执行的重试/恢复走新流程。旧输入已被前端去掉的首尾空白无法恢复。
- 本期旁白仍是用户单独触发的衍生文稿；其上下文采用原文及已验证剧本，不回写原文。

### Open Questions

- 无阻塞项。以上作为本期实施边界，文档待用户审阅。

## 3. Repository Reconnaissance

- 规则：已遵循用户提供的 AGENTS.md；使用 `coding-plan`，只新增本开发文档。
- 已查阅：导演、模型、项目 API/Store、启动恢复、资产引用、旁白、创建表单、概览/分镜组件及相关测试。
- 已有文档：`docs/project-types-and-deletion-development-plan.md`、`docs/assets-frame-generation-development-plan.md`、`dev.md`、`docs/acceptance-runbook.md`。
- 已发现验证命令：`.venv/bin/python -m pytest -q`、`.venv/bin/python scripts/check_provider_boundaries.py`；在 `web/` 执行 `npm run build`（TypeScript + Vite）。
- 工作区已有未提交修改：`ProjectNavigation.tsx`、`ProjectOverview.tsx`、`styles.css`、新增 `videoStyles.ts`，来自视频风格和长标题修复；后续实现须增量保留。
- 证据限制：本次未运行应用测试或付费生成。外部参考用于设计借鉴，不代表其内部实现或原文保真能力已经验证。

## 4. Existing Architecture

### Observed

1. `web/src/components/ProjectNavigation.tsx:submit` 对 `story` 调用 `.trim()`，提交前已改变首尾空白；输入框还使用 `maxLength={6000}`。
2. `app/api/projects.py:create_project` 创建项目后以后台任务调用 `DirectorService.run_project`。`Project.story` 与 `directorRequest.story` 保存请求原文。
3. `DirectorService._generate_outline` 要求编写 `logline/synopsis/theme`、人物动机、冲突、变化和结局；即使提示“不要添加事实”，输出仍然是模型重新组织的故事。
4. `_generate_shots` 只收到模型生成的 `DirectorOutline`，没有直接带入 `request.story`，会放大前一阶段偏离。
5. `_build_project` 要求分镜数等于 `sceneCount`，并按 `outline.scenes[sceneIndex]` 生成镜头与视频提示词。
6. `Project.create_entity_asset_slots` 从 `directorOutline.characters/locations` 派生资产；`resolve_asset_references` 按镜头角色名和场景名匹配。移除大纲而不替换这条数据来源会破坏资产流程。
7. `retry_director` 按有无缓存大纲选择阶段；`app/main.py:resume_video_tasks` 自动恢复 `generating` 导演任务。旧缓存大纲目前会被复用。
8. `ProjectOverview` 展示大纲梗概、场景目标/冲突/结果，并用 `directorOutline` 是否存在判定导演进度；`ShotWorkspace` 没有原文出处。
9. `NarrationService.generate_manuscript` 同时使用原文、模型大纲和分镜，需适配新的剧本上下文。
10. `tests/test_director_service.py` 使用两阶段文本替身；现有用例验证结构、科普和资产，不验证镜头对原文的覆盖与引用。

### Inference

- 仅修改提示词不能充分解决问题：需要将原文、结构化剧本和摄影描述分开存储，并在两阶段都传入原文。
- 忠实剧本拆解有助于资产归属、场景边界和跨镜头连续性；无需另行增加故事创作阶段。

## 5. Relevant Files

| 文件 | 状态 | 责任与依据 | 计划改动 |
|---|---|---|---|
| `app/domain/models.py` | 已有 | 原文、导演结果、镜头、资产槽派生 | 制作剧本与原文片段契约、新旧流程标记、镜头出处 |
| `app/services/story_source.py` | 拟新增 | 原文相关逻辑独立于模型客户端 | 无损分段、来源摘要、引用/覆盖/顺序校验 |
| `app/services/director_service.py` | 已有 | 两阶段执行与缓存 | 大纲创作替换为剧本拆解；原文+剧本生成镜头；原子落盘 |
| `app/api/projects.py`、`app/main.py` | 已有 | 重试与启动恢复 | 新阶段、旧缓存处理、已制作素材保护 |
| `app/services/asset_service.py` | 已有 | 实体名匹配参考图 | 优先复用；仅在测试证实不兼容时调整 |
| `app/services/narration_service.py` | 已有 | 旁白上下文 | 新流程读取制作剧本，原文优先 |
| `web/src/components/ProjectNavigation.tsx` | 已有且有未提交修改 | 创建输入 | 原文不裁剪；明确保留原文；镜头数和按钮文案 |
| `web/src/types.ts` | 已有 | 前端项目/镜头类型 | 新剧本、流程模式和原文引用字段 |
| `web/src/components/ProjectOverview.tsx` | 已有且有未提交修改 | 原文、大纲和进度展示 | 原文完整排版、制作剧本展示、新旧项目兼容 |
| `web/src/components/ShotWorkspace.tsx`、`web/src/styles.css` | 已有 | 镜头详情与布局 | 每镜头原文出处、长文本折叠及换行 |
| `tests/test_story_source.py` | 拟新增 | 无损文本与引用边界 | Unicode、空白、覆盖、顺序回归 |
| `tests/test_director_service.py`、`tests/test_projects.py`、`tests/test_narration_service.py` | 已有 | 服务/API/旁白替身 | 两阶段保真、缓存、失败、兼容 |
| `tests/test_director_recovery.py` | 拟新增 | 重试与启动恢复边界 | 旧缓存失效、类型/原文不一致、已有素材保护 |
| `README.md`、`dev.md`、`docs/acceptance-runbook.md` | 已有 | 操作与验收说明 | 新流程、原文保护范围和人工核验方式 |

## 6. Existing Patterns to Reuse

- `GoogleTextClient.generate_json`：继续使用当前 Google 文本调用和 JSON 输出，不改变供应方、模型或认证。
- 导演两次结构纠错：分别用于剧本和分镜校验；纠错只改衍生结果，原文不变，不增加无限重试。
- `ProjectStore.lock/save`：按阶段保存，最终结果在锁内更新；失败沿用 `failed/errorMessage`。
- Pydantic 默认值兼容旧 JSON：新剧本字段可空、镜头原文引用默认空，旧项目不伪造出处。
- 现有稳定资产 ID、科普资产过滤、首尾帧快照和视频执行：保持外部资产接口，替换实体提取来源。
- 现有分镜编辑与人工上传/生成步骤：作为视觉内容核验和调整入口。

## 7. Impact Analysis

- 直接影响：导演阶段语义、创建输入保存、剧本/镜头结构和概览；间接影响资产、旁白、重试与重启恢复。
- 请求继续使用 `story/projectType/aspectRatio/style/sceneCount`；项目响应新增可兼容字段。无需数据库迁移或新增环境变量。
- 成本：保持两个逻辑模型阶段；第二阶段加入原文会增加输入 token，原文分段由代码执行。校验失败可能产生有限纠错调用。
- 安全：故事按用户数据传入提示词，不执行其中的指令；校验错误仅展示必要的阶段和原因，不输出密钥。
- 发布：先部署兼容新字段的后端，再部署前端；修改后应重启服务，避免新旧任务执行逻辑混跑。

## 8. Proposed Architecture

### 8.1 外部参考与选型依据

资料核对日期：2026-10-22。下表是本项目的设计取舍，不构成产品效果排名。

| 参考 | 官方可确认的能力 | 本项目借鉴 |
|---|---|---|
| [LTX Studio 剧本与分镜流程](https://ltx.io/blog/how-to-storyboard) | 输入剧本后展示场景/镜头拆解，提取可复用 Elements，生成前可检查拆解结果 | 作为主要产品流程参考：场景结构、原文出处、资产与镜头关联 |
| [LTX 前期可视化流程](https://ltx.io/blog/how-to-build-a-complete-pre-visualization-pipeline) | 以故事节拍组织画面、摄影、声音和角色说明 | 将剧情事实与摄影执行描述分字段，保留连续性要求 |
| [Google Flow](https://labs.google/fx/tools/flow) 与 [官方流程介绍](https://blog.google/innovation-and-ai/products/google-flow-veo-ai-filmmaking-tool/) | 资产复用、镜头控制与 Scenebuilder | 复用已有上传资产/首尾帧体系，维护镜头间视觉连续性 |
| [Runway 官方工具说明](https://help.runwayml.com/hc/en-us/articles/45570040112531-Creating-with-Apps) | Scene Builder、Story Panels 和多镜头工具；Apps 本身不开放 API | 参考可编辑镜头组织；本期继续调用项目现有 Google 客户端 |
| [MovieAgent 研究项目](https://weijiawu.github.io/MovieAgent/) | 导演、场景规划、镜头规划的分层设计 | 借鉴职责分层；属于研究参考，本期以两个确定阶段实现，暂不引入多 Agent 编排 |

这些资料支持“剧本/场景结构有助于镜头规划”的方向；它们没有证明本项目所需的逐字保真保证。原文保护仍需项目自己的数据契约和校验。

### 8.2 原文权威性与无损分段

1. `Project.story` 为唯一原始文本；前端直接提交输入框字符串，后端不 `.strip()`、改标点、转换繁简、归一化 Unicode 或重新拼接段落。空白检查可用 `.strip()` 判断，但不能把处理结果保存。
2. 后端代码按段落/句末边界生成 `SourceSegment(id, index, text)`，保留分隔符和空白。特殊格式无法合理分段时，整段保留；始终满足 `''.join(segment.text) == story`。
3. 为原文计算 SHA-256 摘要，用于检查剧本缓存与原文一致性；摘要不替代完整文本保存。
4. 前端现有 6000 字符限制改为显式超长校验，保留用户输入并提示处理，避免粘贴时静默截断。字符计数按 Unicode 码点；本期不擅自收紧后端原有请求长度能力。

### 8.3 第一阶段：忠实剧本拆解

- 以原文及代码生成的片段为输入，输出 `ProductionScript`：实际场景、原文行动/台词引用、角色与场景实体、技术风格信息。
- 停止生成新的 `synopsis/logline/theme`、人物动机、戏剧冲突或结局；新流程不使用 `DirectorOutline` 作为剧情中间稿。
- 行动与台词保留原文引用。引用文本必须是所引用原文片段的精确子串；台词、数量、专有名词不得改写，未明确的说话者或场景信息留空。
- 场景/实体必须带 `sourceSegmentIds`；模型不能创建源文之外的人物、经历或关系。原文未明确的视觉属性标记“未指定”，摄影层可采用与风格一致的中性呈现。
- 剧本场景数服从原文。目标镜头数少于场景数时明确失败；行动数可以多于镜头数，一个镜头允许引用同一场景内连续多条行动。
- 场景编号连续；按场景展开出处后允许相邻重复，去除相邻重复后的片段索引必须完整且有序，避免漏段或倒序。原文跨一个片段发生换场时，可引用同一片段内的不同精确原句。
- 第一阶段通过后持久化剧本与来源签名，再进入分镜设计；不增加强制确认点击。

### 8.4 第二阶段：分镜与技术执行

- 输入同时包含完整原文、已验证制作剧本、风格、比例和目标镜头数；始终声明原文是剧情事实的最终依据。
- 每个镜头增加 `sourceSegmentIds`、场景内的 `sourceBeatIndex` 和 `sourceBeatEndIndex`，起止序号均包含。程序按目标镜头数预分配连续行动范围，模型逐字复制分配的原文和出处；范围文本直接从完整原文截取，保留中间空白。行动数多于镜头数时允许一镜多行动；镜头数多于行动数时可连续重复同一范围以展示不同景别。所有行动必须完整有序覆盖。
- 允许补充景别、运镜、构图、光线、首尾帧、运动节拍与剪辑衔接；不得新增事件、关系、台词、知识结论或原文未给出的数字。
- 校验镜头数、场景引用、片段覆盖与顺序、角色/地点归属、3–10 秒时长及节拍范围；所有剧本场景必须至少被一个镜头覆盖。
- 新项目标题从原文首个非空行确定性截取到现有标题长度上限，仅用于列表显示；原文不被标题替换。
- 最终写入 `shots/productionScript/assets/editPlan` 后设为 `ready/complete`；分镜失败保留已验证剧本供重试。
- 原文和引用完整性可以由代码验证；自然语言摄影描述是否暗中改变语义，仍需样例人工对照。不能将引用校验通过等同于模型绝无幻觉。

### 8.5 资产、科普与旁白

- `Project.create_entity_asset_slots` 按流程模式选择实体来源：新流程取 `productionScript`，旧项目取 `directorOutline`。继续使用既有 ID 生成方式与资产种类。
- 镜头的 `visibleCharacters/locationName` 必须匹配剧本实体；自动关联、上传参考图、首尾帧快照与提示词编辑保持现有契约。
- 科普仍要求角色/镜头角色为空，最终生图/视频提示词保留既有无人物限制。原文与规则冲突时明确失败，不靠关键词清洗或删掉人物通过。
- 旁白上下文携带原文和新剧本；新模式不再读取旧改写大纲。原文台词保存为台词引用，不能静默当作模型新创作的台词。
- 生成媒体的实际内容、台词准确性和画面连续性继续人工核验，本期不扩展语音合成和口型能力。

### 8.6 重试、恢复和旧项目

- 新项目从 `script_breakdown` 开始，依次进入 `shot_design/complete`，失败统一 `failed`；删除保护继续依赖现有 `status=generating`。
- 缓存制作剧本同时核对原文摘要、项目类型、风格、比例、目标镜头数和脚本 schema 版本。匹配时只重试镜头阶段；不匹配时从原文重新拆解。
- `Project.story` 与 `directorRequest.story` 不一致时明确失败，禁止静默选择其中一份当作新原文。
- 旧已完成项目只读兼容，不后台重算。旧失败/生成中且没有实际制作内容的项目，重试/启动恢复时切换新流程，废弃旧大纲缓存及未上传图片的自动实体槽。
- 迁移前在项目锁内检查已有镜头、用户新增参考资产、资产图片、首尾帧、视频、旁白和成片；存在实际制作内容则不自动覆盖。重试返回 409，启动恢复将任务标失败并说明需新建项目。
- 旧项目缺少创建快照时沿用不可恢复处理，不尝试从改写后的大纲反推用户原文。重试和恢复必须共用同一套检查。

## 9. Data / API Changes

- `CreateProjectRequest` 外部字段保持；增加“非纯空白”校验但保存未经裁剪的 `story`。`sceneCount` 在新模式表示目标镜头数，仍为 1–12。
- `Project` 新增 `directorMode: legacy_outline | source_preserving`，读取旧 JSON 默认 `legacy_outline`；新建时明确写 `source_preserving`。
- `Project` 新增可空 `productionScript`：含 `schemaVersion/sourceHash/sourceSegments/scenes/characters/locations/styleBible` 及缓存使用的输入签名。源文片段和签名由服务端生成。
- `ProductionScript.scenes` 含 `index/sourceSegmentIds/locationName/timeOfDay/beats`；`beats` 的行动与台词用精确原文引用表达，不增加改写梗概字段。
- `Shot` 新增 `sourceSegmentIds: list[str] = []`、可空的 `sourceBeatIndex` 和 `sourceBeatEndIndex`；缺少结束序号时沿用起始序号以兼容已有单行动镜头。新模式要求按预分配范围完整覆盖场景全部 beat，旧镜头为空并显示“旧项目无原文出处”。
- `directorOutline` 保留用于旧项目，新流程为 `null`；资产 schemaVersion 沿用当前定义，避免把它与导演模式混为一谈。
- POST/GET/list/DELETE 路由不变。后台结构失败沿用项目 `failed/errorMessage`，没有新 HTTP 成功语义；重试保护拒绝返回 409。

## 10. Dependency Graph

```text
Task 1 原文/剧本契约 → Task 2 剧本拆解 → Task 3 分镜/资产构建 → Task 4 重试恢复
          │                    └──────────────────────────→ Task 7 旁白上下文
          └────────→ Task 5 创建与类型 → Task 6 来源与剧本展示
Task 3 + Task 4 + Task 6 + Task 7 → Task 8 回归与操作文档
```

## 11. Implementation Tasks

### Task 1: 建立原文与制作剧本契约

- 目标：区分不可变原文、模型拆解结果和旧大纲。
- 涉及文件：`app/domain/models.py`；拟新增 `app/services/story_source.py`、`tests/test_story_source.py`。
- 修改内容：新增制作剧本/引用模型和流程模式；无损分段、摘要、引用及有序覆盖验证；旧字段可兼容默认。
- 依赖：无
- 验收标准：中文、emoji、换行、首尾空白和重复段落能够精确还原；无效引用、遗漏、乱序被拒绝；旧项目可读取。
- 验证方式：原文工具单元用例、Pydantic 与 Store 往返测试。
- 风险与回滚：不归一化 Unicode；新数据读取能力保留到回滚版本，旧数据不批量重写。

### Task 2: 将故事大纲创作改为剧本拆解

- 目标：第一阶段只组织原文已有内容。
- 涉及文件：`app/services/director_service.py`、`app/services/story_source.py`、`tests/test_director_service.py`。
- 修改内容：新增剧本拆解提示词与结构验证；确定性标题；保存剧本缓存与输入签名；有限纠错和失败信息。
- 依赖：Task 1。
- 验收标准：不请求生成新故事梗概、冲突和结局；行动/台词均可定位原句；科普冲突和数量不足不会通过改写解决。
- 验证方式：离线文本替身捕获完整提示词，覆盖正确、首错后对、持续违约及缓存签名。
- 风险与回滚：原文引用校验不能替代语义审阅；第一阶段失败不产生可执行镜头。

### Task 3: 以原文和剧本生成可追溯镜头及资产

- 目标：镜头事实和参考资产有稳定来源。
- 涉及文件：`app/services/director_service.py`、`app/domain/models.py`、`tests/test_director_service.py`、`tests/test_frame_project_type.py`。
- 修改内容：分镜输入同时包含原文/剧本；校验镜头出处、顺序、场景/实体、时长；从新剧本生成资产槽；不构造新的旧式大纲。
- 依赖：Task 2。
- 验收标准：目标镜头数和实际剧本场景数解耦；每场有镜头，出处完整有序；单段可连续多镜头；资产能自动匹配首尾帧参考图。
- 验证方式：镜头替身与资产解析回归；科普/故事各走一次不调用真实媒体模型的完整构建。
- 风险与回滚：角色/场景名漂移会导致资产丢关联，须强校验；最终结果原子更新，失败保留原文和有效剧本。

### Task 4: 统一重试和启动恢复边界

- 目标：旧缓存不会继续引入改写内容，也不会覆盖已制作资源。
- 涉及文件：`app/services/director_service.py`、`app/api/projects.py`、`app/main.py`、`tests/test_projects.py`、拟新增 `tests/test_director_recovery.py`。
- 修改内容：统一阶段选择/缓存签名校验；旧空项目升级新流程；有实际制作内容时拒绝自动重建；快照与原文不一致报错。
- 依赖：Task 3。
- 验收标准：重试/重启均绕过旧大纲；有效剧本可复用；旧有图片/镜头/用户参考资产不丢失；生成中的项目仍不可删除。
- 验证方式：隔离 Store 的重试、恢复与资源保护测试，不启动付费模型任务。
- 风险与回滚：升级部署需停止旧执行进程；对已有内容的拒绝信息必须可见，不能静默跳过后保持 generating。

### Task 5: 保留创建表单原文并同步前端契约

- 目标：浏览器提交和服务器保存的故事一致。
- 涉及文件：`web/src/components/ProjectNavigation.tsx`、`web/src/types.ts`。
- 修改内容：移除故事 trim；以显式长度校验替代输入截断；新增剧本/出处/模式类型；更新“目标镜头数”和创建按钮文案。
- 依赖：Task 1。
- 验收标准：首尾空白/换行保留；纯空白拒绝；超长保留输入并提示；风格下拉、自定义和创建失败保留输入仍可用。
- 验证方式：前端构建；浏览器对照输入与网络请求字符串。
- 风险与回滚：保留当前未提交风格功能；不把剧本字段或内部阶段加成用户必填项。

### Task 6: 展示原文、制作剧本与镜头出处

- 目标：用户可以直接检查镜头依据，概览不会再用改写梗概代替原文。
- 涉及文件：`web/src/components/ProjectOverview.tsx`、`web/src/components/ShotWorkspace.tsx`、`web/src/styles.css`。
- 修改内容：原文按原格式可折叠/展开；新模式显示剧本场景/行动/台词；每镜头展示服务端来源原文；更新阶段/进度判断，保留旧项目大纲展示。
- 依赖：Task 3, Task 5。
- 验收标准：新流程完成后进度正确；原文长文可读；无虚构空冲突箭头；旧项目不伪造出处；长标题删除按钮修复保留。
- 验证方式：前端构建；桌面与窄屏人工核验新旧项目、失败及生成中状态。
- 风险与回滚：避免用 CSS 普通空白折叠让显示误像改文；使用现有预格式换行样式或等价规则。

### Task 7: 适配旁白上下文与资产说明

- 目标：下游继续使用正确的原文/制作剧本来源。
- 涉及文件：`app/services/narration_service.py`、`tests/test_narration_service.py`、`web/src/components/AssetWorkspace.tsx`。
- 修改内容：新模式读取制作剧本与原文，旧模式保留既有上下文；调整资产文案为从原文拆解的角色/场景；保持科普行为。
- 依赖：Task 3。
- 验收标准：新模式旁白不消费旧改写大纲；原文不被写回；原有旁白时长/语音链路与资产上传正常。
- 验证方式：旁白请求替身与现有时长回归；人工检查资产页无角色科普项目。
- 风险与回滚：旁白仍为独立衍生文稿，界面不把它标注为用户原文。

### Task 8: 完成回归与使用说明

- 目标：验证从原文提交到可执行镜头的完整链路。
- 涉及文件：`README.md`、`dev.md`、`docs/acceptance-runbook.md`、`tests/test_director_service.py`、`tests/test_projects.py`。
- 修改内容：补齐完整故事/既有剧本/科普/空白/短文多镜头/长文数量不足验收样例，更新操作和兼容说明。
- 依赖：Task 4, Task 6, Task 7。
- 验收标准：下节自动化与人工用例完成；不宣称引用完整性等于生成画面绝对忠实；旧素材保持可读。
- 验证方式：现有 pytest、provider 边界检查、前端构建；隔离项目人工对照，不默认调用真实付费图片/视频模型。
- 风险与回滚：人工语义核验不使用会改动真实项目的数据；如失败先保留新格式读取能力，再修复生成逻辑。

## 12. Test Plan

| 层级 | 场景 | 验证 | 预期 |
|---|---|---|---|
| 输入/Store | 首尾空白、空行、CRLF 请求、emoji、重复句、繁体 | API/Store 字符串比较与无损分段测试 | JSON 解码后的原文逐字符一致，不自动规范化 |
| 输入错误 | 空白、网页超长 | API 拒绝/表单提示 | 不创建无内容项目，不静默裁剪输入 |
| 剧本 | 原文行动、引语、未知人物信息、场景转换 | 文本替身与出处校验 | 不改台词；未指定内容不成为新剧情；实际场景不被目标数强行重写 |
| 引用 | 不存在、遗漏、乱序、相邻多镜头复用 | 程序校验 | 无效结果进入有限纠错，合法重复引用允许 |
| 镜头 | 短文多镜头、目标数不足、时长和节拍越界 | 服务测试 | 不新增事件凑数；不足/无法执行明确失败 |
| 类型/资产 | 普通故事、无人物科普、科普与原文人物冲突 | 替身构建与现有资产解析 | 科普约束保持，冲突不改写；参考图能自动关联 |
| 失败恢复 | 首阶段失败、分镜失败、签名变更、旧大纲、重启 | 隔离 Store 测试 | 同一原文重试；有效剧本复用；旧改写稿不再作为输入 |
| 资源保护 | 旧项目含用户参考、图片、镜头、旁白/成片 | API/恢复回归 | 409 或可见失败说明，无素材丢失 |
| 浏览器 | 原文长文、出处展开、风格、长标题、旧项目进度 | 本地人工验收 | 字符与排版可核对，现有功能正常 |
| 回归 | Python、提供方隔离、TS/Vite | `.venv/bin/python -m pytest -q`；`.venv/bin/python scripts/check_provider_boundaries.py`；在 `web/` 执行 `npm run build` | 通过；不调用远端付费模型 |

## 13. Risks / Edge Cases

| 风险 | 影响 | 处理 |
|---|---|---|
| 原文只有概念，没有完整情节 | 模型容易自行编故事 | 仅制作已有信息的画面；无法满足数量则提示，不补剧情 |
| 引用正确但画面描述偏离语义 | 数据校验不足以保证保真 | 限制创作范围，展示原文出处，人工对照代表性样例 |
| 一句话需要多个景别 | 一段一镜头会限制表达 | 原文片段与镜头分离，允许相邻镜头引用同一片段 |
| 文本含标题、内心独白、引号 | 无法全部直接画成画面 | 原文保留为上下文，展示其引用关系；不得新增剧情来解释 |
| 数量/时长无法容纳原文 | 自动压缩会漏剧情 | 明确失败及调整建议，不擅自增减原文或镜头数 |
| 既有用户上传资产与新结构冲突 | 自动重建会破坏已有工作 | 旧有实际制作内容时禁止自动迁移重建 |
| 剧本缓存与原文或设置不符 | 重试消费过期内容 | 来源与配置签名验证，禁止仅按“有缓存”复用 |
| 旧数据已被 trim 或已有改写结果 | 无法恢复历史丢失字符 | 使用现存原文，不伪造恢复；已完成项目不后台重算 |

## 14. Rollback / Compatibility

- 新字段用默认值兼容旧项目，旧大纲保留；新数据的制作剧本、模式和来源信息不能在回滚时被旧模型保存操作丢弃。
- 按后端数据兼容 → 新导演流程 → 前端展示发布；执行升级前结束旧版本进程，避免旧后台任务继续写入。
- 不提供静默回到旧故事改写流程的回退。出现问题时暂停新生成/恢复，保留项目读取与已有媒体，发布修复。
- 旧已完成项目不自动迁移；旧失败/生成中空项目在受保护的执行入口升级。
- 本期不变更 Google/MiniMax 模型和 API Key 配置。

## 15. Implementation Order and Checkpoints

1. Task 1 → Task 2 → Task 3：原文契约、剧本、镜头和资产。
2. Task 4：重试与启动恢复；Task 5 → Task 6：创建和核验界面。
3. Task 7 → Task 8：下游适配、回归和使用说明。

### Checkpoint 1: Task 1–2 完成后

- 原文可无损往返，剧本中所有事实文本有来源，错误引用和科普冲突可见失败。

### Checkpoint 2: Task 3–4 完成后

- 原文+剧本能生成镜头、派生资产；重试/恢复不消费旧改写大纲，不覆盖已有制作内容。

### Checkpoint 3: Task 5–6 完成后

- 网页提交不裁剪原文；新旧项目均可查看，镜头出处可读；风格和删除布局改动保留。

### Checkpoint 4: Task 7–8 完成后

- 回归和人工语义样例验收完成，文档范围与真实行为一致。

## 16. Approval Gate

- Status: Pending review
- Blocking decisions: 无；采用原文不可变、内部忠实剧本拆解、自动进入分镜的方案。
- Application code changed: No
- 本轮仅新增本方案，已有风格选项和长标题修复的未提交代码保持原状。后续实施采用分阶段开发，按上述检查点推进。
