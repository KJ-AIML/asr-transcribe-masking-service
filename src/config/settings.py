from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # OpenAI settings
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL_BASIC: str | None = None
    OPENAI_MODEL_REASONING: str | None = None

    # Environment settings
    DEBUG: bool = False
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

    # Server Configuration
    SERVER_PORT: int = 3000
    SERVER_HOST: str = "0.0.0.0"

    # Allowed hosts
    ALLOWED_HOSTS: List[str] = ["*"]

    class Config:
        env_file = BASE_DIR / ".env"
        case_sensitive = True


settings = Settings()
