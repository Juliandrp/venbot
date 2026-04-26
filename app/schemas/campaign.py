import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator
from app.models.campaign import CampaignStatus


class CampaignCreate(BaseModel):
    nombre: str
    product_id: uuid.UUID | None = None
    presupuesto_diario: float = 10.0
    roas_minimo: float | None = None
    cpc_maximo: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None

    @field_validator("product_id", "roas_minimo", "cpc_maximo", "fecha_inicio", "fecha_fin", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v

    @field_validator("presupuesto_diario", mode="before")
    @classmethod
    def _empty_default(cls, v):
        if v == "" or v is None:
            return 10.0
        return v


class CampaignUpdate(BaseModel):
    nombre: str | None = None
    product_id: uuid.UUID | None = None
    presupuesto_diario: float | None = None
    roas_minimo: float | None = None
    cpc_maximo: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None

    @field_validator("product_id", "roas_minimo", "cpc_maximo", "presupuesto_diario", "fecha_inicio", "fecha_fin", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class CampaignOut(BaseModel):
    id: uuid.UUID
    nombre: str
    estado: CampaignStatus
    presupuesto_diario: float
    roas_minimo: float | None = None
    cpc_maximo: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None
    product_id: uuid.UUID | None = None
    meta_campaign_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
