#!/bin/bash
# ============================================================
# Venbot — script de arranque para producción (1 contenedor)
#
# Lanza:
#   1. Migraciones Alembic (init/upgrade DB)
#   2. Celery worker en background (procesamiento IA, bot, notificaciones)
#   3. Celery beat en background (tareas programadas)
#   4. Uvicorn FastAPI en foreground (PID 1)
#
# Replica el patrón mentisapp (php-fpm + nginx en un contenedor).
# Para escalar: separar worker/beat en apps Coolify aparte.
# ============================================================
set -e

PORT="${PORT:-8000}"
WORKER_CONCURRENCY="${WORKER_CONCURRENCY:-2}"

echo "[start.sh] Iniciando Venbot en puerto $PORT"

# Crear directorios necesarios (storage local)
mkdir -p /app/media /app/celerybeat
chmod -R 755 /app/media /app/celerybeat

# Migraciones — falla suave en BD virgen (init_database se encarga en lifespan)
# Solo intentamos si ya existe la tabla alembic_version
echo "[start.sh] Verificando si la BD necesita migración..."
python -c "
import asyncio, sys
from sqlalchemy import inspect
from app.database import engine

async def check():
    async with engine.begin() as conn:
        def _check(sync_conn):
            return 'alembic_version' in inspect(sync_conn).get_table_names()
        return await conn.run_sync(_check)

try:
    if asyncio.run(check()):
        sys.exit(0)
    sys.exit(1)
except Exception as e:
    print(f'[check] error: {e}', file=sys.stderr)
    sys.exit(1)
" && {
    echo "[start.sh] BD ya versionada, aplicando alembic upgrade head..."
    alembic upgrade head 2>&1 || echo "[start.sh] WARN: alembic upgrade falló (continuamos)"
} || {
    echo "[start.sh] BD virgen, init_database creará el esquema al arrancar uvicorn"
}

# Celery worker (background) — procesa pipeline IA, bot, notificaciones
echo "[start.sh] Lanzando Celery worker en background..."
celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency="$WORKER_CONCURRENCY" \
    -Q default,content,notifications \
    --logfile=/var/log/celery-worker.log \
    --detach

# Celery beat (background) — scheduler de tareas periódicas
echo "[start.sh] Lanzando Celery beat en background..."
celery -A app.celery_app beat \
    --loglevel=info \
    --schedule=/app/celerybeat/celerybeat-schedule \
    --logfile=/var/log/celery-beat.log \
    --detach

# Uvicorn (foreground — PID 1 del contenedor)
echo "[start.sh] Lanzando Uvicorn en 0.0.0.0:$PORT..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips='*'
