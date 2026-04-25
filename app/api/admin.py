"""Panel de super-administrador."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.core.deps import get_current_superadmin
from app.models.tenant import Tenant, PlanStatus, SubscriptionPlan
from app.models.product import Product
from app.models.order import Order, OrderStatus
from app.models.bot import Conversation, Message
from app.schemas.tenant import TenantOut

router = APIRouter(prefix="/admin", tags=["Super-Admin"])
templates = Jinja2Templates(directory="app/templates")


# ─── Tenants ─────────────────────────────────────────────────

@router.get("/tenants")
async def listar_tenants(
    skip: int = 0,
    limit: int = 100,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos los tenants con métricas básicas."""
    result = await db.execute(
        select(Tenant)
        .where(Tenant.es_superadmin == False)
        .order_by(Tenant.created_at.desc())
        .offset(skip).limit(limit)
    )
    tenants = result.scalars().all()

    items = []
    for t in tenants:
        # Métricas por tenant
        prod_cnt = await db.execute(select(func.count()).select_from(Product).where(Product.tenant_id == t.id))
        ord_cnt = await db.execute(select(func.count()).select_from(Order).where(Order.tenant_id == t.id))
        revenue = await db.execute(
            select(func.sum(Order.total)).where(
                Order.tenant_id == t.id,
                Order.estado.in_([OrderStatus.confirmado, OrderStatus.enviado, OrderStatus.entregado]),
            )
        )
        items.append({
            "id": str(t.id),
            "nombre_empresa": t.nombre_empresa,
            "email": t.email,
            "estado_suscripcion": t.estado_suscripcion.value,
            "activo": t.activo,
            "plan_id": t.plan_id,
            "created_at": t.created_at.isoformat(),
            "total_productos": prod_cnt.scalar() or 0,
            "total_pedidos": ord_cnt.scalar() or 0,
            "revenue_total": float(revenue.scalar() or 0),
        })

    total_q = await db.execute(select(func.count()).select_from(Tenant).where(Tenant.es_superadmin == False))
    return {"total": total_q.scalar() or 0, "items": items}


@router.post("/tenants/{tenant_id}/suspender")
async def suspender_tenant(
    tenant_id: str,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    tenant.estado_suscripcion = PlanStatus.suspended
    tenant.activo = False
    await db.commit()
    return {"mensaje": "Tenant suspendido"}


@router.post("/tenants/{tenant_id}/activar")
async def activar_tenant(
    tenant_id: str,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    tenant.activo = True
    tenant.estado_suscripcion = PlanStatus.active
    await db.commit()
    return {"mensaje": "Tenant activado"}


@router.post("/tenants/{tenant_id}/asignar-plan")
async def asignar_plan(
    tenant_id: str,
    payload: dict,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    plan_id = (payload or {}).get("plan_id")
    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")

    if plan_id is not None:
        plan_check = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
        if not plan_check.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Plan no encontrado")
        tenant.plan_id = plan_id
        tenant.estado_suscripcion = PlanStatus.active
    await db.commit()
    return {"mensaje": "Plan asignado"}


@router.delete("/tenants/{tenant_id}", status_code=204)
async def eliminar_tenant(
    tenant_id: str,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    if tenant.es_superadmin:
        raise HTTPException(status_code=400, detail="No se puede eliminar un super-admin")
    await db.delete(tenant)
    await db.commit()


# ─── Planes de suscripción ──────────────────────────────────

@router.get("/planes")
async def listar_planes(
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.precio_mensual.asc()))
    planes = result.scalars().all()
    return [
        {
            "id": p.id,
            "nombre": p.nombre,
            "tier": p.tier.value,
            "max_productos": p.max_productos,
            "max_campanas": p.max_campanas,
            "max_mensajes_bot": p.max_mensajes_bot,
            "precio_mensual": p.precio_mensual,
            "precio_mensual_usd": p.precio_mensual / 100.0,
            "activo": p.activo,
        }
        for p in planes
    ]


@router.post("/planes", status_code=201)
async def crear_plan(
    payload: dict,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    from app.models.tenant import PlanTier
    plan = SubscriptionPlan(
        nombre=payload["nombre"],
        tier=PlanTier(payload.get("tier", "starter")),
        max_productos=int(payload.get("max_productos", 10)),
        max_campanas=int(payload.get("max_campanas", 5)),
        max_mensajes_bot=int(payload.get("max_mensajes_bot", 1000)),
        precio_mensual=int(float(payload.get("precio_mensual_usd", 0)) * 100),
        activo=bool(payload.get("activo", True)),
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id}


@router.patch("/planes/{plan_id}")
async def actualizar_plan(
    plan_id: int,
    payload: dict,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    for k, v in payload.items():
        if k == "precio_mensual_usd":
            plan.precio_mensual = int(float(v) * 100)
        elif hasattr(plan, k):
            setattr(plan, k, v)
    await db.commit()
    return {"mensaje": "Plan actualizado"}


@router.delete("/planes/{plan_id}", status_code=204)
async def eliminar_plan(
    plan_id: int,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    await db.delete(plan)
    await db.commit()


# ─── Métricas globales ──────────────────────────────────────

@router.get("/metricas")
async def metricas_globales(
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    total_tenants = (await db.execute(
        select(func.count()).select_from(Tenant).where(Tenant.es_superadmin == False)
    )).scalar() or 0
    activos = (await db.execute(
        select(func.count()).select_from(Tenant).where(
            Tenant.activo == True, Tenant.es_superadmin == False
        )
    )).scalar() or 0
    suspendidos = (await db.execute(
        select(func.count()).select_from(Tenant).where(
            Tenant.estado_suscripcion == PlanStatus.suspended
        )
    )).scalar() or 0
    total_productos = (await db.execute(select(func.count()).select_from(Product))).scalar() or 0
    total_pedidos = (await db.execute(select(func.count()).select_from(Order))).scalar() or 0
    revenue_global = (await db.execute(
        select(func.sum(Order.total)).where(
            Order.estado.in_([OrderStatus.confirmado, OrderStatus.enviado, OrderStatus.entregado]),
        )
    )).scalar() or 0
    total_conversaciones = (await db.execute(select(func.count()).select_from(Conversation))).scalar() or 0
    total_mensajes = (await db.execute(select(func.count()).select_from(Message))).scalar() or 0

    return {
        "total_tenants": total_tenants,
        "tenants_activos": activos,
        "tenants_suspendidos": suspendidos,
        "total_productos": total_productos,
        "total_pedidos": total_pedidos,
        "revenue_global": float(revenue_global),
        "total_conversaciones": total_conversaciones,
        "total_mensajes": total_mensajes,
    }


# ─── Vistas HTML ────────────────────────────────────────────

@router.get("/")
async def vista_admin(request: Request):
    return templates.TemplateResponse("admin/index.html", {"request": request})


@router.get("/planes-vista")
async def vista_planes(request: Request):
    return templates.TemplateResponse("admin/planes.html", {"request": request})
