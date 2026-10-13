# video-studio

Google Vertex AI video studio with MiniMax continuous narration.

The project is intentionally independent from `comfyui-worker`.

## Providers

- Google Vertex AI + ADC: director planning, narration manuscript, and Gemini Omni video generation.
- MiniMax Speech: continuous narration audio only.
- Local FFmpeg/ffprobe: validates generated clips and assembles ordered shots with the MiniMax narration track.

The web app is served separately during development; Vite proxies `/v1` to the API on port 8010. Uploaded frames, generated clips, narration audio, and the assembled `final/final.mp4` are available through the project files API. Install FFmpeg and ffprobe on the host before assembling a project.

If FFmpeg is not on `PATH`, set `FFMPEG_BIN` and `FFPROBE_BIN` in `.env` to their executable paths.

The director uses a Google outline stage followed by a Google shot-planning stage. The continuous narration is sentence-based, aligned deterministically to the edit timeline, and voiced only with MiniMax Speech. Gemini Omni video currently requires the `global` Vertex AI location; readiness reports if another location is configured. See [the acceptance runbook](docs/acceptance-runbook.md) for the later joint test; the migration itself has not made real provider calls.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
gcloud auth application-default login
```

Set `GOOGLE_CLOUD_PROJECT` and `MINIMAX_API_KEY` in `.env`. Keep `GOOGLE_CLOUD_LOCATION=global` for Gemini Omni video generation.

Run the API:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

In another terminal, run the web app from `web/` using `npm install` followed by `npm run dev`.

Run tests:

```bash
.venv/bin/python -m pytest -q
```

