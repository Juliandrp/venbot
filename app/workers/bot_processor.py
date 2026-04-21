"""Worker: procesamiento de mensajes entrantes del bot de ventas."""
import asyncio
from app.celery_app import celery_app


@celery_app.task(name="app.workers.bot_processor.procesar_mensaje_whatsapp", bind=True, max_retries=3)
def procesar_mensaje_whatsapp(self, tenant_id: str, payload: dict):
    asyncio.run(_procesar_wa(tenant_id, payload))


@celery_app.task(name="app.workers.bot_processor.procesar_mensaje_messenger", bind=True, max_retries=3)
def procesar_mensaje_messenger(self, tenant_id: str, payload: dict):
    asyncio.run(_procesar_messenger(tenant_id, payload))


async def _procesar_wa(tenant_id: str, payload: dict):
    """Procesa un webhook de WhatsApp y genera respuesta del bot."""
    try:
        entry = payload.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0].get("value", {})
        messages = changes.get("messages", [])
        if not messages:
            return
        msg = messages[0]
        sender_id = msg.get("from")
        text = msg.get("text", {}).get("body", "")
        if not text or not sender_id:
            return
    except (IndexError, KeyError):
        return

    await _responder_bot(tenant_id, sender_id, text, canal="whatsapp")


async def _procesar_messenger(tenant_id: str, payload: dict):
    try:
        entry = payload.get("entry", [{}])[0]
        messaging = entry.get("messaging", [{}])[0]
        sender_id = messaging.get("sender", {}).get("id")
        text = messaging.get("message", {}).get("text", "")
        if not text or not sender_id:
            return
    except (IndexError, KeyError):
        return

    await _responder_bot(tenant_id, sender_id, text, canal="messenger")


async def _responder_bot(tenant_id: str, external_user_id: str, texto: str, canal: str):
    import uuid
    from app.database import AsyncSessionLocal
    from app.models.tenant import TenantConfig
    from app.models.customer import Customer
    from app.models.bot import Conversation, Message, MessageRole, ConversationStatus, Canal
    from app.services.ai_content import generar_respuesta_bot
    from app.services.whatsapp import WhatsAppService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        config_result = await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == uuid.UUID(tenant_id))
        )
        config = config_result.scalar_one_or_none()
        if not config:
            return

        # Buscar o crear cliente
        campo_id = "whatsapp_id" if canal == "whatsapp" else "messenger_id"
        cust_result = await db.execute(
            select(Customer).where(
                Customer.tenant_id == uuid.UUID(tenant_id),
                getattr(Customer, campo_id) == external_user_id,
            )
        )
        cliente = cust_result.scalar_one_or_none()
        if not cliente:
            cliente = Customer(
                tenant_id=uuid.UUID(tenant_id),
                **{campo_id: external_user_id},
            )
            db.add(cliente)
            await db.flush()

        # Buscar conversación activa o crear una nueva
        conv_result = await db.execute(
            select(Conversation).where(
                Conversation.tenant_id == uuid.UUID(tenant_id),
                Conversation.customer_id == cliente.id,
                Conversation.estado == ConversationStatus.activa,
            )
        )
        conversacion = conv_result.scalar_one_or_none()
        if not conversacion:
            conversacion = Conversation(
                tenant_id=uuid.UUID(tenant_id),
                customer_id=cliente.id,
                canal=Canal(canal),
            )
            db.add(conversacion)
            await db.flush()

        # Guardar mensaje del cliente
        msg_cliente = Message(
            conversation_id=conversacion.id,
            tenant_id=uuid.UUID(tenant_id),
            rol=MessageRole.cliente,
            contenido=texto,
        )
        db.add(msg_cliente)

        # Si está transferida a humano, no responder con bot
        if conversacion.estado == ConversationStatus.transferida:
            await db.commit()
            return

        # Cargar historial para contexto
        hist_result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversacion.id)
            .order_by(Message.created_at.asc())
            .limit(30)
        )
        historial = [
            {"rol": "user" if m.rol == MessageRole.cliente else "assistant", "contenido": m.contenido}
            for m in hist_result.scalars().all()
        ]

        # Obtener API key
        anthropic_key = None
        if config.anthropic_api_key_enc:
            anthropic_key = decrypt_secret(config.anthropic_api_key_enc)

        # Generar respuesta
        respuesta, confianza = await generar_respuesta_bot(
            historial=historial,
            contexto_producto="Tienda de e-commerce",  # Se enriquece si hay producto en la conversación
            api_key=anthropic_key,
        )

        # Guardar respuesta del bot
        msg_bot = Message(
            conversation_id=conversacion.id,
            tenant_id=uuid.UUID(tenant_id),
            rol=MessageRole.bot,
            contenido=respuesta,
            confianza=confianza,
        )
        db.add(msg_bot)

        # Transferir a humano si confianza baja
        if confianza < 0.5:
            conversacion.estado = ConversationStatus.transferida

        await db.commit()

        # Enviar respuesta vía WhatsApp
        if canal == "whatsapp" and config.waba_token_enc and config.waba_phone_number_id:
            waba_token = decrypt_secret(config.waba_token_enc)
            wa = WhatsAppService(config.waba_phone_number_id, waba_token)
            await wa.enviar_texto(external_user_id, respuesta)
