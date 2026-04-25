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


@router.get("/uso")
async def mi_uso(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Uso actual vs límite del plan, para mostrar en UI."""
    from app.services.plan_limits import obtener_uso_actual
    return await obtener_uso_actual(tenant, db)


@router.get("/planes-disponibles")
async def planes_disponibles(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Planes activos que el tenant puede contratar."""
    from app.models.tenant import SubscriptionPlan
    result = await db.execute(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.activo == True)
        .order_by(SubscriptionPlan.precio_mensual.asc())
    )
    planes = result.scalars().all()
    return {
        "plan_actual_id": tenant.plan_id,
        "estado": tenant.estado_suscripcion.value,
        "planes": [
            {
                "id": p.id,
                "nombre": p.nombre,
                "tier": p.tier.value,
                "precio_mensual_usd": p.precio_mensual / 100.0,
                "max_productos": p.max_productos,
                "max_campanas": p.max_campanas,
                "max_mensajes_bot": p.max_mensajes_bot,
                "actual": p.id == tenant.plan_id,
            }
            for p in planes
        ],
    }


@router.post("/upgrade-plan")
async def upgrade_plan(
    payload: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Cambia el plan del tenant. En producción esto debería integrarse con
    Stripe/MercadoPago/PayPal. Por ahora marca el plan como activo.
    """
    from app.models.tenant import SubscriptionPlan, PlanStatus
    plan_id = (payload or {}).get("plan_id")
    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id es obligatorio")

    plan_check = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == int(plan_id), SubscriptionPlan.activo == True)
    )
    plan = plan_check.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado o inactivo")

    tenant.plan_id = plan.id
    tenant.estado_suscripcion = PlanStatus.active
    await db.commit()
    return {"mensaje": "Plan activado", "plan": plan.nombre}


@router.get("/config", response_model=TenantConfigOut)
async def obtener_config(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = result.scalar_one_or_none()
    if not config:
        # Devolver configuración vacía con defaults
        return TenantConfigOut(updated_at=None)
    return _config_to_out(config)


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

    # Campos de texto plano
    _plain = [
        ("shopify_store_url", "shopify_store_url"),
        ("meta_ad_account_id", "meta_ad_account_id"),
        ("meta_pixel_id", "meta_pixel_id"),
        ("waba_phone_number_id", "waba_phone_number_id"),
        ("waba_verify_token", "waba_verify_token"),
        ("dropi_store_id", "dropi_store_id"),
        ("smtp_host", "smtp_host"),
        ("smtp_port", "smtp_port"),
        ("smtp_user", "smtp_user"),
        ("smtp_from_email", "smtp_from_email"),
        ("smtp_from_name", "smtp_from_name"),
    ]
    for in_field, model_field in _plain:
        value = getattr(data, in_field, None)
        if value is not None:
            setattr(config, model_field, value)

    config.smtp_use_tls = data.smtp_use_tls

    # Proveedores IA
    if data.ai_provider in ("claude", "gemini", "openai"):
        config.ai_provider = data.ai_provider
    if data.video_provider in ("kling", "heygen", "higgsfield"):
        config.video_provider = data.video_provider

    # Campos cifrados
    _enc = [
        ("shopify_api_key",     "shopify_api_key_enc"),
        ("shopify_access_token","shopify_access_token_enc"),
        ("meta_app_id",         "meta_app_id_enc"),
        ("meta_app_secret",     "meta_app_secret_enc"),
        ("meta_access_token",   "meta_access_token_enc"),
        ("waba_token",          "waba_token_enc"),
        ("dropi_api_key",       "dropi_api_key_enc"),
        ("smtp_password",       "smtp_password_enc"),
        ("anthropic_api_key",   "anthropic_api_key_enc"),
        ("gemini_api_key",      "gemini_api_key_enc"),
        ("openai_api_key",      "openai_api_key_enc"),
        ("kling_api_key",       "kling_api_key_enc"),
        ("heygen_api_key",      "heygen_api_key_enc"),
        ("higgsfield_api_key",  "higgsfield_api_key_enc"),
    ]
    for in_field, model_field in _enc:
        value = getattr(data, in_field, None)
        if value:
            setattr(config, model_field, encrypt_secret(value))

    await db.commit()
    await db.refresh(config)
    return _config_to_out(config)


def _config_to_out(config: TenantConfig) -> TenantConfigOut:
    return TenantConfigOut(
        shopify_store_url=config.shopify_store_url,
        meta_ad_account_id=config.meta_ad_account_id,
        meta_pixel_id=config.meta_pixel_id,
        waba_phone_number_id=config.waba_phone_number_id,
        waba_verify_token=config.waba_verify_token,
        dropi_store_id=config.dropi_store_id,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_from_email=config.smtp_from_email,
        smtp_from_name=config.smtp_from_name,
        smtp_use_tls=config.smtp_use_tls,
        ai_provider=config.ai_provider or "claude",
        video_provider=config.video_provider or "kling",
        tiene_anthropic_key=bool(config.anthropic_api_key_enc),
        tiene_gemini_key=bool(config.gemini_api_key_enc),
        tiene_openai_key=bool(config.openai_api_key_enc),
        tiene_kling_key=bool(config.kling_api_key_enc),
        tiene_heygen_key=bool(config.heygen_api_key_enc),
        tiene_higgsfield_key=bool(config.higgsfield_api_key_enc),
        updated_at=config.updated_at,
    )
