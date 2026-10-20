# Agent Platform API Key 接入修正

日期：2026-10-20。目标：Google Cloud 试用赠金所在项目的 Agent Platform 调用；替代此前 Gemini Developer API 迁移方案。

## 认证与结算

- 使用绑定服务账号的 Cloud API Key，保留 Agent Platform API 限制，不要求本机 gcloud ADC。
- `GOOGLE_CLOUD_PROJECT` 必填，指向关联试用结算账号的项目 ID；不能将展示名称或旧项目名称直接当作 ID。
- `GOOGLE_API_KEY` 为主配置，兼容 `GEMINI_API_KEY`、`GOOGLE_CLOUD_API_KEY`，优先级不变。别名不决定请求服务。
- SDK 显式传入 `enterprise=True`、`project`、`location="global"` 和 `api_key`。项目及区域路径明确，不依赖 Express 免费档。
- 单次请求超时默认 120 秒；Key 脱敏、空白处理及无 ADC 回退保持有效。
- Key 绑定服务账号须具备目标项目的模型调用权限。Cloud 项目须启用 `aiplatform.googleapis.com` 并关联有效的结算账号。
- 代码不能保证赠金可用或抵扣成功。余额、到期时间与 SKU 适用范围以 Cloud Billing 为准；不自动升级结算或修改 IAM。

## 请求与输出

- 文本：`aiplatform.googleapis.com/v1beta1/projects/{project}/locations/global/publishers/google/models/{model}:generateContent`。
- 视频：同一项目下的 Interactions 提交、查询与取消，保留首尾帧输入及后台任务流程。
- 视频 `response_format` 使用列表，明确 `delivery="inline"`、画幅、秒数字符串时长。SDK 契约和官方 Cloud 示例均支持这些字段。
- 不配置 GCS 输出目标，按官方接口默认返回视频字节。内联 Base64 分块落盘，每块检查取消；校验与原子替换前后的状态检查保留。
- 不使用 Gemini Developer Files API；若服务仍返回 URI，明确报错并清理临时文件，避免将 Cloud Key 发往错误服务。
- 模型 ID 保持可配置。Omni 为预览能力，首尾帧任务、账号权限及真实返回形状需要目标项目联调，不以离线测试宣称已可用。

## 历史任务与健康检查

- 新任务 provider 为 `google_agent_platform`。
- `google_vertex`、`google_gemini` 仍可读取及播放本地素材；恢复和取消不得跨客户端复用其远端 ID。用户重提时创建新 provider 和任务 ID。
- `/v1/health` 增加 `googleProjectConfigured`；`/v1/ready` 增加 `googleProject` 检查。就绪仅代表配置齐备，不检查云权限和赠金。

## 验证

- 真实 SDK 配合离线 HTTP 拦截：文本、视频提交/查询/取消均请求 Cloud 主机和指定项目路径，通过 Header 发送 Key，不触发 ADC。
- 覆盖缺 Key、缺项目、空白、别名、旧任务隔离、inline 参数、取消清理和 URI 拒绝。
- 执行 Python 测试、服务商边界检查和前端构建。
- 尚未调用真实 Google 服务，未消耗赠金；最终需检查目标项目的实际账单记录。

## 官方依据

- [Cloud API Key 与服务账号绑定](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/api-keys?usertype=standard)
- [Cloud Interactions 与项目路径](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/interactions/developer-guide)
- [Omni 视频格式及不指定 GCS 时返回视频数据](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-text)
- [Cloud 试用赠金及 AI Studio 排除项](https://docs.cloud.google.com/free/docs/free-cloud-features)
