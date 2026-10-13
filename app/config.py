from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    app_port: int = Field(default=8010, alias="APP_PORT")
    video_studio_data_dir: Path = Field(default=Path("downloads/projects"), alias="VIDEO_STUDIO_DATA_DIR")
    google_cloud_project: str = Field(default="", alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="global", alias="GOOGLE_CLOUD_LOCATION")
    google_application_credentials: Path | None = Field(default=None, alias="GOOGLE_APPLICATION_CREDENTIALS")
    google_text_model: str = Field(default="gemini-3.6-flash", alias="GOOGLE_TEXT_MODEL")
    google_omni_model: str = Field(default="gemini-omni-flash-preview", alias="GOOGLE_OMNI_MODEL")
    google_request_timeout_seconds: float = Field(default=900.0, gt=0, alias="GOOGLE_REQUEST_TIMEOUT_SECONDS")
    google_poll_interval_seconds: float = Field(default=5.0, gt=0, alias="GOOGLE_POLL_INTERVAL_SECONDS")
    google_text_max_retries: int = Field(default=2, ge=0, le=5, alias="GOOGLE_TEXT_MAX_RETRIES")
    retry_backoff_seconds: float = Field(default=0.8, gt=0, le=10, alias="RETRY_BACKOFF_SECONDS")
    minimax_api_key: str | None = Field(default=None, alias="MINIMAX_API_KEY")
    minimax_speech_url: str = Field(default="https://api.minimaxi.com/v1/t2a_v2", alias="MINIMAX_SPEECH_URL")
    minimax_speech_model: str = Field(default="speech-2.8-hd", alias="MINIMAX_SPEECH_MODEL")
    minimax_speech_voice_id: str = Field(default="male-qn-qingse", alias="MINIMAX_SPEECH_VOICE_ID")
    minimax_speech_timeout_seconds: float = Field(default=180.0, gt=0, alias="MINIMAX_SPEECH_TIMEOUT_SECONDS")
    minimax_max_retries: int = Field(default=2, ge=0, le=5, alias="MINIMAX_MAX_RETRIES")
    ffmpeg_bin: str = Field(default="ffmpeg", alias="FFMPEG_BIN")
    ffprobe_bin: str = Field(default="ffprobe", alias="FFPROBE_BIN")

    @field_validator("google_application_credentials", mode="before")
    @classmethod
    def blank_credentials_path_uses_adc(cls, value: object) -> object:
        return None if value is None or (isinstance(value, str) and not value.strip()) else value


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.video_studio_data_dir.mkdir(parents=True, exist_ok=True)
    return settings

