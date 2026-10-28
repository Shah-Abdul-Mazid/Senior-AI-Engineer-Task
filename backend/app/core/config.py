from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-Powered Document Intelligence System"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    # Auth / Security
    SECRET_KEY: str = "change_this_to_a_super_secret_key_in_production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8

    # GenAI / LLM Settings
    OPENAI_API_KEY: str = "sk-placeholder-for-dev"
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ML / Model Settings
    ML_MODEL_NAME: str = "classifier-v1"
    ML_MODEL_PATH: str = "models/weights.bin"
    DEVICE: str = "cpu"
    MAX_BATCH_SIZE: int = 32

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/docai"

    # Redis / Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # File Storage
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [
        "pdf", "jpg", "jpeg", "png", "tiff", "tif",
        "xlsx", "xls", "csv"
    ]

    # Search & AI Processing
    VECTOR_SEARCH_TOP_K: int = 10
    MIN_CONFIDENCE_SCORE: float = 0.6

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
