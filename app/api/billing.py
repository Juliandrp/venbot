"""Endpoints de checkout y webhooks de pago."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant, SubscriptionPlan, PlanStatus
from app.config import settings

router = APIRouter(prefix="/billing", tags=["Pagos"])


@router.post("/checkout/{plan_id}")
async def crear_checkout(
    plan_id: int,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Genera URL de checkout en la pasarela configurada (Stripe / MercadoPago).
    Si el provider es vacío, retorna error 503.
    """
    from app.services.payments import obtener_provider

    provider = obtener_provider()
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="Pagos no habilitados. Configura PAYMENT_PROVIDER en .env",
        )

    result = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.id == plan_id, SubscriptionPlan.activo == True
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    base = settings.app_base_url.rstrip("/")
    success_url = f"{base}/dashboard/plan?pago=ok"
    cancel_url = f"{base}/dashboard/plan?pago=cancelado"

    try:
        url = await provider.crear_checkout(
            plan_id=plan.id,
            plan_nombre=plan.nombre,
            precio_usd=plan.precio_mensual / 100.0,
            tenant_id=str(tenant.id),
            success_url=success_url,
            cancel_url=cancel_url,
        )
        return {"checkout_url": url}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error con la pasarela: {str(e)[:200]}")


@router.post("/webhooks/{provider}", include_in_schema=False)
async def webhook_pago(provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Recibe notificaciones de la pasarela cuando un pago se confirma.
    Activa el plan del tenant correspondiente.
    """
    import uuid as _uuid
    from app.services.payments import obtener_provider

    payment_provider = obtener_provider()
    if payment_provider is None:
        return {"status": "ignored", "reason": "no payment provider configured"}

    payload = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    evento = payment_provider.verificar_y_parsear_webhook(payload, headers)
    if not evento:
        return {"status": "ignored"}

    # Activar plan en el tenant
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == _uuid.UUID(evento["tenant_id"]))
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        return {"status": "tenant_not_found"}

    tenant.plan_id = evento["plan_id"]
    tenant.estado_suscripcion = PlanStatus.active
    tenant.activo = True
    await db.commit()
    return {"status": "ok"}
