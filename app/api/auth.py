from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.tenant import Tenant, PlanStatus
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, RefreshRequest
from jose import JWTError
import uuid

router = APIRouter(prefix="/auth", tags=["Autenticación"])
templates = Jinja2Templates(directory="app/templates")


# ─── REST API ────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def registrar(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    tenant = Tenant(
        nombre_empresa=data.nombre_empresa,
        email=data.email,
        hashed_password=hash_password(data.password),
        estado_suscripcion=PlanStatus.trial,
    )
    db.add(tenant)
    await db.flush()

    # Crear config vacía para el tenant
    from app.models.tenant import TenantConfig
    config = TenantConfig(tenant_id=tenant.id)
    db.add(config)
    await db.commit()
    await db.refresh(tenant)

    token_data = {"sub": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.email == data.email))
    tenant = result.scalar_one_or_none()
    if not tenant or not verify_password(data.password, tenant.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
        )
    if not tenant.activo:
        raise HTTPException(status_code=403, detail="Cuenta desactivada. Contacte soporte.")

    token_data = {"sub": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token inválido")
        tenant_id = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expirado o inválido")

    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant or not tenant.activo:
        raise HTTPException(status_code=401, detail="Tenant no encontrado")

    token_data = {"sub": str(tenant.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


# ─── Vistas HTML ─────────────────────────────────────────────

@router.get("/iniciar-sesion")
async def vista_login(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.get("/registro")
async def vista_registro(request: Request):
    return templates.TemplateResponse("auth/registro.html", {"request": request})
