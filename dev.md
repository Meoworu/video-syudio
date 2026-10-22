# 本地开发

## 环境准备

需要 Python 3.12+、Node.js/npm、FFmpeg 和 ffprobe。首次在项目根目录执行：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
cd web && npm ci
```

已有 `.env` 时保留原文件，不要再次复制覆盖。`downloads/projects/` 保存本地项目与生成素材，已被 Git 忽略。

## 配置服务商

在 `.env` 填写 `GOOGLE_CLOUD_PROJECT`、`GOOGLE_API_KEY`、`GOOGLE_VIDEO_API_KEY` 和 `MINIMAX_API_KEY`。Cloud 项目必须关联持有试用赠金的结算账号，启用 Agent Platform API，并授权 Key 绑定的服务账号。`GOOGLE_API_KEY` 保持限制为 Agent Platform API；`GEMINI_API_KEY`、`GOOGLE_CLOUD_API_KEY` 仅作为文字和图片 Cloud Key 的备用名称。视频单独使用 Gemini Developer API Key `GOOGLE_VIDEO_API_KEY`，建议将其限制为 Generative Language API，模型固定为 `gemini-omni-1.1-flash`。两类 Key 均只由后端读取，不要放入前端配置。Gemini API 视频费用独立结算，不能使用 Google Cloud 试用赠金。`GOOGLE_HTTP_TIMEOUT_SECONDS` 设置 Google 请求的超时，默认 120 秒。

图片生成也使用同一 Google Cloud Agent Platform API Key 和项目，不调用 Gemini Developer API。默认模型为 `gemini-3.1-flash-image`；`GOOGLE_IMAGE_MODEL` 可更换模型，`GOOGLE_IMAGE_RESOLUTION` 设置输出尺寸（默认 `1K`），`GOOGLE_IMAGE_TIMEOUT_SECONDS` 默认 180 秒，`GOOGLE_IMAGE_MAX_CONCURRENCY` 默认限制为 2 个并发任务。图片用量是否由试用赠金抵扣，以 Cloud Billing 的服务范围和账单记录为准。

如果 FFmpeg 不在 `PATH`，在 `.env` 设置 `FFMPEG_BIN` 和 `FFPROBE_BIN` 的可执行文件路径。仅浏览界面和调用健康检查时，可以暂不配置服务商凭据；生成内容需要这些配置。

## 启动

在项目根目录启动 API：

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

另开终端启动前端：

```bash
cd web
npm run dev
```

打开 `http://127.0.0.1:5173/`。Vite 会将 `/v1` 代理到 `http://127.0.0.1:8010`。可用 `/v1/health` 检查 API 是否运行，用 `/v1/ready` 检查 Google Cloud 项目、API Key、MiniMax、FFmpeg 等配置。

## 资产与首尾帧流程

1. 粘贴完整故事/剧本原文并创建项目。系统会保留原文，再拆解为制作剧本和镜头；角色和场景按原文识别后自动成为资产项。
2. 打开「资产」页，为角色和场景上传 PNG、JPG 或 WebP 参考图；单张图片最多 6 MB、40 MP。可新增其他参考图并指定适用镜头。
3. 在「分镜」中调整首帧、尾帧提示词和参考资产。默认按镜头角色/场景自动关联；也可切换为手动选择。
4. 点击单帧生成，或「一键生成首尾帧」。一键操作按首帧、尾帧顺序执行；生成失败会显示错误，可删除失败记录后重试。可再次生成并在历史版本间切换。
5. 首尾帧就绪后，沿用镜头卡片的「生成视频」流程。新生成或切换帧版本后，当前镜头视频与成片需要重新生成。

创建表单最多接受 6000 个 Unicode 字符，超长内容会保留在输入框并提示拆分；纯空白输入会被拒绝。拆解场景数量服从原文，若场景数多于目标镜头数，调整目标镜头数后重试。新项目镜头展示其原文出处；旧项目不会补造出处。旧失败项目若已有镜头、上传资产或生成素材，系统会拒绝自动迁移以保护已有内容。

参考资产是供图片模型参考的素材，不会直接替代最终首尾帧。手动上传首尾帧仍可用于跳过图片生成。

## 本地检查

```bash
.venv/bin/python scripts/check_provider_boundaries.py
.venv/bin/python -m pytest -q
cd web && npm run build
```

真实服务商调用和完整流程的验收步骤见 [联调验收清单](docs/acceptance-runbook.md)。

文字和图片请求使用 Agent Platform 的 `aiplatform.googleapis.com`、区域 `global` 和 Cloud API Key；Omni 视频使用 Gemini Developer API Key。Cloud 赠金抵扣、余额和有效期以 Cloud Billing 为准，Gemini API 视频费用单独结算。视频任务支持 URI 与 inline 输出，保留取消和临时文件清理。旧端点任务需在原平台处理后重新提交。详见 [接入说明](docs/agent-platform-api-key-development.md) 和 [视频接入方案](docs/gemini-omni-1.1-api-key-development-plan.md)。
