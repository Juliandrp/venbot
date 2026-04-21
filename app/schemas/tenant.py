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

    # AI keys opcionales
    anthropic_api_key: str | None = None
    heygen_api_key: str | None = None


class TenantConfigOut(BaseModel):
    shopify_store_url: str | None
    meta_ad_account_id: str | None
    meta_pixel_id: str | None
    waba_phone_number_id: str | None
    dropi_store_id: str | None
    smtp_host: str | None
    smtp_from_email: str | None
    smtp_from_name: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}
