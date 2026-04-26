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
    from app.database import make_celery_session
    AsyncSessionLocal = make_celery_session()
    from app.models.tenant import Tenant, TenantConfig
    from app.models.customer import Customer
    from app.models.product import Product, ProductContent
    from app.models.bot import Conversation, Message, MessageRole, ConversationStatus, Canal
    from app.services.ai_content import generar_respuesta_bot
    from app.services.whatsapp import WhatsAppService
    from app.services.plan_limits import verificar_puede_enviar_mensaje_bot
    from app.services.dropi_service import DropiService
    from app.core.security import decrypt_secret
    from sqlalchemy import select, desc

    async with AsyncSessionLocal() as db:
        # Verificar tenant + límites de plan
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant or not tenant.activo:
            return
        try:
            await verificar_puede_enviar_mensaje_bot(tenant, db)
        except Exception:
            return  # Excedió límite — silencioso para no bombardear al cliente con errores

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

        # ── Identificar producto activo de la conversación ──
        producto_activo = None
        contenido_activo = None
        if conversacion.product_id:
            p_result = await db.execute(
                select(Product).where(Product.id == conversacion.product_id)
            )
            producto_activo = p_result.scalar_one_or_none()
        if not producto_activo:
            # Fallback: el producto más reciente con contenido generado del tenant
            p_result = await db.execute(
                select(Product)
                .where(
                    Product.tenant_id == uuid.UUID(tenant_id),
                    Product.activo == True,
                    Product.contenido_generado == True,
                )
                .order_by(desc(Product.created_at))
                .limit(1)
            )
            producto_activo = p_result.scalar_one_or_none()
            if producto_activo:
                conversacion.product_id = producto_activo.id

        if producto_activo:
            pc_result = await db.execute(
                select(ProductContent).where(ProductContent.product_id == producto_activo.id)
            )
            contenido_activo = pc_result.scalar_one_or_none()

        # ── Construir contexto rico del producto ──
        contexto_producto = _construir_contexto_producto(producto_activo, contenido_activo)

        # ── Si el cliente pregunta por envío, cotizar con Dropi e inyectar al contexto ──
        if _menciona_envio(texto) and config.dropi_api_key_enc and config.dropi_store_id:
            ciudad, departamento = _extraer_ubicacion(texto, cliente)
            if ciudad:
                try:
                    dropi_key = decrypt_secret(config.dropi_api_key_enc)
                    dropi = DropiService(dropi_key, config.dropi_store_id)
                    cotizacion = await dropi.cotizar_envio(ciudad, departamento or "")
                    if cotizacion:
                        contexto_producto += "\n\n--- INFO DE ENVÍO (consultada en Dropi ahora mismo) ---\n"
                        contexto_producto += f"Destino: {ciudad}{', ' + departamento if departamento else ''}\n"
                        for t in cotizacion["transportadoras"]:
                            contexto_producto += f"  • {t['nombre']}: ${t['valor']:,.0f} COP, entrega en {t['dias']} días\n"
                        contexto_producto += f"Rango: ${cotizacion['min']:,.0f} - ${cotizacion['max']:,.0f} COP\n"
                    else:
                        contexto_producto += f"\n\n[Aviso: Dropi no tiene cobertura confirmada en {ciudad}]"
                except Exception:
                    pass  # Si Dropi falla, el bot improvisa

        # Generar respuesta (Claude o Gemini según config del tenant)
        ai_provider = getattr(config, "ai_provider", None) or "claude"
        if ai_provider == "gemini":
            from app.services.gemini_service import generar_respuesta_bot as gemini_bot
            from app.config import settings as _settings
            gemini_key = None
            if config.gemini_api_key_enc:
                gemini_key = decrypt_secret(config.gemini_api_key_enc)
            elif _settings.gemini_api_key:
                gemini_key = _settings.gemini_api_key
            respuesta, confianza = await gemini_bot(
                historial=historial,
                contexto_producto=contexto_producto,
                api_key=gemini_key,
                model=getattr(config, "gemini_model", None),
            )
        else:
            anthropic_key = None
            if config.anthropic_api_key_enc:
                anthropic_key = decrypt_secret(config.anthropic_api_key_enc)
            respuesta, confianza = await generar_respuesta_bot(
                historial=historial,
                contexto_producto=contexto_producto,
                api_key=anthropic_key,
                model=getattr(config, "claude_model", None),
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


# ─── Helpers para construir contexto del bot ─────────────────────

def _construir_contexto_producto(producto, contenido) -> str:
    """Genera el contexto que recibe el bot para responder con info real."""
    if not producto:
        return (
            "El cliente está preguntando por nuestra tienda en general. "
            "No tienes un producto específico cargado todavía. "
            "Si pregunta por un producto puntual, indícale que lo derivarás a un asesor."
        )

    partes = [f"PRODUCTO QUE ESTÁS VENDIENDO: {producto.nombre}"]

    if producto.precio:
        partes.append(f"Precio: ${float(producto.precio):,.0f} COP")
        if producto.precio_comparacion:
            partes.append(f"Precio sin descuento: ${float(producto.precio_comparacion):,.0f} COP (¡resalta el ahorro!)")

    if producto.inventario is not None:
        if producto.inventario == 0:
            partes.append("⚠️ AGOTADO. No prometas envío inmediato; ofrece reservar para próximo lote.")
        elif producto.inventario < 10:
            partes.append(f"Solo quedan {producto.inventario} unidades — usa urgencia honesta.")
        else:
            partes.append(f"Disponible: {producto.inventario} unidades en stock.")

    if producto.descripcion_input:
        partes.append(f"\nDescripción interna del vendedor:\n{producto.descripcion_input}")

    if contenido:
        if contenido.descripcion_seo:
            partes.append(f"\nDescripción del producto (úsala como base):\n{contenido.descripcion_seo}")
        if contenido.bullet_points:
            partes.append("\nBeneficios principales:")
            for b in contenido.bullet_points:
                partes.append(f"  • {b}")
        if contenido.video_script:
            partes.append(f"\nPitch de venta de referencia:\n{contenido.video_script}")

    if producto.shopify_url:
        partes.append(f"\nLink directo de compra: {producto.shopify_url}")

    partes.append(
        "\n\nREGLAS:\n"
        "  - NO inventes características que no estén arriba\n"
        "  - NO inventes precios; usa solo el que está aquí\n"
        "  - Si te preguntan algo que no sabes, di que lo consultas con un asesor\n"
        "  - Cuando el cliente quiera comprar, pide nombre, teléfono, dirección, ciudad, departamento"
    )
    return "\n".join(partes)


_KEYWORDS_ENVIO = (
    "envio", "envío", "envias", "envías", "envia", "envía", "envian", "envían",
    "shipping", "domicilio", "entregan", "entrega",
    "cuanto vale el", "cuánto vale el", "cuanto cuesta el", "cuánto cuesta el",
    "llega a", "llegan a", "llegar a",
)


def _menciona_envio(texto: str) -> bool:
    """Heurística simple para detectar si el cliente pregunta por envío."""
    t = texto.lower()
    return any(kw in t for kw in _KEYWORDS_ENVIO)


# Ciudades principales de Colombia para extraer del texto si el cliente las menciona
_CIUDADES_CO = {
    "bogota": "Bogotá", "bogotá": "Bogotá",
    "medellin": "Medellín", "medellín": "Medellín",
    "cali": "Cali", "barranquilla": "Barranquilla",
    "cartagena": "Cartagena", "bucaramanga": "Bucaramanga",
    "pereira": "Pereira", "manizales": "Manizales",
    "cucuta": "Cúcuta", "cúcuta": "Cúcuta",
    "ibague": "Ibagué", "ibagué": "Ibagué",
    "santa marta": "Santa Marta", "armenia": "Armenia",
    "neiva": "Neiva", "pasto": "Pasto",
    "monteria": "Montería", "montería": "Montería",
    "villavicencio": "Villavicencio", "valledupar": "Valledupar",
    "popayan": "Popayán", "popayán": "Popayán",
    "tunja": "Tunja", "sincelejo": "Sincelejo",
}


def _extraer_ubicacion(texto: str, cliente=None) -> tuple[str | None, str | None]:
    """
    Intenta extraer (ciudad, departamento) del mensaje del cliente.
    Si no encuentra, usa la del cliente (si está cargada en su perfil).
    """
    t = texto.lower()
    for slug, oficial in _CIUDADES_CO.items():
        if slug in t:
            return (oficial, None)
    if cliente and cliente.ciudad:
        return (cliente.ciudad, cliente.departamento)
    return (None, None)
