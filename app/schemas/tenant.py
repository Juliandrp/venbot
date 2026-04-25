import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.models.tenant import PlanStatus


class TenantOut(BaseModel):
    id: uuid.UUID
    nombre_empresa: str
    email: EmailStr
    estado_suscripcion: PlanStatus
    activo: bool
    es_superadmin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantConfigIn(BaseModel):
    # Shopify
    shopify_store_url: str | None = None
    shopify_api_key: str | None = None
    shopify_access_token: str | None = None

    # Meta Ads
    meta_app_id: str | None = None
    meta_app_secret: str | None = None
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_pixel_id: str | None = None

    # WhatsApp
    waba_phone_number_id: str | None = None
    waba_token: str | None = None
    waba_verify_token: str | None = None

    # Dropi
    dropi_api_key: str | None = None
    dropi_store_id: str | None = None

    # SMTP
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    smtp_use_tls: bool = True

    # IA — selección de proveedor
    ai_provider: str | None = None       # claude | gemini | openai
    video_provider: str | None = None    # kling | heygen

    # IA — claves propias del tenant (opcionales, cifradas al guardar)
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    kling_api_key: str | None = None
    heygen_api_key: str | None = None
    higgsfield_api_key: str | None = None


class TenantConfigOut(BaseModel):
    # Integraciones
    shopify_store_url: str | None = None
    meta_ad_account_id: str | None = None
    meta_pixel_id: str | None = None
    waba_phone_number_id: str | None = None
    dropi_store_id: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    smtp_use_tls: bool = True
    waba_verify_token: str | None = None

    # IA — proveedores seleccionados
    ai_provider: str = "claude"
    video_provider: str = "kling"

    # Indicadores de si la key está configurada (nunca devolvemos el valor real)
    tiene_anthropic_key: bool = False
    tiene_gemini_key: bool = False
    tiene_openai_key: bool = False
    tiene_kling_key: bool = False
    tiene_heygen_key: bool = False
    tiene_higgsfield_key: bool = False

    updated_at: datetime | None = None

    model_config = {"from_attributes": False}
