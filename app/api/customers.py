"""Endpoints para gestión de clientes (Customers)."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.schemas.customer import (
    CustomerCreate, CustomerUpdate, CustomerOut, CustomerListOut,
)

router = APIRouter(prefix="/clientes", tags=["Clientes"])
templates = Jinja2Templates(directory="app/templates")


# ─── Vista HTML ──────────────────────────────────────────────

@router.get("/vista/lista")
async def vista_clientes(request: Request):
    return templates.TemplateResponse("customers/index.html", {"request": request})


# ─── API JSON ────────────────────────────────────────────────

async def _enriquecer(customer: Customer, db: AsyncSession) -> dict:
    """Agrega métricas de pedidos al cliente."""
    cnt = await db.execute(
        select(func.count()).select_from(Order).where(Order.customer_id == customer.id)
    )
    total_pedidos = cnt.scalar() or 0

    sum_result = await db.execute(
        select(func.sum(Order.total)).where(
            Order.customer_id == customer.id,
            Order.estado.in_([OrderStatus.confirmado, OrderStatus.enviado, OrderStatus.entregado]),
        )
    )
    total_gastado = float(sum_result.scalar() or 0)

    d = CustomerOut.model_validate(customer).model_dump()
    d["total_pedidos"] = total_pedidos
    d["total_gastado"] = total_gastado
    return d


@router.get("/", response_model=CustomerListOut)
async def listar_clientes(
    skip: int = 0,
    limit: int = 50,
    q: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(Customer).where(Customer.tenant_id == tenant.id)
    count_query = select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant.id)

    if q:
        like = f"%{q}%"
        cond = or_(
            Customer.nombre.ilike(like),
            Customer.email.ilike(like),
            Customer.telefono.ilike(like),
            Customer.whatsapp_id.ilike(like),
        )
        query = query.where(cond)
        count_query = count_query.where(cond)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(
        query.order_by(Customer.created_at.desc()).offset(skip).limit(limit)
    )
    items = result.scalars().all()
    enriquecidos = [await _enriquecer(c, db) for c in items]
    return {"total": total, "items": enriquecidos}


@router.post("/", response_model=CustomerOut, status_code=201)
async def crear_cliente(
    data: CustomerCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    cliente = Customer(tenant_id=tenant.id, **data.model_dump())
    db.add(cliente)
    await db.commit()
    await db.refresh(cliente)
    return await _enriquecer(cliente, db)


@router.get("/{customer_id}", response_model=CustomerOut)
async def obtener_cliente(
    customer_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id)
    )
    cliente = result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return await _enriquecer(cliente, db)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def actualizar_cliente(
    customer_id: uuid.UUID,
    data: CustomerUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id)
    )
    cliente = result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cliente, field, value)
    await db.commit()
    await db.refresh(cliente)
    return await _enriquecer(cliente, db)


@router.delete("/{customer_id}", status_code=204)
async def eliminar_cliente(
    customer_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id)
    )
    cliente = result.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    await db.delete(cliente)
    await db.commit()
