"""
Inicialización de la base de datos al arrancar la app.

Estrategia:
  1. Si la BD está vacía (sin tabla `alembic_version`) → ejecuta create_all
     y marca como migrada (`alembic stamp head`).
  2. Si ya está versionada → ejecuta `alembic upgrade head` para aplicar
     migraciones pendientes.

Esto permite ambos flujos:
  - Despliegue limpio (Coolify primera vez): crea esquema + stamp
  - Despliegue posterior: aplica solo nuevas migraciones
"""
import os
from pathlib import Path
from alembic.config import Config
from alembic import command
from sqlalchemy import inspect


def _alembic_config() -> Config:
    """Construye la config de Alembic apuntando a la app/."""
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    return cfg


async def init_database():
    """Llamado desde el lifespan de FastAPI al arrancar."""
    from app.database import engine, Base
    import app.models  # noqa: F401  carga todos los modelos

    cfg = _alembic_config()

    async with engine.begin() as conn:
        # Verificar si existe la tabla alembic_version
        def _check_versionada(sync_conn):
            inspector = inspect(sync_conn)
            return "alembic_version" in inspector.get_table_names()

        ya_versionada = await conn.run_sync(_check_versionada)

        if not ya_versionada:
            # BD virgen o legacy sin Alembic: crear esquema y marcar como migrada
            await conn.run_sync(Base.metadata.create_all)
            print("[db_init] Esquema creado con create_all (BD virgen)")

            def _stamp(sync_conn):
                cfg.attributes["connection"] = sync_conn
                command.stamp(cfg, "head")
            await conn.run_sync(_stamp)
            print("[db_init] BD marcada como 'head' (alembic stamp)")
        else:
            # BD versionada: aplicar migraciones pendientes
            def _upgrade(sync_conn):
                cfg.attributes["connection"] = sync_conn
                command.upgrade(cfg, "head")
            await conn.run_sync(_upgrade)
            print("[db_init] Migraciones aplicadas (alembic upgrade head)")
