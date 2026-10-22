# video-studio

Google Cloud Agent Platform video studio with MiniMax continuous narration.

The project is intentionally independent from `comfyui-worker`.

## Providers

- Google Cloud Agent Platform API: director planning and narration manuscript; Gemini Developer API: Omni video generation.
- MiniMax Speech: continuous narration audio only.
- Local FFmpeg/ffprobe: validates generated clips and assembles ordered shots with the MiniMax narration track.

The web app is served separately during development; Vite proxies `/v1` to the API on port 8010. Uploaded assets and frames, generated clips, narration audio, and the assembled `final/final.mp4` are available through the project files API. Install FFmpeg and ffprobe on the host before assembling a project.

If FFmpeg is not on `PATH`, set `FFMPEG_BIN` and `FFPROBE_BIN` in `.env` to their executable paths.

The director preserves the submitted story as-is, breaks it into source-linked production scenes, then plans shots against both the original text and the breakdown. It does not create a rewritten synopsis or change the project story. Each new shot shows its source excerpt. The continuous narration is sentence-based, aligned deterministically to the edit timeline, and voiced only with MiniMax Speech. Text and image generation use a service-account-bound Google Cloud API key through Agent Platform. Omni video uses the Gemini Developer API and its separate `GOOGLE_VIDEO_API_KEY` with `gemini-omni-1.1-flash`; it does not use ADC or the Cloud project key. See [the acceptance runbook](docs/acceptance-runbook.md) for joint testing.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_API_KEY`, `GOOGLE_VIDEO_API_KEY`, and `MINIMAX_API_KEY` in `.env`. The Cloud project must be linked to the billing account holding your trial credits, with Agent Platform API enabled and the bound service account authorized. Keep `GOOGLE_API_KEY` restricted to Agent Platform API; `GEMINI_API_KEY` and `GOOGLE_CLOUD_API_KEY` remain aliases for text and image requests only. Create `GOOGLE_VIDEO_API_KEY` for the Gemini Developer API, restrict it to Generative Language API, and use it only for `gemini-omni-1.1-flash`. Video API usage has separate billing and is not covered by Google Cloud trial credits. Image generation uses the Cloud key and project with `GOOGLE_IMAGE_MODEL` (default `gemini-3.1-flash-image`), `GOOGLE_IMAGE_RESOLUTION` (default `1K`), `GOOGLE_IMAGE_TIMEOUT_SECONDS` (default 180), and `GOOGLE_IMAGE_MAX_CONCURRENCY` (default 2). Other Google requests time out after 120 seconds by default; set `GOOGLE_HTTP_TIMEOUT_SECONDS` to change this.

When creating a project, choose **普通故事** or **科普**. Science projects use an object and process focused outline, omit character roles, and append no-human constraints to frame, video, and narration generation; uploaded reference images should also avoid people. Project type is fixed after creation, while older projects default to ordinary story. Upload character/location references for stories, or scene/object/experiment references for science projects in the **Assets** tab. The shot workspace automatically associates matching assets; edit the first/last frame prompts and generate either frame or both in sequence. Generated versions remain selectable, and successful frames feed the existing video generation flow. See [local development](dev.md) and the [acceptance runbook](docs/acceptance-runbook.md) for the workflow.

Projects can be permanently deleted from the project list after confirmation. This removes the local project directory and media; running jobs are rejected, and the delete action does not cancel remote provider jobs.

Run the API:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In another terminal, run the web app from `web/` using `npm install` followed by `npm run dev`.

Run tests:

```bash
.venv/bin/python -m pytest -q
```


Google Cloud trial credits apply only to eligible usage under the linked billing account; they do not pay for AI Studio Gemini API usage. Check credit balance and expiry in Cloud Billing. This app does not verify credit eligibility or automatically upgrade billing. See [the Agent Platform integration notes](docs/agent-platform-api-key-development.md).

Video requests use Gemini Files URI delivery with inline output compatibility. Older Vertex ADC, Agent Platform, and Gemini Developer task IDs remain readable but cannot be resumed or cancelled through the new client. Finish them through their original provider before resubmitting.
