# video-studio

Google Vertex AI video studio with MiniMax continuous narration.

The project is intentionally independent from `comfyui-worker`.

## Providers

- Google Vertex AI + ADC: director planning, narration manuscript, and Gemini Omni video generation.
- MiniMax Speech: continuous narration audio only.
- Local FFmpeg/ffprobe: media inspection, mixing, and final assembly.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
gcloud auth application-default login
```

Run the API:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Run tests:

```bash
.venv/bin/python -m pytest -q
```

