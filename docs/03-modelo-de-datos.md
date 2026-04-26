# 03 — Modelo de datos

## Diagrama lógico

```
┌──────────────┐     ┌────────────────┐
│SubscriptionPlan│   │    Tenant      │
│ (planes)     │◀──┤ (cuentas)       │──────┐──────┐──────┐──────┐
└──────────────┘     └────────────────┘      │      │      │      │
                              │              │      │      │      │
                              ▼              ▼      ▼      ▼      ▼
                      ┌──────────────┐  ┌────────┐ ┌──────┐ ┌──────┐ ┌──────┐
                      │ TenantConfig │  │Product │ │Custom│ │Order │ │Campaign
                      │ (1:1, keys)  │  │        │ │er    │ │      │ │      │
                      └──────────────┘  └───┬────┘ └──┬───┘ └─┬────┘ └──┬───┘
                                             │         │       │         │
                                             ▼         ▼       ▼         ▼
                                      ProductContent Conversation       AdSet
                                                       │                   │
                                                       ▼                   ▼
                                                    Message      AdPerformanceSnapshot
                                                                       │
                                                                       ▼
                                                              ShipmentEvent
```

Toda tabla tiene `tenant_id` (FK) excepto `SubscriptionPlan` que es global.

## Tablas

### `tenants` — usuarios/empresas

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | UUID PK | |
| `nombre_empresa` | str(200) | |
| `email` | str(255) UQ | login |
| `hashed_password` | str(255) | bcrypt |
| `dominio_personalizado` | str(255) | futuro: white-label |
| `activo` | bool | si false → 401 en cualquier request |
| `es_superadmin` | bool | bypass de plan limits, acceso a `/admin/*` |
| `plan_id` | int FK → subscription_plans | nullable (trial) |
| `estado_suscripcion` | enum | trial / active / suspended / cancelled |
| `created_at`, `updated_at` | timestamp | |

### `tenant_configs` — credenciales y settings (1:1 con tenants)

Tabla "ancha" por simplicidad. Todas las API keys cifradas con Fernet (sufijo `_enc`).

Campos cifrados: `shopify_api_key_enc`, `shopify_access_token_enc`, `meta_app_secret_enc`, `meta_access_token_enc`, `waba_token_enc`, `dropi_api_key_enc`, `smtp_password_enc`, `anthropic_api_key_enc`, `gemini_api_key_enc`, `openai_api_key_enc`, `kling_api_key_enc`, `heygen_api_key_enc`, `higgsfield_api_key_enc`.

Campos plain: URLs públicas, IDs, configuración de selección de modelo.

Selección de proveedor:
- `ai_provider` — claude | gemini | openai
- `video_provider` — kling | heygen | higgsfield

Modelos específicos por proveedor:
- `claude_model` — default `claude-sonnet-4-6`
- `gemini_model` — default `gemini-2.5-flash`
- `openai_model` — default `gpt-4o-mini`
- `kling_model` — default `kling-v1-6`

### `subscription_plans` — planes (global)

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | int PK | |
| `nombre` | str(50) UQ | "Pro", "Starter", etc. |
| `tier` | enum | starter / pro / enterprise |
| `max_productos`, `max_campanas`, `max_mensajes_bot` | int | cuotas |
| `precio_mensual` | int | **en centavos USD** |
| `activo` | bool | visible en UI de tenant |

### `products` — productos del tenant

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | FK | |
| `nombre` | str(500) | |
| `descripcion_input` | text | lo que el usuario escribió, alimenta a la IA |
| `precio` | numeric(12,2) | nullable |
| `precio_comparacion` | numeric(12,2) | precio tachado (descuento) |
| `inventario` | int | |
| `imagenes_originales` | JSON list | URLs de fotos subidas por el usuario |
| `contenido_generado` | bool | true cuando termina el pipeline |
| `publicado_shopify` | bool | |
| `shopify_product_id`, `shopify_url` | str | |

### `product_contents` — contenido IA (1:1 con product)

| Columna | Tipo | Notas |
|---------|------|-------|
| `product_id` | FK UQ | |
| `titulo_seo` | str(500) | máx 70 chars (SEO) |
| `descripcion_seo` | text | 150-200 palabras |
| `bullet_points` | JSON list | 5 beneficios |
| `variantes_copy` | JSON dict | `{"18-24": {"M": "...", "F": "...", "todos": "..."}, ...}` 21 variantes |
| `video_script` | text | guion 30-60 seg para Kling/HeyGen |
| `heygen_video_id` | str | id externo del video (Kling/HeyGen/Higgsfield) |
| `video_url` | str | URL final del video MP4 |
| `video_estado` | str | procesando / completed / failed |
| `imagenes_generadas` | JSON list | URLs de imágenes IA |
| `pipeline_paso` | int | 0=cola, 1=copy, 2=imágenes, 3=video, 4=publicado |

### `customers` — clientes finales del tenant

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | FK | |
| `nombre` | str(200) nullable | |
| `email` | str(255) nullable | |
| `telefono` | str(50) | |
| `whatsapp_id` | str(100) indexed | número en formato Meta (sin +, ej. "573001112222") |
| `messenger_id` | str(100) indexed | |
| `direccion`, `ciudad`, `departamento`, `pais` | | |

Se crean automáticamente al recibir primer mensaje del bot.

### `conversations` — chats con clientes

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | UUID PK | |
| `tenant_id`, `customer_id`, `product_id` (nullable), `campaign_id` (nullable) | FK | |
| `canal` | enum | whatsapp / messenger |
| `external_thread_id` | str | id del hilo en el canal externo |
| `estado` | enum | activa / transferida / cerrada |
| `confianza_promedio` | float | media de confianza de respuestas del bot |
| `venta_cerrada` | bool | true cuando se crea Order asociado |

### `messages` — mensajes individuales

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | int PK | |
| `conversation_id`, `tenant_id` | FK | |
| `rol` | enum | cliente / bot / humano |
| `contenido` | text | |
| `confianza` | float nullable | solo para mensajes del bot |
| `meta_message_id` | str | id en WhatsApp/Messenger para evitar duplicados |

### `orders` — pedidos

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | UUID PK | |
| `tenant_id`, `customer_id`, `product_id`, `conversation_id`, `campaign_id` | FK | |
| `cantidad`, `precio_unitario`, `subtotal`, `envio`, `total` | numeric | |
| `nombre_destinatario`, `telefono_destinatario`, `direccion_envio`, `ciudad_envio`, `departamento_envio` | str | |
| `dropi_order_id` | str | id en Dropi para tracking |
| `numero_seguimiento`, `transportadora` | str | |
| `estado` | enum | pendiente / confirmado / enviado / en_camino / entregado / fallido / cancelado |

### `shipment_events` — historial de envío

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | int PK | |
| `order_id`, `tenant_id` | FK | |
| `tipo` | enum | confirmado / enviado / en_camino / entregado / fallido / otro |
| `descripcion`, `ubicacion` | str | |

Lo poblan los workers `shipping_tracker` y los cambios manuales.

### `campaigns` — campañas Meta Ads

| Columna | Tipo | Notas |
|---------|------|-------|
| `id` | UUID PK | |
| `tenant_id`, `product_id` (nullable) | FK | |
| `nombre`, `meta_campaign_id` | str | |
| `meta_campaign_objective` | str | default "OUTCOME_SALES" |
| `presupuesto_diario`, `presupuesto_total`, `roas_minimo`, `cpc_maximo` | numeric | |
| `fecha_inicio`, `fecha_fin` | timestamp | |
| `estado` | enum | borrador / activa / pausada / finalizada / error |

### `ad_sets` — conjuntos de anuncios segmentados

7 por campaña típicamente (4 grupos de edad × M/F + 45+todos).

| Columna | Tipo | Notas |
|---------|------|-------|
| `meta_adset_id`, `meta_ad_id` | str | ids en Meta |
| `grupo_edad`, `genero` | str | "18-24" / "M" |
| `copy_anuncio` | text | la variante específica de este segmento |
| `impresiones`, `clics`, `gasto`, `conversiones`, `roas` | métricas live | actualizadas cada ciclo monitor |

### `ad_performance_snapshots` — historial de métricas

Una fila por campaña por ciclo de monitoreo (cada 30 min). Permite ver curvas de rendimiento en el tiempo.

## Índices y unique constraints importantes

- `tenants.email` UQ
- `subscription_plans.nombre` UQ
- `tenant_configs.tenant_id` UQ (1:1)
- `product_contents.product_id` UQ (1:1)
- `customers.whatsapp_id` indexed (lookup en cada webhook)
- Todos los `tenant_id` FK están indexed (joins de cada query)

## Reglas de borrado

- `Tenant` borrado → cascade a config, productos, clientes, pedidos, conversaciones (config en SQLAlchemy con `cascade="all, delete-orphan"`)
- `Customer` borrado → pedidos quedan **huérfanos** (intencional: mantener historial de ventas)
- `Product` borrado → campañas asociadas quedan apuntando a `null` (también intencional)

## Tabla `alembic_version`

Una sola fila con `version_num`. Apunta a la última migración aplicada. La maneja Alembic, no la toques manual salvo `init_database()` la primera vez.
