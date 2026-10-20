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

在 `.env` 填写 `GOOGLE_API_KEY` 和 `MINIMAX_API_KEY`。`GEMINI_API_KEY`、`GOOGLE_CLOUD_API_KEY` 可作为 Google Key 的备用名称。Google API Key 仅由后端读取，不要放入前端配置。`GOOGLE_HTTP_TIMEOUT_SECONDS` 设置单次 Google 请求的超时，默认 120 秒。

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

打开 `http://127.0.0.1:5173/`。Vite 会将 `/v1` 代理到 `http://127.0.0.1:8010`。可用 `/v1/health` 检查 API 是否运行，用 `/v1/ready` 检查 Google API Key、MiniMax、FFmpeg 等配置。

## 本地检查

```bash
.venv/bin/python scripts/check_provider_boundaries.py
.venv/bin/python -m pytest -q
cd web && npm run build
```

真实服务商调用和完整流程的验收步骤见 [联调验收清单](docs/acceptance-runbook.md)。
