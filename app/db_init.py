"""
Inicialización de la base de datos al arrancar la app.

Estrategia:
  1. Si la BD está vacía (sin tabla `alembic_version`) → ejecuta create_all
     y marca como migrada insertando la última revisión.
  2. Si ya está versionada → intenta `alembic upgrade head`. Si falla por
     conflictos async/sync, registra warning y deja que el código siga
     (las tablas ya están creadas desde versiones previas).

Por qué insertamos en alembic_version manualmente en lugar de usar
`command.stamp`: stamp dispara `env.py` que llama `asyncio.run()` —
esto choca con el event loop de uvicorn y produce RuntimeWarnings
y reinicios silenciosos del contenedor en producción.
"""
from pathlib import Path
from sqlalchemy import inspect, text


# Última revisión de Alembic conocida. Sincronizar con el archivo más reciente
# en alembic/versions/ (ej. "0002_higgsfield_key.py" → "0002").
LATEST_REVISION = "0002"


async def init_database():
    """Llamado desde el lifespan de FastAPI al arrancar."""
    from app.database import engine, Base
    import app.models  # noqa: F401  registra todos los modelos en Base.metadata

    async with engine.begin() as conn:
        def _check_versionada(sync_conn):
            inspector = inspect(sync_conn)
            return "alembic_version" in inspector.get_table_names()

        ya_versionada = await conn.run_sync(_check_versionada)

        if not ya_versionada:
            # BD virgen: crear esquema completo y stampar manualmente
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            ))
            await conn.execute(text(
                f"INSERT INTO alembic_version (version_num) VALUES ('{LATEST_REVISION}') "
                f"ON CONFLICT (version_num) DO NOTHING"
            ))
            print(f"[db_init] Esquema creado con create_all + stamped en '{LATEST_REVISION}'")
        else:
            # BD existente: solo asegura que tenga la última versión registrada
            # Las migraciones reales deben correr ANTES (start.sh: alembic upgrade head)
            current = (await conn.execute(text(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ))).scalar()
            print(f"[db_init] BD versionada en '{current}' (esperado: '{LATEST_REVISION}')")
