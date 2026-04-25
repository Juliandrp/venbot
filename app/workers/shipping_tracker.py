"""Worker: rastreo de envíos Dropi y notificaciones al cliente."""
import asyncio
from app.celery_app import celery_app

DROPI_A_INTERNO = {
    "pending": "pendiente",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "in_transit": "en_camino",
    "delivered": "entregado",
    "failed": "fallido",
}


@celery_app.task(name="app.workers.shipping_tracker.track_all_shipments", bind=True)
def track_all_shipments(self):
    asyncio.run(_track())


async def _track():
    from app.database import make_celery_session
    AsyncSessionLocal = make_celery_session()
    from app.models.order import Order, OrderStatus, ShipmentEvent, ShipmentEventType
    from app.models.tenant import TenantConfig
    from app.models.customer import Customer
    from app.services.dropi_service import DropiService
    from app.services.whatsapp import WhatsAppService
    from app.services.email_service import EmailService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    estados_finales = {OrderStatus.entregado, OrderStatus.cancelado, OrderStatus.fallido}

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Order).where(
                Order.dropi_order_id.isnot(None),
                Order.estado.notin_(list(estados_finales)),
            )
        )
        pedidos = result.scalars().all()

        for pedido in pedidos:
            try:
                c_result = await db.execute(
                    select(TenantConfig).where(TenantConfig.tenant_id == pedido.tenant_id)
                )
                config = c_result.scalar_one_or_none()
                if not config or not config.dropi_api_key_enc:
                    continue

                dropi_key = decrypt_secret(config.dropi_api_key_enc)
                dropi = DropiService(dropi_key, config.dropi_store_id or "")
                info = await dropi.consultar_estado(pedido.dropi_order_id)

                nuevo_estado_str = DROPI_A_INTERNO.get(info["estado"], "")
                nuevo_estado = OrderStatus(nuevo_estado_str) if nuevo_estado_str else None

                if not nuevo_estado or nuevo_estado == pedido.estado:
                    continue

                # Actualizar pedido
                pedido.estado = nuevo_estado
                if info.get("numero_seguimiento"):
                    pedido.numero_seguimiento = info["numero_seguimiento"]
                if info.get("transportadora"):
                    pedido.transportadora = info["transportadora"]

                # Guardar evento de envío
                tipo_map = {
                    "confirmado": ShipmentEventType.confirmado,
                    "enviado": ShipmentEventType.enviado,
                    "en_camino": ShipmentEventType.en_camino,
                    "entregado": ShipmentEventType.entregado,
                    "fallido": ShipmentEventType.fallido,
                }
                evento = ShipmentEvent(
                    order_id=pedido.id,
                    tenant_id=pedido.tenant_id,
                    tipo=tipo_map.get(nuevo_estado_str, ShipmentEventType.otro),
                    descripcion=f"Estado actualizado: {nuevo_estado_str}",
                    ubicacion=info.get("ubicacion"),
                )
                db.add(evento)

                # Notificar al cliente
                cliente_result = await db.execute(select(Customer).where(Customer.id == pedido.customer_id))
                cliente = cliente_result.scalar_one_or_none()

                if cliente and config.waba_token_enc and config.waba_phone_number_id and cliente.whatsapp_id:
                    waba_token = decrypt_secret(config.waba_token_enc)
                    wa = WhatsAppService(config.waba_phone_number_id, waba_token)
                    mensajes = {
                        "confirmado": f"✅ ¡Hola {cliente.nombre}! Tu pedido fue confirmado y está siendo preparado.",
                        "enviado": f"📦 ¡Tu pedido está en camino! Guía de rastreo: {pedido.numero_seguimiento or 'por asignar'}",
                        "en_camino": f"🚚 ¡Tu pedido está cerca! Hoy o mañana llegará a tu dirección.",
                        "entregado": f"🎉 ¡Tu pedido fue entregado! Esperamos que lo disfrutes.",
                        "fallido": f"😟 Tuvimos un problema con la entrega. Nos comunicaremos contigo pronto.",
                    }
                    if nuevo_estado_str in mensajes:
                        await wa.enviar_texto(cliente.whatsapp_id, mensajes[nuevo_estado_str])

                if cliente and cliente.email and config.smtp_host:
                    email_svc = EmailService(config)
                    await email_svc.enviar_estado_envio(
                        cliente.email, cliente.nombre or "Cliente",
                        nuevo_estado_str, pedido.numero_seguimiento
                    )

            except Exception:
                pass

        await db.commit()
