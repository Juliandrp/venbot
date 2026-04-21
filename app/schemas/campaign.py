import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.campaign import CampaignStatus


class CampaignCreate(BaseModel):
    nombre: str
    product_id: uuid.UUID
    presupuesto_diario: float = 10.0
    roas_minimo: float | None = None
    cpc_maximo: float | None = None
    fecha_inicio: datetime | None = None
    fecha_fin: datetime | None = None


class CampaignOut(BaseModel):
    id: uuid.UUID
    nombre: str
    estado: CampaignStatus
    presupuesto_diario: float
    meta_campaign_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
