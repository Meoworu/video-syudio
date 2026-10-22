import shutil

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings


router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "ok": True,
        "service": "video-studio",
        "googleApiKeyConfigured": bool(settings.google_api_key_value),
        "googleProjectConfigured": bool(settings.google_cloud_project),
        "googleVideoApiKeyConfigured": bool(settings.google_video_api_key_value),
        "googleVideoModel": settings.google_omni_model,
        "minimaxConfigured": bool(settings.minimax_api_key),
    }


@router.get("/ready")
def readiness(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    checks = {
        "googleApiKey": bool(settings.google_api_key_value),
        "googleProject": bool(settings.google_cloud_project),
        "googleVideoApiKey": bool(settings.google_video_api_key_value),
        "googleVideoModel": settings.google_omni_model == "gemini-omni-1.1-flash",
        "minimaxKey": bool(settings.minimax_api_key),
        "ffmpeg": bool(shutil.which(settings.ffmpeg_bin)),
        "ffprobe": bool(shutil.which(settings.ffprobe_bin)),
    }
    return {"ready": all(checks.values()), "checks": checks}

