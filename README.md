# Venbot — Plataforma SaaS de Automatización E-commerce con IA

Sistema multi-tenant para automatizar todo el ciclo de ventas: generación de contenido con IA, publicación en Shopify, campañas Meta Ads segmentadas por edad/género, bot de ventas WhatsApp/Messenger, y rastreo de pedidos Dropi.

## Stack

| Componente | Tecnología |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Base de datos | PostgreSQL + SQLAlchemy (async) + Alembic |
| Cola de tareas | Celery + Redis |
| Frontend | Jinja2 + Alpine.js + TailwindCSS |
| IA | Claude API (Anthropic) + DALL-E 3 (OpenAI) |
| Video | HeyGen API |
| E-commerce | Shopify Admin API |
| Anuncios | Meta Marketing API |
| Mensajería | WhatsApp Business API + Facebook Messenger |
| Fulfillment | Dropi API |
| Email | SMTP genérico |

## Inicio rápido

### 1. Clonar y configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

Generar las claves necesarias:

```bash
# SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# ENCRYPTION_KEY (Fernet)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Levantar con Docker Compose

```bash
docker compose up -d
```

Servicios disponibles:
- App: http://localhost:8000
- Documentación API: http://localhost:8000/api/docs
- Flower (monitoreo Celery): http://localhost:5555

### 3. Migraciones (opcional, el app crea tablas automáticamente en dev)

```bash
docker compose exec app alembic upgrade head
```

### 4. Primer acceso

El super-admin se crea automáticamente al iniciar con las credenciales de `.env`:
- Email: `SUPERADMIN_EMAIL`
- Contraseña: `SUPERADMIN_PASSWORD`

Ve a http://localhost:8000/auth/iniciar-sesion para ingresar.

## Módulos del sistema

### Flujo de un producto nuevo

1. **Crear producto** → POST `/productos/` → lanza `content_pipeline` en Celery
2. **Pipeline de contenido** (background):
   - Claude genera título SEO, descripción, bullet points, variantes de copy por segmento (edad+género), guión de video
   - HeyGen genera el video con el guión
3. **Publicar en Shopify** → el bot o el dashboard publican el producto
4. **Crear campaña Meta Ads** → POST `/campanas/` + `/campanas/{id}/lanzar`
   - Se crean automáticamente AdSets por cada segmento con el copy personalizado
5. **Bot de ventas** responde en WhatsApp/Messenger con contexto del producto
6. **Pedido creado** en Dropi cuando el cliente da sus datos de envío
7. **Rastreo automático** cada 2h — notifica al cliente por WhatsApp y email

### Workers Celery

| Worker | Frecuencia | Función |
|---|---|---|
| `campaign_monitor` | Cada 30 min | Métricas Meta Ads, auto-pausa por ROAS/CPC |
| `shipping_tracker` | Cada 2 horas | Estado Dropi, notificaciones al cliente |
| `content_pipeline` | On-demand | Genera contenido IA al crear producto |
| `bot_processor` | On-demand | Procesa mensajes WhatsApp/Messenger |

### Webhooks

Configura en Meta Business Manager:
- **WhatsApp:** `https://tudominio.com/bot/whatsapp/webhook/{tenant_id}`
- **Messenger:** `https://tudominio.com/bot/messenger/webhook/{tenant_id}`

`tenant_id` es el UUID del tenant, visible en el perfil.

## Estructura del proyecto

```
app/
├── main.py              # Entry point FastAPI
├── config.py            # Settings (pydantic-settings)
├── database.py          # AsyncEngine + SessionLocal
├── celery_app.py        # Celery + beat schedule
├── core/
│   ├── security.py      # JWT, bcrypt, Fernet
│   └── deps.py          # Dependencias FastAPI
├── models/              # SQLAlchemy ORM
├── schemas/             # Pydantic schemas
├── api/                 # Routers FastAPI
├── services/            # Lógica de negocio + integraciones API
├── workers/             # Tareas Celery
└── templates/           # Jinja2 + Alpine.js (dashboard)
```

## Deploy en producción (Coolify + Traefik)

1. Configurar dominio en `APP_DOMAIN` en `.env`
2. Los labels de Traefik ya están en `docker-compose.yml`
3. `docker compose up -d`

## Seguridad

- Credenciales de tenants cifradas en BD con Fernet
- JWT con refresh tokens
- Aislamiento estricto por `tenant_id` en todas las queries
- Variables sensibles solo en `.env` (nunca en código)

## Desarrollo

```bash
# Instalar dependencias localmente
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Levantar solo la infraestructura
docker compose up postgres redis -d

# Correr la app en modo desarrollo
uvicorn app.main:app --reload

# Correr worker Celery
celery -A app.celery_app worker --loglevel=info
```
