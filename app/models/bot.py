import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base


class Canal(str, enum.Enum):
    whatsapp = "whatsapp"
    messenger = "messenger"


class ConversationStatus(str, enum.Enum):
    activa = "activa"
    transferida = "transferida"  # pasada a agente humano
    cerrada = "cerrada"


class MessageRole(str, enum.Enum):
    cliente = "cliente"
    bot = "bot"
    humano = "humano"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)

    canal: Mapped[Canal] = mapped_column(SAEnum(Canal))
    external_thread_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    estado: Mapped[ConversationStatus] = mapped_column(SAEnum(ConversationStatus), default=ConversationStatus.activa)

    # Meta-datos del bot
    confianza_promedio: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_cerrada: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cliente: Mapped["Customer"] = relationship("Customer", back_populates="conversaciones")
    mensajes: Mapped[list["Message"]] = relationship("Message", back_populates="conversacion", order_by="Message.created_at")
    pedidos: Mapped[list["Order"]] = relationship("Order", back_populates="conversacion")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)

    rol: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole))
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversacion: Mapped["Conversation"] = relationship("Conversation", back_populates="mensajes")
