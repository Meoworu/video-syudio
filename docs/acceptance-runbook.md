# video-studio 联调验收清单

核心功能迁移已完成，待与用户联合测试；真实 Google Cloud / MiniMax 调用、自动化测试和前端构建尚未执行。

范围说明：已提供 `DELETE /v1/projects/{project_id}`，会永久删除目标项目目录及其上传/生成素材；运行中的导演或视频任务会被拒绝删除，项目 ID 或目录边界异常也会拒绝操作。此操作不可恢复，请在联测中只对专门创建的测试项目验证。

## 环境

1. 安装 Python 3.12+、Node.js、FFmpeg 和 ffprobe。
2. 在项目根目录执行 `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`。
3. 复制 `.env.example` 为 `.env`，填写 `GOOGLE_CLOUD_PROJECT` 与 `MINIMAX_API_KEY`；不使用 Google API Key。
4. 执行 `gcloud auth application-default login`，并确认目标项目启用了 Vertex AI / Agent Platform API、账号具备访问权限和模型配额；Gemini Omni 视频目前需使用 `GOOGLE_CLOUD_LOCATION=global`。
5. 后端执行 `uvicorn app.main:app --host 127.0.0.1 --port 8010`；前端在 `web/` 执行 `npm install && npm run dev`。
6. 查看 `http://127.0.0.1:8010/v1/ready`，检查 ADC、项目配置、MiniMax Key、FFmpeg 和 ffprobe 项。

## 完整流程

1. 创建 2-3 场的短故事，确认标题、大纲、角色、场景冲突和风格圣经完整。
2. 审核每个镜头的叙事目的、摄影说明、首尾帧描述/提示词、运动节拍和转场；可编辑标题、时长、视频提示词。
3. 按每个镜头的首帧/尾帧提示词准备图片并上传，确认素材预览与类型校验正常。
4. 提交单镜头与批量 Google 视频任务；观察状态轮询、失败重试、取消，并刷新页面确认状态持久。
5. 生成连续旁白；检查完整句子、全片时长预算、跨镜头 cue 时间线；手动修改后保存并确认重新对齐。
6. 使用 MiniMax 生成至少两个不同语速版本，播放、切换 take，并确认所选版本与音频时长状态一致。
7. 选择硬切/叠化方案后合成成片；确认音轨完整、播放正常、时长与时间线相符，旧成片只在新成片校验成功后替换。
8. 在测试中的视频任务期间重启 API，确认有持久 Interaction ID 的任务能恢复；无法确认 ID 的提交需显示可操作失败提示。

## 自动检查

联合测试时再运行：

```bash
python scripts/check_provider_boundaries.py
python -m pytest -q
cd web && npm run build
```

记录模型 ID、Google 区域、MiniMax 模型、失败信息、耗时和成本估算；不要记录密钥、ADC 内容或完整凭证路径。
