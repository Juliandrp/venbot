import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Numeric, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base


class OrderStatus(str, enum.Enum):
    pendiente = "pendiente"
    confirmado = "confirmado"
    enviado = "enviado"
    en_camino = "en_camino"
    entregado = "entregado"
    fallido = "fallido"
    cancelado = "cancelado"


class ShipmentEventType(str, enum.Enum):
    confirmado = "confirmado"
    enviado = "enviado"
    en_camino = "en_camino"
    entregado = "entregado"
    fallido = "fallido"
    otro = "otro"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)

    # Dropi
    dropi_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    numero_seguimiento: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transportadora: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Datos del cliente al momento del pedido
    nombre_destinatario: Mapped[str] = mapped_column(String(300), nullable=False)
    telefono_destinatario: Mapped[str] = mapped_column(String(50), nullable=False)
    direccion_envio: Mapped[str] = mapped_column(Text, nullable=False)
    ciudad_envio: Mapped[str] = mapped_column(String(100), nullable=False)
    departamento_envio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pais_envio: Mapped[str] = mapped_column(String(10), default="CO")

    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus), default=OrderStatus.pendiente)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="pedidos")
    cliente: Mapped["Customer"] = relationship("Customer", back_populates="pedidos")
    campana: Mapped["Campaign | None"] = relationship("Campaign", back_populates="pedidos")
    conversacion: Mapped["Conversation | None"] = relationship("Conversation", back_populates="pedidos")
    eventos_envio: Mapped[list["ShipmentEvent"]] = relationship("ShipmentEvent", back_populates="pedido", order_by="ShipmentEvent.created_at")


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)

    tipo: Mapped[ShipmentEventType] = mapped_column(SAEnum(ShipmentEventType))
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    ubicacion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notificacion_enviada: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    pedido: Mapped["Order"] = relationship("Order", back_populates="eventos_envio")
