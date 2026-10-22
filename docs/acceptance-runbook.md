# video-studio 联调验收清单

文字与图片通过 Google Cloud Agent Platform API Key；视频通过 Gemini Developer API Key。按当前环境完成自动化检查后，再进行真实 Google / MiniMax 联测。

范围说明：已提供 `DELETE /v1/projects/{project_id}`，会永久删除目标项目目录及其上传/生成素材；运行中的导演或视频任务会被拒绝删除，项目 ID 或目录边界异常也会拒绝操作。此操作不可恢复，请在联测中只对专门创建的测试项目验证。

## 环境

1. 安装 Python 3.12+、Node.js、FFmpeg 和 ffprobe。
2. 在项目根目录执行 `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`。
3. 复制 `.env.example` 为 `.env`，填写 `GOOGLE_CLOUD_PROJECT`、`GOOGLE_API_KEY`、`GOOGLE_VIDEO_API_KEY` 与 `MINIMAX_API_KEY`。`GEMINI_API_KEY` 或 `GOOGLE_CLOUD_API_KEY` 仅可作为文字/图片 Cloud Key 别名。模型设为 `GOOGLE_OMNI_MODEL=gemini-omni-1.1-flash`。单次请求超时默认 120 秒，可用 `GOOGLE_HTTP_TIMEOUT_SECONDS` 调整。
4. 确认 Cloud 项目已关联持有试用赠金的结算账号，启用 Agent Platform API；Cloud Key 绑定的服务账号有权调用文字和图片模型。视频 Key 来自可访问 Gemini API 的项目，并允许 Generative Language API。Gemini API 视频费用独立结算，不使用 Cloud 试用赠金；检查两侧各自的结算和配额。
5. 后端执行 `uvicorn app.main:app --host 127.0.0.1 --port 8010`；前端在 `web/` 执行 `npm install && npm run dev`。
6. 查看 `http://127.0.0.1:8010/v1/ready`，检查 Cloud 项目及 Key、视频 Key 与模型、MiniMax Key、FFmpeg 和 ffprobe 项。

## 完整流程

1. 创建 2-3 场的短故事，确认标题、大纲、角色、场景冲突和风格圣经完整。
2. 审核每个镜头的叙事目的、摄影说明、首尾帧描述/提示词、运动节拍和转场；可编辑标题、时长、视频提示词。
3. 打开「资产」页，分别上传角色和场景参考图，确认镜头自动关联；新增一个其他参考资产并指定镜头范围，确认它只出现在指定镜头。
4. 在分镜中分别生成首帧和尾帧，再用另一个镜头执行「一键生成首尾帧」。确认尾帧使用新生成首帧保持连续性；修改提示词或替换参考图后应显示旧结果已过期。
5. 对已生成帧再次生成并切换版本，确认历史可选；制造一次图片模型失败，确认错误显示、删除失败记录和重试可用。上传一张手动帧，确认与生成版本一致进入历史。
6. 提交单镜头与批量 Google 视频任务；观察状态轮询、失败重试、取消，并刷新页面确认状态持久。
7. 生成连续旁白；检查完整句子、全片时长预算、跨镜头 cue 时间线；手动修改后保存并确认重新对齐。
8. 使用 MiniMax 生成至少两个不同语速版本，播放、切换 take，并确认所选版本与音频时长状态一致。
9. 选择硬切/叠化方案后合成成片；确认音轨完整、播放正常、时长与时间线相符，旧成片只在新成片校验成功后替换。
10. 在新的 Gemini Omni 视频任务期间重启 API，确认持久 Interaction ID 能恢复；旧 Vertex ADC / Agent Platform / Gemini Developer 任务不会发送到新端点，应先在原平台结束旧活动任务。确认 URI/inline 输出均可保存并通过 ffprobe，取消时无残缺成品。

## 自动检查

联合测试时再运行：

```bash
python scripts/check_provider_boundaries.py
python -m pytest -q
cd web && npm run build
```

记录模型 ID、MiniMax 模型、失败信息、耗时和成本估算；不要记录密钥。
