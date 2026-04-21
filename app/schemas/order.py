import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.order import OrderStatus


class OrderOut(BaseModel):
    id: uuid.UUID
    nombre_destinatario: str
    telefono_destinatario: str
    ciudad_envio: str
    total: float
    estado: OrderStatus
    dropi_order_id: str | None
    numero_seguimiento: str | None
    transportadora: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
