"""Panel de super-administrador."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.core.deps import get_current_superadmin
from app.models.tenant import Tenant, PlanStatus
from app.schemas.tenant import TenantOut

router = APIRouter(prefix="/admin", tags=["Super-Admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/tenants", response_model=list[TenantOut])
async def listar_tenants(
    skip: int = 0,
    limit: int = 100,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Tenant).where(Tenant.es_superadmin == False).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("/tenants/{tenant_id}/suspender")
async def suspender_tenant(
    tenant_id: str,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    tenant.estado_suscripcion = PlanStatus.suspended
    await db.commit()
    return {"mensaje": "Tenant suspendido"}


@router.post("/tenants/{tenant_id}/activar")
async def activar_tenant(
    tenant_id: str,
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    tenant.activo = True
    tenant.estado_suscripcion = PlanStatus.active
    await db.commit()
    return {"mensaje": "Tenant activado"}


@router.get("/metricas")
async def metricas_globales(
    _admin: Tenant = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    total_tenants = await db.execute(select(func.count()).select_from(Tenant).where(Tenant.es_superadmin == False))
    activos = await db.execute(
        select(func.count()).select_from(Tenant).where(Tenant.activo == True, Tenant.es_superadmin == False)
    )
    return {
        "total_tenants": total_tenants.scalar(),
        "tenants_activos": activos.scalar(),
    }


@router.get("/")
async def vista_admin(request: Request, _admin: Tenant = Depends(get_current_superadmin)):
    return templates.TemplateResponse("admin/index.html", {"request": request, "admin": _admin})
