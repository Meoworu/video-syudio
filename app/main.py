from fastapi import FastAPI

from app.api.health import router as health_router


app = FastAPI(
    title="video-studio",
    version="0.1.0",
    description="Google Vertex AI video studio with MiniMax continuous narration.",
)
app.include_router(health_router, prefix="/v1")

