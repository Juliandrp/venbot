import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Numeric, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base


class CampaignStatus(str, enum.Enum):
    borrador = "borrador"
    activa = "activa"
    pausada = "pausada"
    finalizada = "finalizada"
    error = "error"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)

    # Meta Ads IDs
    meta_campaign_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meta_campaign_objective: Mapped[str] = mapped_column(String(100), default="OUTCOME_SALES")

    # Presupuesto
    presupuesto_diario: Mapped[float] = mapped_column(Numeric(10, 2), default=10.0)  # USD
    presupuesto_total: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Umbrales de pausa automática
    roas_minimo: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    cpc_maximo: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    estado: Mapped[CampaignStatus] = mapped_column(SAEnum(CampaignStatus), default=CampaignStatus.borrador)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    producto: Mapped["Product"] = relationship("Product", back_populates="campanas")
    ad_sets: Mapped[list["AdSet"]] = relationship("AdSet", back_populates="campana", cascade="all, delete-orphan")
    snapshots: Mapped[list["AdPerformanceSnapshot"]] = relationship("AdPerformanceSnapshot", back_populates="campana")
    pedidos: Mapped[list["Order"]] = relationship("Order", back_populates="campana")


class AdSet(Base):
    """Conjunto de anuncios segmentado por grupo de edad y género."""
    __tablename__ = "ad_sets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)

    meta_adset_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meta_ad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Segmentación
    grupo_edad: Mapped[str] = mapped_column(String(20))   # "18-24" | "25-34" | "35-44" | "45+"
    genero: Mapped[str] = mapped_column(String(10))       # "M" | "F" | "todos"
    copy_anuncio: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Métricas actuales (se actualizan en cada ciclo)
    impresiones: Mapped[int] = mapped_column(Integer, default=0)
    clics: Mapped[int] = mapped_column(Integer, default=0)
    gasto: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    conversiones: Mapped[int] = mapped_column(Integer, default=0)
    roas: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campana: Mapped["Campaign"] = relationship("Campaign", back_populates="ad_sets")


class AdPerformanceSnapshot(Base):
    """Historial de métricas de campaña (guardado cada ciclo de monitoreo)."""
    __tablename__ = "ad_performance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)

    impresiones: Mapped[int] = mapped_column(Integer, default=0)
    clics: Mapped[int] = mapped_column(Integer, default=0)
    gasto: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    conversiones: Mapped[int] = mapped_column(Integer, default=0)
    roas: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0)
    ctr: Mapped[float] = mapped_column(Numeric(8, 4), default=0.0)
    cpc: Mapped[float] = mapped_column(Numeric(8, 2), default=0.0)
    datos_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    capturado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    campana: Mapped["Campaign"] = relationship("Campaign", back_populates="snapshots")
