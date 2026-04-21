from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.deps import get_current_tenant
from app.core.security import encrypt_secret
from app.models.tenant import Tenant, TenantConfig
from app.schemas.tenant import TenantOut, TenantConfigIn, TenantConfigOut

router = APIRouter(prefix="/tenant", tags=["Tenant"])


@router.get("/me", response_model=TenantOut)
async def mi_perfil(tenant: Tenant = Depends(get_current_tenant)):
    return tenant


@router.get("/config", response_model=TenantConfigOut)
async def obtener_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Configuración no encontrada")
    return config


@router.put("/config", response_model=TenantConfigOut)
async def actualizar_config(
    data: TenantConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = result.scalar_one_or_none()
    if not config:
        config = TenantConfig(tenant_id=tenant.id)
        db.add(config)

    # Campos no sensibles
    if data.shopify_store_url is not None:
        config.shopify_store_url = data.shopify_store_url
    if data.meta_ad_account_id is not None:
        config.meta_ad_account_id = data.meta_ad_account_id
    if data.meta_pixel_id is not None:
        config.meta_pixel_id = data.meta_pixel_id
    if data.waba_phone_number_id is not None:
        config.waba_phone_number_id = data.waba_phone_number_id
    if data.waba_verify_token is not None:
        config.waba_verify_token = data.waba_verify_token
    if data.dropi_store_id is not None:
        config.dropi_store_id = data.dropi_store_id
    if data.smtp_host is not None:
        config.smtp_host = data.smtp_host
    if data.smtp_port is not None:
        config.smtp_port = data.smtp_port
    if data.smtp_user is not None:
        config.smtp_user = data.smtp_user
    if data.smtp_from_email is not None:
        config.smtp_from_email = data.smtp_from_email
    if data.smtp_from_name is not None:
        config.smtp_from_name = data.smtp_from_name
    config.smtp_use_tls = data.smtp_use_tls

    # Campos cifrados
    _enc_fields = [
        ("shopify_api_key", "shopify_api_key_enc"),
        ("shopify_access_token", "shopify_access_token_enc"),
        ("meta_app_id", "meta_app_id_enc"),
        ("meta_app_secret", "meta_app_secret_enc"),
        ("meta_access_token", "meta_access_token_enc"),
        ("waba_token", "waba_token_enc"),
        ("dropi_api_key", "dropi_api_key_enc"),
        ("smtp_password", "smtp_password_enc"),
        ("anthropic_api_key", "anthropic_api_key_enc"),
        ("heygen_api_key", "heygen_api_key_enc"),
    ]
    for input_field, model_field in _enc_fields:
        value = getattr(data, input_field, None)
        if value:
            setattr(config, model_field, encrypt_secret(value))

    await db.commit()
    await db.refresh(config)
    return config
