import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.database import Base


class PlanTier(str, enum.Enum):
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class PlanStatus(str, enum.Enum):
    active = "active"
    trial = "trial"
    suspended = "suspended"
    cancelled = "cancelled"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    tier: Mapped[PlanTier] = mapped_column(SAEnum(PlanTier), default=PlanTier.starter)
    max_productos: Mapped[int] = mapped_column(Integer, default=10)
    max_campanas: Mapped[int] = mapped_column(Integer, default=5)
    max_mensajes_bot: Mapped[int] = mapped_column(Integer, default=1000)
    precio_mensual: Mapped[int] = mapped_column(Integer, default=0)  # en centavos USD
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    tenants: Mapped[list["Tenant"]] = relationship("Tenant", back_populates="plan")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre_empresa: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    dominio_personalizado: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    es_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    estado_suscripcion: Mapped[PlanStatus] = mapped_column(SAEnum(PlanStatus), default=PlanStatus.trial)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan: Mapped["SubscriptionPlan | None"] = relationship("SubscriptionPlan", back_populates="tenants")
    config: Mapped["TenantConfig | None"] = relationship("TenantConfig", back_populates="tenant", uselist=False)
    productos: Mapped[list["Product"]] = relationship("Product", back_populates="tenant")
    clientes: Mapped[list["Customer"]] = relationship("Customer", back_populates="tenant")
    pedidos: Mapped[list["Order"]] = relationship("Order", back_populates="tenant")


class TenantConfig(Base):
    """Credenciales API por tenant — valores cifrados con Fernet."""
    __tablename__ = "tenant_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), unique=True)

    # Shopify
    shopify_store_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    shopify_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    shopify_api_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    shopify_access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Meta Ads
    meta_app_id_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_app_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_ad_account_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    meta_pixel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # WhatsApp Business
    waba_phone_number_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    waba_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    waba_verify_token: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Dropi
    dropi_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    dropi_store_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # SMTP
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)

    # AI overrides (opcionales, usan las del platform si están vacíos)
    ai_provider: Mapped[str] = mapped_column(String(20), default="claude")  # claude | gemini
    video_provider: Mapped[str] = mapped_column(String(20), default="kling")  # kling | heygen
    anthropic_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    heygen_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    kling_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="config")
