# Google API 接入说明

## 服务与凭据

- 导演文字与首尾帧图片：Google Cloud Agent Platform，使用绑定服务账号的 Cloud API Key。
- 视频生成：Google Cloud Agent Platform Interactions，使用 `gemini-omni-1.1-flash-preview`，通过 OAuth Application Default Credentials (ADC) 鉴权。
- 文字/图片 Key 配置为 `GOOGLE_API_KEY`，兼容 `GEMINI_API_KEY` 与 `GOOGLE_CLOUD_API_KEY` 别名。视频请求不使用 API Key。
- 请求项目配置为 `GOOGLE_CLOUD_PROJECT`，视频模型使用 global 区域；本机通过 `gcloud auth application-default login` 提供 ADC。运行环境也可使用标准 Google ADC 凭据提供方式。
- Cloud 项目需启用 Agent Platform API，视频调用身份需要相应 IAM 权限。符合 Cloud Billing 条件的用量会计入该项目关联账单，可使用适用的 Cloud 赠金。

## 视频请求和任务兼容

- Interactions 使用模型 `gemini-omni-1.1-flash-preview`，发送动作提示、首帧和尾帧；时长与画幅通过提示词及 `response_format` 传入。
- 提交、查询与取消统一使用 ADC OAuth。提交关闭 SDK 自动重试，避免不确定结果时重复创建收费任务；Interaction ID 会持久保存并用于轮询和重启恢复。
- 首尾帧以内联图片数据发送；视频响应以内联数据保存并通过 ffprobe 校验后原子替换成片。
- 新任务 provider 为 `google_agent_platform_omni_1_1`。旧 `google_vertex`、`google_gemini`、`google_agent_platform`、`google_gemini_omni_1_1` 和缺少 provider 的记录仍可读取，但远端任务不能跨 API 恢复或取消；须在原服务端处理后重新提交。
- OAuth 权限、Agent Platform API 启用状态、模型权限、配额或账单不可用时请求会失败。提交没有返回 ID 时标记为结果未知，不自动重投。

## 验证与操作

- 查看 `/v1/health` 和 `/v1/ready` 的 Cloud Key、Cloud 项目、视频模型及本地媒体工具状态。健康检查不发外部请求。
- 使用 `.env.example` 配置项目 ID 与文本/图片 Cloud API Key；视频端需单独配置 ADC OAuth，不需新增视频 API Key。
- 本地调试前运行 `gcloud auth application-default login`。真实联调通过工作台选择一个首尾帧完整的镜头后手动提交，并检查生成文件及 Cloud Billing 账单。

## 官方文档

- [Agent Platform Omni 首尾帧视频生成](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-first-and-last-frames)
- [Agent Platform 视频生成模型](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/generate-videos-from-text)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/provide-credentials-adc)
