"""Worker: notificaciones a clientes (WhatsApp + email) ante eventos del pedido."""
import asyncio
import uuid
from app.celery_app import celery_app


MENSAJES = {
    "creado": "🛒 ¡Hola {nombre}! Recibimos tu pedido #{numero} por ${total:,.0f}. Pronto te confirmaremos los detalles.",
    "confirmado": "✅ ¡Hola {nombre}! Tu pedido #{numero} fue confirmado y está en preparación. Total: ${total:,.0f}.",
    "enviado": "📦 ¡Tu pedido #{numero} fue despachado! Guía de rastreo: {tracking}",
    "en_camino": "🚚 ¡Tu pedido #{numero} está cerca! Hoy o mañana llegará a tu dirección.",
    "entregado": "🎉 ¡Tu pedido #{numero} fue entregado! Esperamos que lo disfrutes.",
    "fallido": "😟 Tuvimos un problema con la entrega del pedido #{numero}. Nos comunicaremos contigo pronto.",
    "cancelado": "❌ Tu pedido #{numero} fue cancelado. Si crees que es un error, contáctanos.",
}


@celery_app.task(
    name="app.workers.notifications.notificar_cliente_pedido",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def notificar_cliente_pedido(self, order_id: str, evento: str):
    """
    Envía notificación al cliente sobre un evento del pedido.

    evento: 'creado' | 'confirmado' | 'enviado' | 'en_camino' | 'entregado' | 'fallido' | 'cancelado'
    """
    try:
        asyncio.run(_notificar(order_id, evento))
    except Exception as exc:
        raise self.retry(exc=exc)


# Alias retro-compatible para llamadas existentes
@celery_app.task(name="app.workers.notifications.notificar_pedido_confirmado", bind=True)
def notificar_pedido_confirmado(self, order_id: str, tenant_id: str):
    asyncio.run(_notificar(order_id, "confirmado"))


async def _notificar(order_id: str, evento: str):
    from app.database import make_celery_session
    AsyncSessionLocal = make_celery_session()
    from app.models.order import Order
    from app.models.tenant import TenantConfig
    from app.models.customer import Customer
    from app.services.whatsapp import WhatsAppService
    from app.services.email_service import EmailService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
        pedido = result.scalar_one_or_none()
        if not pedido:
            return

        c_result = await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == pedido.tenant_id)
        )
        config = c_result.scalar_one_or_none()
        if not config:
            return

        cust = await db.execute(select(Customer).where(Customer.id == pedido.customer_id))
        cliente = cust.scalar_one_or_none()
        if not cliente:
            return

        plantilla = MENSAJES.get(evento)
        if not plantilla:
            return

        nombre_corto = (cliente.nombre or "Cliente").split()[0]
        numero_corto = str(pedido.id)[:8].upper()
        total = float(pedido.total or 0)
        tracking = pedido.numero_seguimiento or "por asignar"

        texto = plantilla.format(
            nombre=nombre_corto, numero=numero_corto, total=total, tracking=tracking,
        )

        # WhatsApp
        if (
            cliente.whatsapp_id
            and config.waba_token_enc
            and config.waba_phone_number_id
        ):
            try:
                token = decrypt_secret(config.waba_token_enc)
                wa = WhatsAppService(config.waba_phone_number_id, token)
                await wa.enviar_texto(cliente.whatsapp_id, texto)
            except Exception:
                pass

        # Email
        if cliente.email and config.smtp_host:
            try:
                email_svc = EmailService(config)
                cuerpo = (
                    f"<div style='font-family:Arial,sans-serif;max-width:600px;'>"
                    f"<h2 style='color:#4F46E5'>{nombre_corto},</h2>"
                    f"<p style='font-size:16px;line-height:1.6'>{texto}</p>"
                    f"<p style='font-size:14px;color:#666;margin-top:30px'>Gracias por tu compra.</p>"
                    f"</div>"
                )
                asunto = f"Pedido #{numero_corto} — {evento.replace('_', ' ').capitalize()}"
                await email_svc.enviar(cliente.email, asunto, cuerpo)
            except Exception:
                pass
