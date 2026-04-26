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


@router.get("/conversaciones/{conv_id}/mensajes")
async def listar_mensajes(
    conv_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    from app.models.bot import Message
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == uuid.UUID(conv_id),
            Conversation.tenant_id == tenant.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    msgs = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
    )
    return list(msgs.scalars().all())


@router.post("/conversaciones/{conv_id}/responder", status_code=201)
async def responder_conversacion(
    conv_id: str,
    payload: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Envía un mensaje del agente humano al cliente.

    Modos según `tomar_control`:
      - False (default — "Asistir"): mensaje sale al cliente, conversación
        queda activa, el bot sigue respondiendo siguientes mensajes con
        este texto en el historial como contexto.
      - True ("Tomar control"): conversación pasa a 'transferida', el bot
        deja de responder hasta que se cierre.
    """
    import uuid
    from app.models.bot import Message, MessageRole, ConversationStatus, Canal
    from app.models.customer import Customer
    from app.core.security import decrypt_secret

    payload = payload or {}
    texto = (payload.get("texto") or "").strip()
    tomar_control = bool(payload.get("tomar_control", False))
    if not texto:
        raise HTTPException(status_code=400, detail="El texto del mensaje es obligatorio")

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == uuid.UUID(conv_id),
            Conversation.tenant_id == tenant.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    config_result = await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant.id)
    )
    config = config_result.scalar_one_or_none()

    cust_result = await db.execute(select(Customer).where(Customer.id == conv.customer_id))
    cliente = cust_result.scalar_one_or_none()

    meta_message_id = None
    error_envio = None

    # Enviar al canal externo
    if conv.canal == Canal.whatsapp:
        if not config or not config.waba_phone_number_id or not config.waba_token_enc:
            error_envio = "WhatsApp no configurado en Configuración"
        elif not cliente or not cliente.whatsapp_id:
            error_envio = "Cliente sin whatsapp_id"
        else:
            try:
                from app.services.whatsapp import WhatsAppService
                token = decrypt_secret(config.waba_token_enc)
                wa = WhatsAppService(config.waba_phone_number_id, token)
                meta_message_id = await wa.enviar_texto(cliente.whatsapp_id, texto)
            except Exception as e:
                error_envio = f"Error al enviar a WhatsApp: {str(e)[:200]}"

    # Guardar el mensaje localmente aunque falle el envío
    msg = Message(
        conversation_id=conv.id,
        tenant_id=tenant.id,
        rol=MessageRole.humano,
        contenido=texto,
        meta_message_id=meta_message_id,
    )
    db.add(msg)
    # Solo cambiar a 'transferida' si el agente quiere tomar control total.
    # En modo asistir, conversación queda activa y el bot sigue respondiendo.
    if tomar_control:
        conv.estado = ConversationStatus.transferida
    await db.commit()
    await db.refresh(msg)

    return {
        "id": msg.id,
        "rol": msg.rol.value,
        "contenido": msg.contenido,
        "created_at": msg.created_at.isoformat(),
        "enviado_externo": meta_message_id is not None,
        "error": error_envio,
        "estado_conversacion": conv.estado.value,
    }


@router.post("/conversaciones/{conv_id}/cerrar")
async def cerrar_conversacion(
    conv_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    from app.models.bot import ConversationStatus
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == uuid.UUID(conv_id),
            Conversation.tenant_id == tenant.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv.estado = ConversationStatus.cerrada
    await db.commit()
    return {"mensaje": "Conversación cerrada"}
