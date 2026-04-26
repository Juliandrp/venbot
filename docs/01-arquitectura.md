# 01 — Arquitectura

## Visión general

Venbot es una **aplicación web multi-tenant** que combina:

- **API REST** (FastAPI) para todas las operaciones CRUD y la lógica de negocio
- **Frontend server-side** (Jinja2 + Alpine.js + Tailwind) — sin SPA, navegación tradicional + reactividad puntual
- **Workers asíncronos** (Celery) para tareas largas: generación IA, notificaciones, monitoreo
- **Base de datos** (PostgreSQL) — schema único compartido por todos los tenants, isolation por `tenant_id`
- **Cola** (Redis) para Celery broker + result backend
- **Storage abstracto** — local por defecto, S3-compatible opcional
- **Reverse proxy** (Traefik vía Coolify) para HTTPS automático con Let's Encrypt

## Diagrama de flujo

```
┌──────────┐     ┌──────────────┐     ┌──────────┐
│ Usuario  │────▶│  Traefik     │────▶│ FastAPI  │
│ (browser)│     │  (HTTPS)     │     │ (uvicorn)│
└──────────┘     └──────────────┘     └────┬─────┘
                                            │
              ┌─────────────────────────────┼──────────────────────┐
              │                             │                      │
              ▼                             ▼                      ▼
       ┌──────────────┐              ┌────────────┐         ┌─────────────┐
       │  PostgreSQL  │              │   Redis    │◀────────│ Celery      │
       │  (datos)     │              │ (cola+cache)│         │ worker+beat │
       └──────────────┘              └────────────┘         └──────┬──────┘
                                                                    │
                              ┌─────────────────────────────────────┼─────────────────┐
                              ▼                  ▼                  ▼                 ▼
                       ┌──────────┐      ┌──────────┐       ┌────────────┐   ┌──────────┐
                       │  Gemini  │      │ Pollin.  │       │  Kling     │   │  Meta    │
                       │  /Claude │      │  Imagen3 │       │  Higgs.    │   │  Ads     │
                       │  /OpenAI │      │  DALL-E  │       │  HeyGen    │   │  WhatsAp │
                       └──────────┘      └──────────┘       └────────────┘   └──────────┘
                          (texto)         (imágenes)           (video)         (publicidad)
```

## Componentes principales

### `app/main.py` — FastAPI lifespan

Al arrancar:
1. Llama a `init_database()` — crea schema si la BD está vacía, marca como migrada
2. Llama a `_seed_superadmin()` — crea/actualiza el super-admin desde `.env`
3. Monta routers, archivos estáticos, `/media`

### `app/api/` — Routers REST

Un router por dominio:
- `auth.py` — registro, login, refresh token
- `tenants.py` — perfil, configuración, planes disponibles, uso
- `products.py` — CRUD productos + upload imágenes + pipeline trigger
- `campaigns.py` — CRUD campañas + lanzar/pausar/sincronizar Meta
- `bot.py` — webhooks WhatsApp/Messenger + endpoints conversación
- `orders.py` — listar pedidos + cambio de estado + reenviar notificación
- `customers.py` — CRUD clientes
- `dashboard.py` — métricas + vistas HTML
- `admin.py` — super-admin: gestión tenants, planes, métricas globales
- `billing.py` — checkout Stripe/MercadoPago + webhooks de pago

### `app/models/` — ORM (SQLAlchemy 2.0 async)

- `tenant.py` — Tenant, TenantConfig, SubscriptionPlan
- `product.py` — Product, ProductContent
- `campaign.py` — Campaign, AdSet, AdPerformanceSnapshot
- `bot.py` — Conversation, Message
- `order.py` — Order, ShipmentEvent
- `customer.py` — Customer

### `app/services/` — Adaptadores externos

Cada servicio externo tiene su archivo. Patrón: clase con métodos async + retry con tenacity.

- IA texto: `ai_content.py` (Claude), `gemini_service.py`, `openai_content_service.py`
- Imágenes: `pollinations_service.py` (gratis), `imagen_service.py`, `dalle_service.py`
- Video: `kling_service.py`, `higgsfield_service.py`, `heygen.py`
- Comercio: `shopify_service.py`, `meta_ads.py`, `dropi_service.py`
- Comunicación: `whatsapp.py`, `email_service.py`
- Pagos: `payments.py` (Stripe + MercadoPago)
- Storage: `storage.py` (local + S3)
- Validación: `plan_limits.py`

### `app/workers/` — Tareas Celery

- `content_pipeline.py` — pipeline IA completo (4 pasos)
- `bot_processor.py` — procesa mensajes WhatsApp/Messenger
- `campaign_monitor.py` — revisa campañas Meta cada 30 min
- `shipping_tracker.py` — consulta Dropi cada 2 horas
- `notifications.py` — envía notificaciones a clientes

Ver [05-workers-y-tareas.md](05-workers-y-tareas.md) para detalle.

### `app/templates/` — Frontend

Jinja2 + Tailwind + Alpine.js. Una carpeta por dominio:
`auth/`, `dashboard/`, `products/`, `campaigns/`, `orders/`, `customers/`, `billing/`, `bot/`, `settings/`, `admin/`, `manual/`.

### `app/db_init.py`

Inicializa la BD al arrancar uvicorn. Si la tabla `alembic_version` no existe → corre `create_all` + stamp manual. Si existe → no hace nada (las migraciones corren desde `start.sh` antes de uvicorn).

### `start.sh`

Script de arranque del contenedor en producción (un solo container con todo):
1. `alembic upgrade head` (si la BD ya está versionada)
2. `celery worker --detach`
3. `celery beat --detach`
4. `exec uvicorn` (PID 1)

## Aislamiento multi-tenant

Cada tabla tiene `tenant_id` (FK a `tenants`). **Cada query** filtra por `tenant_id` del usuario autenticado:

```python
result = await db.execute(
    select(Producto).where(Producto.tenant_id == tenant.id)
)
```

El `tenant` viene de `Depends(get_current_tenant)` que decodifica el JWT y carga el tenant desde BD.

**Sin esto, cualquier usuario podría ver datos de otros.** Es la regla de oro.

## Por qué un solo contenedor en vez de docker-compose

Coolify tipo "Application" deploya una sola imagen Docker. Para correr uvicorn + worker + beat juntos, el `start.sh` los lanza dentro del mismo container con `--detach`. Equivalente al patrón php-fpm + nginx que usa Laravel.

Tradeoff: si el worker crashea, el container entero se reinicia (no hay aislamiento). Para escalar: separar worker en una segunda app Coolify apuntando al mismo repo, con `start.sh` distinto.

## Próximos pasos arquitectónicos

- **Separar worker y beat en contenedores propios** cuando supere ~1000 productos/día
- **Migrar storage a S3/R2** para no depender del volumen del VPS
- **Agregar Sentry** para captura de errores centralizada
- **Logging estructurado** (JSON) en vez de print/logging básico
- **Cache de tenant config** en Redis para evitar query por request
