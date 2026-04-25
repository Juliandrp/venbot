"""
Validación de límites según el plan de suscripción del tenant.

Cada función verifica si el tenant puede realizar una acción dado su plan,
y lanza HTTPException 402 (Payment Required) si excedió el límite.

Tenants en estado 'trial' usan límites del plan más barato disponible
(o un fallback razonable si no hay planes definidos).
"""
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.tenant import Tenant, SubscriptionPlan, PlanStatus
from app.models.product import Product
from app.models.campaign import Campaign, CampaignStatus
from app.models.bot import Message


# Límites por defecto si el tenant no tiene plan asignado
DEFAULT_TRIAL_LIMITS = {
    "max_productos": 5,
    "max_campanas": 1,
    "max_mensajes_bot": 100,
}


async def _obtener_limites(tenant: Tenant, db: AsyncSession) -> dict:
    """Retorna los límites efectivos del tenant según su plan."""
    if tenant.plan_id:
        result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == tenant.plan_id)
        )
        plan = result.scalar_one_or_none()
        if plan:
            return {
                "max_productos": plan.max_productos,
                "max_campanas": plan.max_campanas,
                "max_mensajes_bot": plan.max_mensajes_bot,
                "plan_nombre": plan.nombre,
            }
    # Sin plan: usar defaults de trial
    return {**DEFAULT_TRIAL_LIMITS, "plan_nombre": "Trial"}


def _bloqueado_por_suscripcion(tenant: Tenant) -> bool:
    return tenant.estado_suscripcion == PlanStatus.suspended or not tenant.activo


async def verificar_puede_crear_producto(tenant: Tenant, db: AsyncSession):
    """Lanza 402 si el tenant ya alcanzó max_productos del plan."""
    if tenant.es_superadmin:
        return
    if _bloqueado_por_suscripcion(tenant):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Tu cuenta está suspendida. Contacta soporte o actualiza tu plan.",
        )

    limites = await _obtener_limites(tenant, db)
    cnt = await db.execute(
        select(func.count()).select_from(Product).where(
            Product.tenant_id == tenant.id, Product.activo == True
        )
    )
    actual = cnt.scalar() or 0
    if actual >= limites["max_productos"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Alcanzaste el límite de {limites['max_productos']} productos del plan {limites['plan_nombre']}. "
                f"Actualiza tu plan para crear más."
            ),
        )


async def verificar_puede_crear_campana(tenant: Tenant, db: AsyncSession):
    """Lanza 402 si el tenant ya alcanzó max_campanas activas."""
    if tenant.es_superadmin:
        return
    if _bloqueado_por_suscripcion(tenant):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Tu cuenta está suspendida. Contacta soporte o actualiza tu plan.",
        )

    limites = await _obtener_limites(tenant, db)
    cnt = await db.execute(
        select(func.count()).select_from(Campaign).where(
            Campaign.tenant_id == tenant.id,
            Campaign.estado.in_([CampaignStatus.activa, CampaignStatus.borrador]),
        )
    )
    actual = cnt.scalar() or 0
    if actual >= limites["max_campanas"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Alcanzaste el límite de {limites['max_campanas']} campañas del plan {limites['plan_nombre']}. "
                f"Pausa o elimina alguna, o actualiza tu plan."
            ),
        )


async def verificar_puede_enviar_mensaje_bot(tenant: Tenant, db: AsyncSession):
    """Lanza 402 si el tenant excedió mensajes del bot en el mes actual."""
    if tenant.es_superadmin:
        return
    if _bloqueado_por_suscripcion(tenant):
        return  # Mejor no responder que devolver 402 desde el bot

    limites = await _obtener_limites(tenant, db)
    inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cnt = await db.execute(
        select(func.count()).select_from(Message).where(
            Message.tenant_id == tenant.id,
            Message.created_at >= inicio_mes,
        )
    )
    actual = cnt.scalar() or 0
    if actual >= limites["max_mensajes_bot"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Alcanzaste el límite de {limites['max_mensajes_bot']} mensajes/mes del plan {limites['plan_nombre']}."
            ),
        )


async def obtener_uso_actual(tenant: Tenant, db: AsyncSession) -> dict:
    """Retorna el uso actual vs límite para mostrar en UI (barras de progreso)."""
    limites = await _obtener_limites(tenant, db)

    productos = await db.execute(
        select(func.count()).select_from(Product).where(
            Product.tenant_id == tenant.id, Product.activo == True
        )
    )
    campanas = await db.execute(
        select(func.count()).select_from(Campaign).where(
            Campaign.tenant_id == tenant.id,
            Campaign.estado.in_([CampaignStatus.activa, CampaignStatus.borrador]),
        )
    )
    inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mensajes = await db.execute(
        select(func.count()).select_from(Message).where(
            Message.tenant_id == tenant.id,
            Message.created_at >= inicio_mes,
        )
    )

    return {
        "plan": limites["plan_nombre"],
        "productos": {"usado": productos.scalar() or 0, "limite": limites["max_productos"]},
        "campanas": {"usado": campanas.scalar() or 0, "limite": limites["max_campanas"]},
        "mensajes_bot": {"usado": mensajes.scalar() or 0, "limite": limites["max_mensajes_bot"]},
    }
