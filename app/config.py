from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",        # ignora vars del .env que no estén definidas aquí
    )

    # App
    secret_key: str = Field(..., env="SECRET_KEY")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    environment: str = "development"
    app_base_url: str = "http://localhost:8000"

    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    sync_database_url: str = Field(..., env="SYNC_DATABASE_URL")

    # Redis / Celery
    redis_url: str = Field(..., env="REDIS_URL")
    celery_broker_url: str = Field(..., env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(..., env="CELERY_RESULT_BACKEND")

    # Cifrado de secretos de tenants
    encryption_key: str = Field(..., env="ENCRYPTION_KEY")

    # IA (opcionales — se puede configurar por tenant en BD)
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")

    # Super-admin (se crea automáticamente al iniciar)
    superadmin_email: str = Field(default="admin@venbot.io", env="SUPERADMIN_EMAIL")
    superadmin_password: str = Field(default="changeme", env="SUPERADMIN_PASSWORD")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
