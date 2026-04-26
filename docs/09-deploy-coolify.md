# 09 — Deploy en Coolify

## Estado actual de producción

- **VPS**: Hostinger 168.231.70.175
- **Coolify**: 4.0.0-beta.468
- **App ID en Coolify**: 17 (`zg9cndhm0uhttuwfltfuue3j`)
- **Repo conectado**: github.com/Juliandrp/venbot, branch `main`
- **Domain**: https://almabot.matriz.cloud
- **Build pack**: Dockerfile (NO nixpacks)
- **Project Coolify**: `matriz`

## Cómo se deploya

```
git push origin main
       │
       ▼
GitHub webhook → Coolify
       │
       ▼
Coolify clona repo, lee Dockerfile
       │
       ▼
docker build -t zg9cndhm:<sha> .
       │
       ▼
docker run con:
  - env vars (cifradas en BD Coolify)
  - volumen venbot_media → /app/media
  - port 8000 expuesto
  - network coolify
       │
       ▼
start.sh:
  1. alembic upgrade head
  2. celery worker --detach
  3. celery beat --detach
  4. uvicorn (PID 1)
       │
       ▼
Cron sync-almabot-traefik.sh (cada minuto)
detecta el nuevo container y actualiza
/data/coolify/proxy/dynamic/almabot.yaml
       │
       ▼
Traefik recarga config y enruta tráfico al nuevo container
```

## Componentes externos al app container

Los corremos como containers separados en la network `coolify`:

| Container | Imagen | Volumen |
|-----------|--------|---------|
| `venbot-postgres` | postgres:18-alpine | `venbot_postgres` |
| `venbot-redis` | redis:7-alpine | `venbot_redis` |

Configurados con `--network coolify --network-alias venbot-postgres` para que la app los encuentre por nombre.

**Estos NO los gestiona Coolify UI** — son contenedores manuales fuera de su control. Tradeoff: más simple para empezar, no hay backups automáticos.

Para migrar a Resources de Coolify (recomendado a largo plazo), ver al final.

## Variables de entorno

Las gestiona Coolify (cifradas con Laravel Encrypter en su BD `coolify-db`). UI: tu app → Environment Variables.

Críticas para que arranque:
```
SECRET_KEY=<random hex 64>
ENCRYPTION_KEY=<Fernet key>
DATABASE_URL=postgresql+asyncpg://venbot:<pass>@venbot-postgres:5432/venbot_db
SYNC_DATABASE_URL=postgresql://venbot:<pass>@venbot-postgres:5432/venbot_db
REDIS_URL=redis://:<pass>@venbot-redis:6379/0
CELERY_BROKER_URL=redis://:<pass>@venbot-redis:6379/1
CELERY_RESULT_BACKEND=redis://:<pass>@venbot-redis:6379/2
PORT=8000
APP_BASE_URL=https://almabot.matriz.cloud
SUPERADMIN_EMAIL=admin@venbot.io
SUPERADMIN_PASSWORD=<set en config>
ENVIRONMENT=production
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=/app/media
STORAGE_LOCAL_BASE_URL=/media
```

Opcionales (vacías si no usas):
```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
KLING_API_KEY=
HIGGSFIELD_API_KEY=
PAYMENT_PROVIDER=         # vacío | "stripe" | "mercadopago"
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
MERCADOPAGO_ACCESS_TOKEN=
MERCADOPAGO_WEBHOOK_SECRET=
```

## El "hack" del YAML de Traefik

**Problema**: Coolify configura Traefik con `--providers.docker=false`. Ignora los labels Traefik del docker-compose. Solo lee archivos YAML estáticos de `/data/coolify/proxy/dynamic/`.

**Solución**: cada deploy regenera el container con un nombre nuevo (`zg9cndhm-<timestamp>`). Mantenemos un YAML que apunta al container activo:

```yaml
# /data/coolify/proxy/dynamic/almabot.yaml
http:
  routers:
    venbot-router:
      rule: "Host(`almabot.matriz.cloud`)"
      service: venbot-service
      entryPoints: [https]
      tls:
        certResolver: letsencrypt
    venbot-http-router:
      rule: "Host(`almabot.matriz.cloud`)"
      service: venbot-service
      entryPoints: [http]
      middlewares: [redirect-to-https]
  middlewares:
    redirect-to-https:
      redirectScheme: { scheme: https, permanent: true }
  services:
    venbot-service:
      loadBalancer:
        servers:
          - url: "http://zg9cndhm0uhttuwfltfuue3j-XXXXXXX:8000"  # ← se actualiza solo
```

Y un cron job en el VPS lo mantiene sincronizado:

```bash
# /etc/cron.d/almabot-traefik-sync
* * * * * root /usr/local/bin/sync-almabot-traefik.sh
```

El script detecta el container activo (filtrando por prefijo `zg9cndhm`) y actualiza el `url:` si cambió. Idempotente, log en `/var/log/almabot-traefik-sync.log`.

## Cómo desplegar manualmente

Si necesitas forzar un deploy desde el server (sin git push):

```bash
# Generar API token (una sola vez)
TOKEN=$(openssl rand -hex 32)
HASHED=$(echo -n "$TOKEN" | sha256sum | awk '{print $1}')
docker exec coolify-db psql -U coolify -c \
  "INSERT INTO personal_access_tokens (tokenable_type, tokenable_id, name, token, team_id, abilities, created_at, updated_at) VALUES ('App\\Models\\User', 0, 'manual-deploy', '$HASHED', '0', '[\"*\"]', NOW(), NOW());"
echo "$TOKEN" > /root/coolify-token.txt

# Habilitar API (una sola vez)
docker exec coolify-db psql -U coolify -c "UPDATE instance_settings SET is_api_enabled=true;"

# Trigger deploy
docker exec coolify curl -s \
  -X GET 'http://localhost:8080/api/v1/deploy?uuid=zg9cndhm0uhttuwfltfuue3j&force=true' \
  -H "Authorization: Bearer $(cat /root/coolify-token.txt)"
```

## Cómo agregar un dominio nuevo (para vender white-label)

1. En el panel admin de Coolify → tu app → Domains → agregar
2. Cliente apunta su DNS A al IP del server
3. Coolify emite cert SSL automático con Let's Encrypt
4. **Editar el YAML** de Traefik para incluir el nuevo dominio en el rule (o crear otro YAML)

## Logs y diagnóstico

```bash
# App logs
docker logs --tail 100 -f $(docker ps --filter name=zg9cndhm --format '{{.Names}}' | head -1)

# Celery worker
docker exec <container> tail -f /var/log/celery-worker.log

# Celery beat
docker exec <container> tail -f /var/log/celery-beat.log

# Postgres
docker logs venbot-postgres

# Redis
docker logs venbot-redis

# Traefik
docker logs coolify-proxy

# Cron sync
tail -f /var/log/almabot-traefik-sync.log
```

## Reiniciar la app

```bash
# Soft (preserva BD y volúmenes)
docker restart $(docker ps --filter name=zg9cndhm --format '{{.Names}}' | head -1)

# Hard (recrea container — equivalente a redeploy)
docker exec coolify curl -X GET \
  'http://localhost:8080/api/v1/deploy?uuid=zg9cndhm0uhttuwfltfuue3j&force=true' \
  -H "Authorization: Bearer $(cat /root/coolify-token.txt)"
```

## Migrar a Resources oficiales de Coolify

Si quieres que Postgres/Redis se gestionen desde la UI de Coolify (con backups automáticos):

1. Coolify UI → tu Project → New Resource → PostgreSQL
2. Coolify crea el container y te da las credenciales
3. **Migrar datos**:
   ```bash
   docker exec venbot-postgres pg_dump -U venbot venbot_db | \
     docker exec -i <nuevo-coolify-postgres> psql -U <nuevo-user> <nueva-db>
   ```
4. Actualizar `DATABASE_URL` y `SYNC_DATABASE_URL` en env vars de Coolify
5. Redeploy
6. Cuando confirmes que todo funciona: `docker rm -f venbot-postgres` y `docker volume rm venbot_postgres`

Mismo proceso para Redis.

## Próximas mejoras de deploy

- **CI/CD con GitHub Actions** que corra `pytest` antes de permitir merge a `main`
- **Deploy desde `develop`** y merge manual a `main` solo cuando esté validado
- **Healthcheck en el Dockerfile** (`HEALTHCHECK CMD curl -f http://localhost:8000/health`) para que Docker reinicie automáticamente si la app cuelga
- **Logging estructurado** a stdout en JSON, recogido por un agregador (Loki, Datadog)
