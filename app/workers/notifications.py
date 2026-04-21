"""Worker: notificaciones puntuales (confirmación de pedido, etc.)."""
import asyncio
from app.celery_app import celery_app


@celery_app.task(name="app.workers.notifications.notificar_pedido_confirmado", bind=True, max_retries=3)
def notificar_pedido_confirmado(self, order_id: str, tenant_id: str):
    asyncio.run(_notificar_confirmacion(order_id, tenant_id))


async def _notificar_confirmacion(order_id: str, tenant_id: str):
    import uuid
    from app.database import AsyncSessionLocal
    from app.models.order import Order
    from app.models.tenant import TenantConfig
    from app.models.customer import Customer
    from app.services.email_service import EmailService
    from app.services.whatsapp import WhatsAppService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        pedido_result = await db.execute(select(Order).where(Order.id == uuid.UUID(order_id)))
        pedido = pedido_result.scalar_one_or_none()
        if not pedido:
            return

        config_result = await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == uuid.UUID(tenant_id))
        )
        config = config_result.scalar_one_or_none()
        if not config:
            return

        cliente_result = await db.execute(select(Customer).where(Customer.id == pedido.customer_id))
        cliente = cliente_result.scalar_one_or_none()
        if not cliente:
            return

        numero = str(pedido.id)[:8].upper()

        # Email
        if cliente.email and config.smtp_host:
            email_svc = EmailService(config)
            await email_svc.enviar_confirmacion_pedido(cliente.email, cliente.nombre or "Cliente", numero)

        # WhatsApp
        if cliente.whatsapp_id and config.waba_token_enc and config.waba_phone_number_id:
            waba_token = decrypt_secret(config.waba_token_enc)
            wa = WhatsAppService(config.waba_phone_number_id, waba_token)
            await wa.enviar_texto(
                cliente.whatsapp_id,
                f"✅ ¡Hola {cliente.nombre or 'cliente'}! Tu pedido #{numero} fue confirmado. "
                f"Te avisaremos cuando sea despachado. 🚀"
            )
