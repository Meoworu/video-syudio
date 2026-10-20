# video-studio

Google Gemini video studio with MiniMax continuous narration.

The project is intentionally independent from `comfyui-worker`.

## Providers

- Google Gemini Developer API: director planning, narration manuscript, and Gemini Omni video generation.
- MiniMax Speech: continuous narration audio only.
- Local FFmpeg/ffprobe: validates generated clips and assembles ordered shots with the MiniMax narration track.

The web app is served separately during development; Vite proxies `/v1` to the API on port 8010. Uploaded frames, generated clips, narration audio, and the assembled `final/final.mp4` are available through the project files API. Install FFmpeg and ffprobe on the host before assembling a project.

If FFmpeg is not on `PATH`, set `FFMPEG_BIN` and `FFPROBE_BIN` in `.env` to their executable paths.

The director uses a Google outline stage followed by a Google shot-planning stage. The continuous narration is sentence-based, aligned deterministically to the edit timeline, and voiced only with MiniMax Speech. Google calls use a Gemini Developer API key; Vertex AI project, location, and ADC settings are not required. See [the acceptance runbook](docs/acceptance-runbook.md) for joint testing.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set `GOOGLE_API_KEY` and `MINIMAX_API_KEY` in `.env`. `GEMINI_API_KEY` and `GOOGLE_CLOUD_API_KEY` are accepted as fallback names. The key is only used by the backend. Individual Google requests time out after 120 seconds by default; set `GOOGLE_HTTP_TIMEOUT_SECONDS` to change this.

Run the API:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In another terminal, run the web app from `web/` using `npm install` followed by `npm run dev`.

Run tests:

```bash
.venv/bin/python -m pytest -q
```

