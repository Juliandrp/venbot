import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.order import Order, OrderStatus
from app.schemas.order import OrderOut, OrderUpdateStatus

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])


@router.get("/", response_model=list[OrderOut])
async def listar_pedidos(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    result = await db.execute(
        select(Order)
        .where(Order.tenant_id == tenant.id)
        .order_by(Order.created_at.desc())
        .offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/{order_id}", response_model=OrderOut)
async def obtener_pedido(
    order_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    pedido = result.scalar_one_or_none()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return pedido


@router.patch("/{order_id}/estado", response_model=OrderOut)
async def cambiar_estado_pedido(
    order_id: uuid.UUID,
    data: OrderUpdateStatus,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Cambia el estado del pedido manualmente y dispara notificación al cliente."""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    pedido = result.scalar_one_or_none()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    estado_anterior = pedido.estado
    pedido.estado = data.estado
    if data.numero_seguimiento:
        pedido.numero_seguimiento = data.numero_seguimiento
    if data.transportadora:
        pedido.transportadora = data.transportadora
    await db.commit()
    await db.refresh(pedido)

    # Disparar notificación si cambió el estado y se solicitó
    if data.notificar_cliente and pedido.estado != estado_anterior:
        from app.workers.notifications import notificar_cliente_pedido
        notificar_cliente_pedido.delay(str(pedido.id), pedido.estado.value)

    return pedido


@router.post("/{order_id}/reenviar-notificacion", status_code=202)
async def reenviar_notificacion(
    order_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Reenvía notificación del estado actual del pedido al cliente."""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.tenant_id == tenant.id)
    )
    pedido = result.scalar_one_or_none()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    from app.workers.notifications import notificar_cliente_pedido
    notificar_cliente_pedido.delay(str(pedido.id), pedido.estado.value)
    return {"mensaje": "Notificación encolada"}
