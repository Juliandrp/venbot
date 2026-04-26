# 11 — Troubleshooting

Catálogo de problemas conocidos y cómo diagnosticarlos.

## La app no arranca / 503 desde Traefik

### Síntoma
- `curl https://almabot.matriz.cloud/health` → `503 Service Unavailable` "no available server"
- O timeout de la request

### Diagnóstico
```bash
# 1. ¿Está corriendo el container?
docker ps --filter name=zg9cndhm

# 2. ¿En estado "Restarting"?
docker logs --tail 50 <container>

# 3. ¿Coolify-proxy puede llegar al container?
IP=$(docker inspect <container> --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
docker exec coolify-proxy wget -qO- http://$IP:8000/health

# 4. ¿El YAML de Traefik apunta al container correcto?
cat /data/coolify/proxy/dynamic/almabot.yaml
```

### Causas comunes

| Causa | Fix |
|-------|-----|
| Container en restart loop | Ver logs, usualmente: env var faltante o BD no responde |
| YAML apunta a container viejo | `/usr/local/bin/sync-almabot-traefik.sh` o esperar 1 min |
| Container no está en network coolify | `docker network connect coolify <container>` |

---

## Container reinicia en loop

### Síntoma
`docker ps` muestra `Restarting (X) Y seconds ago`

### Diagnóstico
```bash
docker logs --tail 100 <container>
```

### Causas comunes

| Log dice | Causa | Fix |
|----------|-------|-----|
| `bash: -c: option requires an argument` | Coolify usa Custom Start Command vacío | Verificar `start_command` en BD: `docker exec coolify-db psql -U coolify -c "SELECT start_command FROM applications WHERE id=17;"` |
| `relation "X" does not exist` | Migración no corrió | Ejecutar `alembic upgrade head` manualmente |
| `connection refused` (Postgres) | venbot-postgres caído | `docker ps venbot-postgres` y reiniciar si hace falta |
| `Future attached to different loop` | Worker usa `AsyncSessionLocal` global | Cambiar a `make_celery_session()` |

---

## Pipeline IA se queda en "En cola..."

### Síntoma
Producto creado, pasa minutos sin avanzar la barra.

### Diagnóstico
```bash
# 1. ¿Worker corriendo?
docker exec <container> ps aux | grep celery

# 2. ¿Hay tareas en la cola Redis?
docker exec venbot-redis redis-cli -a $REDIS_PASS LLEN celery

# 3. Logs del worker
docker exec <container> tail -100 /var/log/celery-worker.log
```

### Causas comunes

| Log dice | Causa | Fix |
|----------|-------|-----|
| `404 Not Found` (Gemini) | Modelo deprecated | Cambiar `gemini_model` en Configuración a uno válido |
| `401 Unauthorized` | API key inválida | Re-pegar key en Configuración |
| `429 Too Many Requests` | Rate limit del proveedor | Esperar / cambiar a otro proveedor |
| `RetryError` | El servicio externo está caído | Esperar y revisar status del proveedor |
| Sin output de Celery | Worker no se inició | Reiniciar container |

---

## Modal "no se cierra" después de crear producto

### Síntoma
Creas producto, todo dice "Listo" pero el modal sigue abierto.

### Causa
Bug conocido y fixed en commit `6144e0a`: `cerrarModal()` tenía `if (this.subiendo) return` y `subiendo` aún era `true` al llamarlo. Fixed cerrando con `modalNuevo = false` directo.

Si lo ves en otra parte de la app, aplica el mismo patrón.

---

## "undefined%" en barra de progreso

### Causa
Frontend hace `[0,25,50,75,90][p.pipeline_paso] + '%'`. Si `pipeline_paso` es `null`, resultado es `"undefined%"`.

### Fix
```javascript
[5,25,50,75,90][p.pipeline_paso || 0] + '%'
```

Aplicado en `templates/products/index.html`.

---

## "Input should be a valid integer" al guardar settings

### Causa
Form HTML envía `""` (string vacío) cuando el campo `<input type="number">` está vacío. Pydantic falla al parsearlo como int.

### Fix
Validators `field_validator(mode="before")` que convierten `""` a `None` o al default.

Aplicado en:
- `TenantConfigIn.smtp_port`
- `ProductCreate/Update.precio*, inventario`
- `CampaignCreate/Update.presupuesto_diario, roas_minimo, fechas, product_id`

Si agregas un campo numeric nuevo en un schema, **agrégale el validator**.

---

## Bot no responde mensajes de WhatsApp

### Diagnóstico

```bash
# 1. ¿Llega el webhook?
docker logs <container> | grep "POST /bot/whatsapp"

# 2. ¿Se encola la tarea?
docker exec <container> tail -50 /var/log/celery-worker.log | grep procesar_mensaje
```

### Causas comunes

| Síntoma | Causa | Fix |
|---------|-------|-----|
| No hay logs del webhook | Meta no está enviando | Revisar configuración del webhook en Meta Developers |
| Webhook devuelve 403 | `verify_token` no coincide | Mismo valor en Meta y en Configuración de Venbot |
| Webhook OK pero no respuesta | API key IA inválida | Revisar logs del worker |
| Bot responde solo a algunos | Plan límite excedido | `verificar_puede_enviar_mensaje_bot` rechaza |

---

## Cert Let's Encrypt no se emite

### Síntoma
Browser muestra warning de cert no confiable.

### Diagnóstico
```bash
docker logs coolify-proxy | grep -i "letsencrypt\|acme\|almabot"
```

### Causas

| Causa | Fix |
|-------|-----|
| DNS no propagado | Esperar y verificar: `dig almabot.matriz.cloud` |
| Rate limit Let's Encrypt | 5 errores → bloqueo 1 hora; 50 certs/semana por dominio |
| YAML de Traefik mal formado | Validar yaml: `python -c "import yaml; yaml.safe_load(open('/data/coolify/proxy/dynamic/almabot.yaml'))"` |

---

## Errores 422 con detail = `[{...}]`

### Causa
Pydantic devuelve array de errores. Frontend asume string y muestra "[object Object]".

### Fix en frontend
```javascript
const detail = err.detail;
const msg = Array.isArray(detail)
  ? detail.map(e => e.msg).join('; ')
  : (detail || 'Error');
```

Patrón aplicado en settings, customers, campaigns, billing.

---

## Cómo regenerar las API keys de un tenant

Si un tenant pierde acceso a sus credenciales (ej. olvidó su key de Anthropic):

```sql
-- Ver qué tiene configurado
SELECT
  CASE WHEN anthropic_api_key_enc IS NULL THEN 'no' ELSE 'sí' END as anthropic,
  CASE WHEN gemini_api_key_enc IS NULL THEN 'no' ELSE 'sí' END as gemini,
  ai_provider
FROM tenant_configs WHERE tenant_id = '<uuid>';

-- Limpiar una key específica
UPDATE tenant_configs SET anthropic_api_key_enc = NULL WHERE tenant_id = '<uuid>';
```

El tenant podrá ingresar una key nueva desde Configuración.

---

## "DecryptException" al leer env vars de Coolify

### Causa
Insertaste valores en `environment_variables` SIN cifrar con Laravel. Coolify intenta descifrarlos y falla.

### Fix
Cifrar con `encrypt()` de Laravel antes de insertar:

```bash
docker exec coolify php -r "
require 'vendor/autoload.php';
\$app = require 'bootstrap/app.php';
\$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
echo encrypt('mi-valor');
"
```

Y guardar el resultado en la columna `value`.

Más fácil: usar siempre la UI de Coolify para env vars.

---

## Worker no procesa nada después de un deploy

### Diagnóstico
```bash
docker exec <container> ps aux | grep celery
```

Si no aparecen procesos celery → `start.sh` no los lanzó.

### Causa
`start.sh` no tiene permisos de ejecución o crashea antes de llegar a celery.

### Fix
Verificar Dockerfile:
```dockerfile
RUN chmod +x /app/start.sh
CMD ["bash", "/app/start.sh"]
```

Y que `start.sh` use `--detach` para celery (no espera bloquea uvicorn).

---

## Comandos diagnósticos útiles

```bash
# Espacio en disco
df -h

# Uso del volumen media
du -sh /var/lib/docker/volumes/venbot_media

# Conexiones activas a Postgres
docker exec venbot-postgres psql -U venbot -c \
  "SELECT count(*), state FROM pg_stat_activity WHERE datname='venbot_db' GROUP BY state;"

# Memoria de los containers
docker stats --no-stream | grep -E "zg9cndhm|venbot-"

# Tamaño BD
docker exec venbot-postgres psql -U venbot -d venbot_db -c \
  "SELECT pg_size_pretty(pg_database_size('venbot_db'));"
```

---

## Cuándo escalar

Indicadores de que necesitas más recursos:

| Síntoma | Acción |
|---------|--------|
| Worker procesa lento, cola crece | Aumentar `WORKER_CONCURRENCY` o separar worker en su propio container |
| BD lenta en queries | Agregar índices en columnas que filtras seguido |
| Disco lleno | Migrar a S3 (`STORAGE_BACKEND=s3`) |
| Pico de tráfico colapsa app | Sumar Cloudflare delante (cache + rate limit) |
| Cert renewal falla | Revisar logs de Coolify-proxy |
