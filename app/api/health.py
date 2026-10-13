import shutil

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


@router.get("/ready")
def readiness(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    try:
        from app.clients.google_vertex import load_vertex_runtime
        load_vertex_runtime(settings)
        adc_ready = True
    except Exception:
        adc_ready = False
    checks = {
        "googleProject": bool(settings.google_cloud_project),
        "googleAdc": adc_ready,
        "googleVideoLocationGlobal": settings.google_cloud_location.strip().lower() == "global",
        "minimaxKey": bool(settings.minimax_api_key),
        "ffmpeg": bool(shutil.which(settings.ffmpeg_bin)),
        "ffprobe": bool(shutil.which(settings.ffprobe_bin)),
    }
    return {"ready": all(checks.values()), "checks": checks}

