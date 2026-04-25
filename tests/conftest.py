"""
Fixtures globales de pytest.

Usa SQLite en memoria por test para máxima velocidad y aislamiento.
La app entera se reconfigura para apuntar a la BD de test mediante override
de la dependencia `get_db`.
"""
import os
# Configurar entorno ANTES de importar app — evita validación de Settings
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")
os.environ.setdefault("ENCRYPTION_KEY", "M9CkMBkO45dC1WK3VgOe8pE6CK7IbN0Yb-W2sU-O0Ok=")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SYNC_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("STORAGE_LOCAL_PATH", "/tmp/venbot_test_media")

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.database import Base, get_db
from app.core.security import hash_password
from app.models.tenant import Tenant


@pytest_asyncio.fixture
async def db_engine():
    """Engine SQLite en memoria, fresco por test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        # Importar todos los modelos para que se registren en Base.metadata
        import app.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Session SQLAlchemy compartida con la app durante el test."""
    SessionLocal = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    """Cliente HTTP que comparte la session de DB del test."""
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def tenant_normal(db_session):
    """Crea un tenant común (no super-admin) y retorna el modelo."""
    t = Tenant(
        nombre_empresa="Test Company",
        email="test@example.com",
        hashed_password=hash_password("test123"),
        activo=True,
        es_superadmin=False,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def superadmin(db_session):
    t = Tenant(
        nombre_empresa="Super Admin",
        email="admin@test.io",
        hashed_password=hash_password("admin123"),
        activo=True,
        es_superadmin=True,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest_asyncio.fixture
async def auth_token(client, tenant_normal):
    """Login del tenant normal y retorna access_token."""
    resp = await client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "test123"},
    )
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def admin_token(client, superadmin):
    resp = await client.post(
        "/auth/login",
        json={"email": "admin@test.io", "password": "admin123"},
    )
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
