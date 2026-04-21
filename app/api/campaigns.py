import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.campaign import Campaign, CampaignStatus
from app.schemas.campaign import CampaignCreate, CampaignOut

router = APIRouter(prefix="/campanas", tags=["Campañas"])


@router.get("/", response_model=list[CampaignOut])
async def listar_campanas(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign)
        .where(Campaign.tenant_id == tenant.id)
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/", response_model=CampaignOut, status_code=201)
async def crear_campana(
    data: CampaignCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    campana = Campaign(
        tenant_id=tenant.id,
        nombre=data.nombre,
        product_id=data.product_id,
        presupuesto_diario=data.presupuesto_diario,
        roas_minimo=data.roas_minimo,
        cpc_maximo=data.cpc_maximo,
        fecha_inicio=data.fecha_inicio,
        fecha_fin=data.fecha_fin,
    )
    db.add(campana)
    await db.commit()
    await db.refresh(campana)
    return campana


@router.post("/{campaign_id}/lanzar", response_model=CampaignOut)
async def lanzar_campana(
    campaign_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    )
    campana = result.scalar_one_or_none()
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    from app.services.meta_ads import MetaAdsService
    from app.models.tenant import TenantConfig
    config_result = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = config_result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=400, detail="Configure las credenciales de Meta Ads primero")

    service = MetaAdsService(config)
    campaign_id_meta = await service.crear_campana(campana, db)
    campana.meta_campaign_id = campaign_id_meta
    campana.estado = CampaignStatus.activa
    await db.commit()
    await db.refresh(campana)
    return campana


@router.post("/{campaign_id}/pausar")
async def pausar_campana(
    campaign_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.tenant_id == tenant.id)
    )
    campana = result.scalar_one_or_none()
    if not campana:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    campana.estado = CampaignStatus.pausada
    await db.commit()
    return {"mensaje": "Campaña pausada"}
