"""Dependencias compartidas de FastAPI."""
import uuid
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.security import decode_token
from app.models.tenant import Tenant

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_tenant(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        tenant_id: str = payload.get("sub")
        token_type: str = payload.get("type")
        if tenant_id is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if tenant is None or not tenant.activo:
        raise credentials_exception
    return tenant


async def get_current_superadmin(
    tenant: Tenant = Depends(get_current_tenant),
) -> Tenant:
    if not tenant.es_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
    return tenant


def require_active_plan(tenant: Tenant = Depends(get_current_tenant)) -> Tenant:
    from app.models.tenant import PlanStatus
    if tenant.estado_suscripcion == PlanStatus.suspended:
        raise HTTPException(status_code=402, detail="Suscripción suspendida. Contacte soporte.")
    return tenant
