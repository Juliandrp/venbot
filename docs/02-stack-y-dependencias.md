# 02 — Stack y dependencias

## Versiones core

| Componente | Versión | Por qué |
|------------|---------|---------|
| Python | 3.12-slim | Moderno, soporte completo `match`/`type \|`, asyncio maduro |
| FastAPI | 0.115.5 | Async nativo, generación OpenAPI, deps injection |
| SQLAlchemy | 2.0.36 | API 2.0 con `Mapped`/`mapped_column`, async first-class |
| asyncpg | 0.30.0 | Driver Postgres async más rápido |
| Alembic | 1.14.0 | Migraciones de schema con autogenerate |
| Celery | 5.4.0 | Cola estándar para tareas async en Python |
| Redis | 5.2.0 (cliente) / 7-alpine (server) | Broker + cache + result backend |
| Pydantic | 2.10.3 | Validación con `field_validator`, performance C |
| Anthropic SDK | 0.40.0 | Cliente oficial Claude |
| google-genai | 1.10.0 | Cliente oficial Gemini (nuevo, reemplazó google-generativeai) |
| openai | 1.57.0 | Cliente oficial OpenAI |
| boto3 | 1.35.81 | Solo si `STORAGE_BACKEND=s3` |
| stripe | 11.4.1 | Solo si `PAYMENT_PROVIDER=stripe` |
| mercadopago | 2.2.3 | Solo si `PAYMENT_PROVIDER=mercadopago` |

## Frontend (sin build step)

- **Tailwind CSS** vía CDN (`cdn.tailwindcss.com`) — desarrollo rápido sin webpack
- **Alpine.js** 3.x vía CDN — reactividad ligera, no necesita compilación
- **Chart.js** 4 vía CDN — gráficas opcionales
- **Inter** desde Google Fonts — tipografía sans-serif moderna

> **Decisión consciente**: no hay React/Vue/Svelte/build step. Todo el frontend es server-rendered con Jinja + reactividad puntual con Alpine. Resultado: cero infraestructura frontend, cambios visibles instantáneos al editar HTML.

## Auth

- **python-jose[cryptography]** 3.3.0 — JWT (access + refresh)
- **passlib[bcrypt]** 1.7.4 + **bcrypt** 4.0.1 — hash de passwords (4.0.1 fix por incompatibilidad bcrypt 5.x con passlib)
- **cryptography** 43.0.3 — Fernet para cifrar API keys de tenants en BD

## Pinning específico que NO debes tocar sin razón

| Paquete | Versión pinned | Razón |
|---------|----------------|-------|
| `bcrypt==4.0.1` | Exacta | bcrypt 5.0+ rompe con passlib 1.7.x |
| `httpx==0.28.1` | Exacta | google-genai exige >=0.28.1, FastAPI puede romperse en 0.29+ |
| `pydantic==2.10.3` | Exacta | 2.11 cambia comportamiento de `field_validator` |
| `pydantic[email]==2.10.3` | Línea separada | extras de email-validator |

## Email

- **aiosmtplib** 3.0.2 — SMTP async puro Python, funciona con Gmail/SendGrid/Resend/Mailgun

## Tests

- **pytest** 8.3.4 + **pytest-asyncio** 0.25.0 — runner async
- **pytest-cov** 6.0.0 — cobertura
- **aiosqlite** 0.20.0 — SQLite async para tests aislados

## Monitoring opcional

- **prometheus-fastapi-instrumentator** 7.0.0 — métricas /metrics si lo activas
- **flower** 2.0.1 — UI de Celery (no se deploya en producción todavía)

## Sistema operativo del container

- Base: `python:3.12-slim` (Debian)
- Paquetes APT: `build-essential` (compilar), `libpq-dev` (psycopg2/asyncpg), `curl` (healthchecks), `bash` (start.sh)

## Variables de entorno requeridas

Ver [`.env.example`](../.env.example) para lista completa. Las críticas:

| Var | Por qué |
|-----|---------|
| `SECRET_KEY` | Firma de JWTs |
| `ENCRYPTION_KEY` | Fernet — descifrar API keys de tenants |
| `DATABASE_URL` | Postgres async URL |
| `REDIS_URL` | Cache + Celery |
| `CELERY_BROKER_URL` | DB Redis para cola (puede ser misma instancia, distinta DB) |
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` | Bootstrap del primer admin |

## Dependencias que considera **opcionales**

Estas se importan dentro de funciones, no al top del archivo. Si no usas la feature, no necesitas la lib instalada:

- `google.genai` — solo se importa dentro de `gemini_service.py`
- `boto3` — solo se importa dentro de `storage.py` cuando `STORAGE_BACKEND=s3`
- `stripe` / `mercadopago` — solo se importan dentro de `payments.py`

Esto permite imágenes Docker más pequeñas si removes lo que no uses.

## Cómo agregar un proveedor IA nuevo

1. Crear `app/services/<nombre>_service.py` con función async `generar_contenido_producto(nombre, descripcion, api_key, image_urls, model)` que retorne dict con shape compatible
2. Agregar columna `<nombre>_api_key_enc` y `<nombre>_model` a `TenantConfig`
3. Crear migración Alembic
4. Agregar al `TenantConfigIn` / `TenantConfigOut` schema
5. Agregar opciones en el selector de Configuración (`templates/settings/index.html`)
6. Agregar branch en `content_pipeline.py` para usar el nuevo proveedor

Ver [06-pipeline-ia.md](06-pipeline-ia.md) para detalle.
