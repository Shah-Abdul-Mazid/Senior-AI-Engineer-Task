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

    # Database (PostgreSQL & MongoDB)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/docai"
    MONGODB_URI: str = ""
    MONGODB_DB_PROJECTS_NAME: str = "document_intelligence"
    CLUSTER_NAME: str = "Cluster0"

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

    @property
    def clean_mongodb_uri(self) -> str:
        """Ensures special characters in username/password are URL-encoded according to RFC 3986."""
        uri = self.MONGODB_URI.strip() if self.MONGODB_URI else ""
        if not uri:
            return ""
        try:
            from pymongo.uri_parser import parse_uri
            parse_uri(uri)
            return uri
        except Exception:
            pass

        import re
        import urllib.parse
        m = re.match(r"^(mongodb(?:\+srv)?://)(.*)@([^/@?]+.*)$", uri)
        if m:
            prefix = m.group(1)
            cred = m.group(2)
            rest = m.group(3)
            if ":" in cred:
                user, pwd = cred.split(":", 1)
                enc_user = urllib.parse.quote_plus(urllib.parse.unquote_plus(user))
                enc_pwd = urllib.parse.quote_plus(urllib.parse.unquote_plus(pwd))
                return f"{prefix}{enc_user}:{enc_pwd}@{rest}"
        return uri

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
