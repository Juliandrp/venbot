import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, Integer, Boolean, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(500), nullable=False)
    descripcion_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    precio: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    precio_comparacion: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    inventario: Mapped[int] = mapped_column(Integer, default=0)
    imagenes_originales: Mapped[list | None] = mapped_column(JSON, nullable=True)  # URLs subidas

    # Estado del pipeline
    contenido_generado: Mapped[bool] = mapped_column(Boolean, default=False)
    publicado_shopify: Mapped[bool] = mapped_column(Boolean, default=False)
    shopify_product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shopify_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="productos")
    contenido: Mapped["ProductContent | None"] = relationship("ProductContent", back_populates="producto", uselist=False)
    campanas: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="producto")


class ProductContent(Base):
    """Contenido generado por IA para un producto."""
    __tablename__ = "product_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), unique=True)

    # Generado por Claude
    titulo_seo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    descripcion_seo: Mapped[str | None] = mapped_column(Text, nullable=True)
    bullet_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Variantes de copy por segmento: {age_group: {gender: copy_text}}
    variantes_copy: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Generado por HeyGen
    video_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    heygen_video_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_estado: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Imágenes generadas por DALL-E / Flux
    imagenes_generadas: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    producto: Mapped["Product"] = relationship("Product", back_populates="contenido")
