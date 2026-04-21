import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.api import auth, tenants, products, campaigns, bot, orders, dashboard, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas si no existen (en producción usa Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_superadmin()
    yield


async def _seed_superadmin():
    """Crea el super-admin al iniciar si no existe."""
    from app.database import AsyncSessionLocal
    from app.models.tenant import Tenant
    from app.core.security import hash_password
    from app.config import settings
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tenant).where(Tenant.email == settings.superadmin_email))
        if not result.scalar_one_or_none():
            admin = Tenant(
                nombre_empresa="Super Admin",
                email=settings.superadmin_email,
                hashed_password=hash_password(settings.superadmin_password),
                es_superadmin=True,
                activo=True,
            )
            db.add(admin)
            await db.commit()


app = FastAPI(
    title="Venbot — Automatización E-commerce con IA",
    description="Plataforma SaaS para automatizar ventas, anuncios y atención al cliente con inteligencia artificial.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Archivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Media (imágenes subidas por tenants)
os.makedirs("/app/media", exist_ok=True)
app.mount("/media", StaticFiles(directory="/app/media"), name="media")

# Routers
app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(products.router)
app.include_router(campaigns.router)
app.include_router(bot.router)
app.include_router(orders.router)
app.include_router(dashboard.router)
app.include_router(admin.router)


@app.get("/")
async def raiz():
    return RedirectResponse(url="/dashboard/")


@app.get("/health")
async def health():
    return {"status": "ok", "servicio": "Venbot"}
