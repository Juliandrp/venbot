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
    kling_api_key: str = Field(default="", env="KLING_API_KEY")
    higgsfield_api_key: str = Field(default="", env="HIGGSFIELD_API_KEY")

    # Super-admin (se crea automáticamente al iniciar)
    superadmin_email: str = Field(default="admin@venbot.io", env="SUPERADMIN_EMAIL")
    superadmin_password: str = Field(default="changeme", env="SUPERADMIN_PASSWORD")

    # Storage — backend para imágenes/videos generados
    # "local" = disco del contenedor (con volumen persistente en producción)
    # "s3"    = bucket S3-compatible (AWS S3, R2, MinIO, etc.)
    storage_backend: str = Field(default="local", env="STORAGE_BACKEND")
    storage_local_path: str = Field(default="/app/media", env="STORAGE_LOCAL_PATH")
    storage_local_base_url: str = Field(default="/media", env="STORAGE_LOCAL_BASE_URL")

    # S3 / R2 / MinIO (solo si storage_backend == "s3")
    s3_endpoint_url: str = Field(default="", env="S3_ENDPOINT_URL")
    s3_access_key: str = Field(default="", env="S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", env="S3_SECRET_KEY")
    s3_bucket: str = Field(default="", env="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", env="S3_REGION")
    s3_public_base_url: str = Field(default="", env="S3_PUBLIC_BASE_URL")

    # Pagos
    # "" = pagos deshabilitados | "stripe" | "mercadopago"
    payment_provider: str = Field(default="", env="PAYMENT_PROVIDER")
    stripe_secret_key: str = Field(default="", env="STRIPE_SECRET_KEY")
    stripe_webhook_secret: str = Field(default="", env="STRIPE_WEBHOOK_SECRET")
    mercadopago_access_token: str = Field(default="", env="MERCADOPAGO_ACCESS_TOKEN")
    mercadopago_webhook_secret: str = Field(default="", env="MERCADOPAGO_WEBHOOK_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
