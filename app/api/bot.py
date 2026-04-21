"""Webhooks de WhatsApp y Messenger + endpoints del bot."""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant, TenantConfig
from app.models.bot import Conversation
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/bot", tags=["Bot de Ventas"])


# ─── Webhook WhatsApp ────────────────────────────────────────

@router.get("/whatsapp/webhook/{tenant_id}")
async def verificar_webhook_whatsapp(
    tenant_id: str,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    db: AsyncSession = Depends(get_db),
):
    """Verificación del webhook de Meta para WhatsApp Business."""
    from app.models.tenant import TenantConfig
    import uuid
    result = await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == uuid.UUID(tenant_id))
    )
    config = result.scalar_one_or_none()
    if not config or config.waba_verify_token != hub_verify_token:
        raise HTTPException(status_code=403, detail="Token de verificación inválido")
    if hub_mode == "subscribe":
        return int(hub_challenge)
    raise HTTPException(status_code=400, detail="Modo inválido")


@router.post("/whatsapp/webhook/{tenant_id}")
async def recibir_mensaje_whatsapp(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Recibe mensajes entrantes de WhatsApp Business."""
    payload = await request.json()
    from app.workers.bot_processor import procesar_mensaje_whatsapp
    procesar_mensaje_whatsapp.delay(tenant_id, payload)
    return {"status": "ok"}


# ─── Webhook Messenger ───────────────────────────────────────

@router.get("/messenger/webhook/{tenant_id}")
async def verificar_webhook_messenger(
    tenant_id: str,
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    db: AsyncSession = Depends(get_db),
):
    from app.models.tenant import TenantConfig
    import uuid
    result = await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == uuid.UUID(tenant_id))
    )
    config = result.scalar_one_or_none()
    if not config or config.waba_verify_token != hub_verify_token:
        raise HTTPException(status_code=403, detail="Token de verificación inválido")
    if hub_mode == "subscribe":
        return int(hub_challenge)
    raise HTTPException(status_code=400, detail="Modo inválido")


@router.post("/messenger/webhook/{tenant_id}")
async def recibir_mensaje_messenger(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    from app.workers.bot_processor import procesar_mensaje_messenger
    procesar_mensaje_messenger.delay(tenant_id, payload)
    return {"status": "ok"}


# ─── Endpoints de gestión (autenticados) ─────────────────────

@router.get("/conversaciones")
async def listar_conversaciones(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.tenant_id == tenant.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())
