from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # OpenAI settings
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL_BASIC: str | None = None
    OPENAI_MODEL_REASONING: str | None = None

    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_MODEL_BASIC: str | None = None
    DEEPSEEK_MODEL_REASONING: str | None = None

    INFERENCE_SERVER_URL: str | None = None
    INFERENCE_SERVER_API_KEY: str | None = None
    INFERENCE_SERVER_MODEL_BASIC: str | None = None

    INFERENCE_PRIVATE_SERVER_URL: str | None = None
    INFERENCE_PRIVATE_SERVER_MODEL_BASIC: str | None = None

    # Environment settings
    DEBUG: bool = True
    SECRET_KEY: str = "your-default-secret-key"

    # Database settings
    DATABASE_URL: str = "sqlite:///db.sqlite3"

    # API settings
    API_PREFIX: str = "/api"

    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None
    REDIS_DB: int = 0

    # Cache settings
    CACHE_TTL: int = 900

    # Logging settings
    LOG_LEVEL: str = "info"
    LOG_SAVE_TO_FILE: bool = False
    LOG_FILE: str = "src/logs/app.log"
    LOG_AUTO_SETUP: bool = True

    # VAD / audio processing
    USE_ML_VAD: bool = True  # Enable VAD to filter silence before transcription
    VAD_ENGINE: str = "silero"  # Options: "silero", "ten"
    # TEN VAD settings
    VAD_TENVAD_THRESHOLD: float = 0.3  # Typhoon BE default
    VAD_TENVAD_HOP_SIZE: int = 256  # Frame hop size for TEN VAD

    # Silero VAD settings
    VAD_SILERO_THRESHOLD: float = 0.25  # VAD threshold (0-1), lower = more sensitive
    VAD_SILERO_MIN_SPEECH_MS: int = 300  # Minimum speech duration (milliseconds)
    VAD_SILERO_MIN_SILENCE_MS: int = 200  # Minimum silence to split (milliseconds)
    VAD_SILERO_SPEECH_PAD_MS: int = 100  # Padding around speech (milliseconds)

    # Common VAD settings
    VAD_MIN_SPEECH_DURATION: float = 0.3  # Minimum speech duration (seconds)
    MIN_SILENCE_DURATION: float = 0.2  # Minimum silence to split (seconds)
    VAD_PADDING_SECONDS: float = 0.1  # Padding around speech regions

    # Server Configuration
    SERVER_PORT: int = 3000
    SERVER_HOST: str = "0.0.0.0"

    # Allowed hosts
    ALLOWED_HOSTS: List[str] = ["*"]

    class Config:
        env_file = BASE_DIR / ".env"
        case_sensitive = True


settings = Settings()
