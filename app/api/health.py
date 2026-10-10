from fastapi import APIRouter, Depends

from app.config import Settings, get_settings


router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "ok": True,
        "service": "video-studio",
        "googleProjectConfigured": bool(settings.google_cloud_project),
        "minimaxConfigured": bool(settings.minimax_api_key),
    }

