# video-studio 联调验收清单

文字与图片通过 Google Cloud Agent Platform API Key；视频通过 Google Cloud Agent Platform Interactions API 和 OAuth ADC。按当前环境完成本地检查后，再进行真实 Google / MiniMax 联测。

范围说明：已提供 `DELETE /v1/projects/{project_id}`，会永久删除目标项目目录及其上传/生成素材；运行中的导演或视频任务会被拒绝删除，项目 ID 或目录边界异常也会拒绝操作。此操作不可恢复，请在联测中只对专门创建的测试项目验证。

## 环境

1. 安装 Python 3.12+、Node.js、FFmpeg 和 ffprobe。
2. 在项目根目录执行 `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`。
3. 复制 `.env.example` 为 `.env`，填写 `GOOGLE_CLOUD_PROJECT`、`GOOGLE_API_KEY` 与 `MINIMAX_API_KEY`。`GEMINI_API_KEY` 或 `GOOGLE_CLOUD_API_KEY` 仅可作为文字/图片 Cloud Key 别名。模型设为 `GOOGLE_OMNI_MODEL=gemini-omni-1.1-flash-preview`。本机执行 `gcloud auth application-default login` 获取视频 API 所需 OAuth 凭据；单次请求超时默认 120 秒，可用 `GOOGLE_HTTP_TIMEOUT_SECONDS` 调整。
4. 确认 Cloud 项目已关联持有试用赠金的结算账号，启用 Agent Platform API；Cloud Key 绑定的服务账号有权调用文字和图片模型；本机 ADC 登录账号也有权调用 Agent Platform。视频模型使用 global 位置的 Agent Platform Interactions API，符合条件的费用通过关联 Cloud Billing 结算。
5. 后端执行 `uvicorn app.main:app --host 127.0.0.1 --port 8010`；前端在 `web/` 执行 `npm install && npm run dev`。
6. 查看 `http://127.0.0.1:8010/v1/ready`，检查 Cloud 项目及 Key、视频 OAuth 所需项目与模型、MiniMax Key、FFmpeg 和 ffprobe 项。

## 完整流程

1. 分别创建普通故事和科普项目。创建输入包含首尾空格、换行和 emoji 时，检查项目原文逐字保留；纯空白输入被拒绝，超过 6000 Unicode 字符时输入不被截断且出现提示。
2. 检查导演先生成忠实剧本拆解，再生成分镜。拆解只包含原文场景、角色、地点和逐字行动/台词引用；每个镜头都显示原文出处，镜头按原文顺序覆盖内容。确认原文未被大纲、标题或镜头改写。
3. 检查短文目标镜头数、原文场景数与镜头数解耦；场景数超过目标镜头数时应明确失败并提示调整，不得合并或删改剧情来凑数。科普原文明示人类角色时应失败并保留原文；动物、昆虫等真实生物主体可作为非拟人化资产，不因科普类型被过滤。
4. 审核每个镜头的摄影说明、首尾帧描述/提示词、运动节拍和转场；角色/地点只能来自制作剧本；可编辑标题、时长、视频提示词。
5. 打开「资产」页，为普通故事上传角色和场景参考图；为科普上传真实动物/昆虫生物主体、场景或实验装置参考图。检查对应镜头自动关联；新增其他参考资产并指定镜头范围，确认它只出现在指定镜头。
6. 在分镜中分别生成首帧和尾帧，再用另一个镜头执行「一键生成首尾帧」。确认尾帧使用新生成首帧保持连续性；修改提示词或替换参考图后应显示旧结果已过期。
7. 对已生成帧再次生成并切换版本，确认历史可选；制造一次图片模型失败，确认错误显示、删除失败记录和重试可用。上传一张手动帧，确认与生成版本一致进入历史。
8. 提交单镜头与批量 Google 视频任务；观察状态轮询、失败重试、取消，并刷新页面确认状态持久。
9. 生成连续旁白；新模式的旁白请求使用原文与制作剧本，不读取旧导演大纲；检查完整句子、全片时长预算、跨镜头 cue 时间线；手动修改后保存并确认重新对齐。
10. 使用 MiniMax 生成至少两个不同语速版本，播放、切换 take，并确认所选版本与音频时长状态一致。
11. 选择硬切/叠化方案后合成成片；确认音轨完整、播放正常、时长与时间线相符，旧成片只在新成片校验成功后替换。
12. 在新的 Gemini Omni 视频任务期间重启 API，确认持久 Interaction ID 能恢复；旧 Gemini Developer 任务不会发送到新端点，应先在原平台结束旧活动任务。确认 inline 视频输出可保存并通过 ffprobe，取消时无残缺成品。
13. 在专用临时项目上检查项目列表删除：取消确认不发请求；空闲项目删除后本地项目与媒体消失；运行中的任务得到拒绝且项目仍保留；删除当前项目回到欢迎页，删除非当前项目保持当前选择。

恢复回归：有效制作剧本缓存只重跑分镜；原文/风格/类型/比例/目标镜头数变化后从原文重新拆解。旧空项目可迁移且废弃旧大纲，已有镜头、用户参考资产、首尾帧、视频、旁白或成片的旧失败项目必须拒绝自动迁移并保留内容。自动引用校验不代表摄影描述和最终生成画面不存在语义偏差，仍需人工对照原文。

## 自动检查

联合测试时再运行：

```bash
python scripts/check_provider_boundaries.py
python -m pytest -q
cd web && npm run build
```

记录模型 ID、MiniMax 模型、失败信息、耗时和成本估算；不要记录密钥。
