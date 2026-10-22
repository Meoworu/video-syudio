# Google API 接入说明

## 服务与凭据

- 导演文字与首尾帧图片：Google Cloud Agent Platform，使用绑定服务账号的 Cloud API Key。
- 视频生成：Gemini Developer API Interactions，使用独立 `GOOGLE_VIDEO_API_KEY`，模型为 `gemini-omni-1.1-flash`。
- 文字/图片 Key 配置为 `GOOGLE_API_KEY`，兼容 `GEMINI_API_KEY` 与 `GOOGLE_CLOUD_API_KEY` 别名。视频 Key 不接受这些别名，也不会回退到 Cloud Key 或 ADC。
- Cloud 请求需要 `GOOGLE_CLOUD_PROJECT`、global 区域及 Agent Platform API 权限；Gemini 视频请求不读取 Cloud 项目或 ADC。
- Gemini 视频 Key 建议限制为 Generative Language API。视频请求仅在服务端发出，不能返回到前端、项目 JSON 或日志。
- Cloud 项目赠金只适用于符合 Cloud Billing 条件的 Cloud 使用量；Gemini Developer API 使用单独结算，不抵扣 Cloud 试用赠金。

## 视频请求和任务兼容

- Interactions 使用模型 `gemini-omni-1.1-flash`、首尾帧图片输入和 `<FIRST_FRAME>` / `<LAST_FRAME>` 来源标记；时长通过提示词和视频输出格式传入，画幅通过 `response_format` 指定。
- 提交、查询与取消统一使用 Gemini API Key。提交关闭 SDK 自动重试，避免不确定结果时重复创建收费任务；已有 Interaction ID 会持久保存并用于轮询和重启恢复。
- 输出优先使用 Gemini Files URI，兼容 inline Base64。只接受 Gemini 官方文件资源，等待文件状态为 `ACTIVE` 后用同一视频 Key 下载，并通过 ffprobe 校验后原子替换成片。
- 新任务 provider 为 `google_gemini_omni_1_1`。旧 `google_vertex`、`google_gemini`、`google_agent_platform` 和缺少 provider 的记录仍可读取，但远端任务不能跨 API 恢复或取消；须在原服务端处理后重新提交。
- 401/403 不会循环重试；提交没有返回 ID 时标记提交失败，不自动重投。Key 配置正确并不代表模型权限、地域、配额或结算已经可用。

## 验证与操作

- 查看 `/v1/health` 和 `/v1/ready` 的 Cloud Key、Cloud 项目、视频 Key、视频模型及本地媒体工具状态。健康检查不发外部请求。
- 使用 `.env.example` 配置两种 Google Key。更换模型时不得把 Cloud 项目的 API Key 用作 Gemini 视频 Key。
- 自动化检查不创建收费视频。真实联调通过工作台选择一个首尾帧完整的镜头后手动提交，并检查生成文件及 Gemini API 单独账单。

## 官方文档

- [Gemini Omni 视频生成和编辑](https://ai.google.dev/gemini-api/docs/omni)
- [Gemini API Key](https://ai.google.dev/gemini-api/docs/api-key)
- [Google Cloud 免费试用赠金适用范围](https://docs.cloud.google.com/free/docs/free-cloud-features)
