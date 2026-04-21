from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.product import Product
from app.models.campaign import Campaign, CampaignStatus
from app.models.order import Order, OrderStatus
from app.models.bot import Conversation

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/resumen")
async def resumen(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    hoy = datetime.utcnow().date()
    inicio_semana = hoy - timedelta(days=7)
    inicio_mes = hoy.replace(day=1)

    # Pedidos y revenue
    async def revenue_desde(fecha_desde):
        result = await db.execute(
            select(func.sum(Order.total)).where(
                Order.tenant_id == tenant.id,
                Order.estado.in_([OrderStatus.confirmado, OrderStatus.enviado, OrderStatus.entregado]),
                Order.created_at >= datetime.combine(fecha_desde, datetime.min.time()),
            )
        )
        return float(result.scalar() or 0)

    revenue_hoy = await revenue_desde(hoy)
    revenue_semana = await revenue_desde(inicio_semana)
    revenue_mes = await revenue_desde(inicio_mes)

    # Campañas activas
    result = await db.execute(
        select(func.count()).select_from(Campaign).where(
            Campaign.tenant_id == tenant.id,
            Campaign.estado == CampaignStatus.activa
        )
    )
    campanas_activas = result.scalar()

    # Total pedidos hoy
    result = await db.execute(
        select(func.count()).select_from(Order).where(
            Order.tenant_id == tenant.id,
            Order.created_at >= datetime.combine(hoy, datetime.min.time()),
        )
    )
    pedidos_hoy = result.scalar()

    return {
        "revenue_hoy": revenue_hoy,
        "revenue_semana": revenue_semana,
        "revenue_mes": revenue_mes,
        "campanas_activas": campanas_activas,
        "pedidos_hoy": pedidos_hoy,
    }


# ─── Vistas HTML ─────────────────────────────────────────────

@router.get("/")
async def vista_dashboard(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    return templates.TemplateResponse("dashboard/index.html", {"request": request, "tenant": tenant})


@router.get("/campanas")
async def vista_campanas(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    return templates.TemplateResponse("campaigns/index.html", {"request": request, "tenant": tenant})


@router.get("/bot")
async def vista_bot(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    return templates.TemplateResponse("bot/index.html", {"request": request, "tenant": tenant})


@router.get("/pedidos")
async def vista_pedidos(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    return templates.TemplateResponse("orders/index.html", {"request": request, "tenant": tenant})


@router.get("/configuracion")
async def vista_configuracion(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    return templates.TemplateResponse("settings/index.html", {"request": request, "tenant": tenant})
