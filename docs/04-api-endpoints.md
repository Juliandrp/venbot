# 04 — API endpoints

Referencia de todos los endpoints. Auth por defecto: **Bearer JWT** en header `Authorization`. Endpoints marcados con 🌐 son públicos.

OpenAPI auto-generado disponible en `/api/docs` (Swagger) y `/api/redoc`.

---

## 🔐 `/auth` — Autenticación

| Método | Path | Body | Response |
|--------|------|------|----------|
| 🌐 POST | `/auth/register` | `{nombre_empresa, email, password}` | `{access_token, refresh_token, token_type}` |
| 🌐 POST | `/auth/login` | `{email, password}` | tokens |
| 🌐 POST | `/auth/refresh` | `{refresh_token}` | tokens nuevos |
| 🌐 GET | `/auth/iniciar-sesion` | — | HTML login |
| 🌐 GET | `/auth/registro` | — | HTML registro |

Tokens: access dura 60 min, refresh dura 30 días. JWT firmado con `SECRET_KEY` (HS256).

---

## 👤 `/tenant` — Mi cuenta

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/tenant/me` | Mi perfil — incluye `es_superadmin` para condicionales en UI |
| GET | `/tenant/uso` | Uso actual vs límites del plan |
| GET | `/tenant/planes-disponibles` | Lista de planes activos |
| POST | `/tenant/upgrade-plan` | Body: `{plan_id}` — activa plan manual (sin pago real) |
| GET | `/tenant/config` | Configuración (sin valores cifrados, solo flags `tiene_X_key`) |
| PUT | `/tenant/config` | Actualiza config y guarda keys cifradas |

---

## 📦 `/productos` — Productos

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/productos/` | Lista paginada — incluye `pipeline_paso` |
| POST | `/productos/` | Crear (limit-checked) |
| GET | `/productos/{id}` | Detalle con `contenido` (relación cargada) |
| PATCH | `/productos/{id}` | Editar campos básicos |
| DELETE | `/productos/{id}` | Eliminar (soft: `activo=false`) |
| POST | `/productos/{id}/imagenes` | Multipart — sube fotos + dispara pipeline |
| POST | `/productos/{id}/regenerar-contenido` | Re-dispara pipeline IA |
| POST | `/productos/{id}/publicar-shopify` | Publica en Shopify manualmente |
| 🌐 GET | `/productos/vista/lista` | HTML lista |
| 🌐 GET | `/productos/vista/{id}` | HTML detalle |

Validación de límite: `verificar_puede_crear_producto` antes de POST.

---

## 📣 `/campanas` — Campañas

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/campanas/` | Lista de campañas del tenant |
| POST | `/campanas/` | Crear (limit-checked, estado `borrador`) |
| PATCH | `/campanas/{id}` | Editar — sincroniza a Meta si tiene `meta_campaign_id` |
| DELETE | `/campanas/{id}` | Eliminar |
| POST | `/campanas/{id}/lanzar` | Crea en Meta, cambia a `activa` |
| POST | `/campanas/{id}/pausar` | Marca `pausada` (no llama a Meta — mejorable) |

---

## 🛒 `/pedidos` — Pedidos

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/pedidos/` | Lista paginada |
| GET | `/pedidos/{id}` | Detalle |
| PATCH | `/pedidos/{id}/estado` | Body: `{estado, numero_seguimiento, transportadora, notificar_cliente}` — dispara notificación si cambió |
| POST | `/pedidos/{id}/reenviar-notificacion` | Encola notificación del estado actual |

---

## 👥 `/clientes` — Clientes

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/clientes/?q=texto` | Lista + búsqueda en nombre/email/tel/whatsapp |
| POST | `/clientes/` | Crear manual |
| GET | `/clientes/{id}` | Detalle (incluye total_pedidos y total_gastado) |
| PATCH | `/clientes/{id}` | Editar |
| DELETE | `/clientes/{id}` | Eliminar (pedidos quedan sin customer_id) |
| 🌐 GET | `/clientes/vista/lista` | HTML lista |

---

## 💬 `/bot` — Bot de ventas

| Método | Path | Descripción |
|--------|------|-------------|
| 🌐 GET | `/bot/whatsapp/webhook/{tenant_id}` | Verificación Meta (hub.challenge) |
| 🌐 POST | `/bot/whatsapp/webhook/{tenant_id}` | Recibe mensajes WhatsApp — encola `procesar_mensaje_whatsapp` |
| 🌐 GET/POST | `/bot/messenger/webhook/{tenant_id}` | Idem para Messenger |
| GET | `/bot/conversaciones` | Lista de conversaciones (últimas 100) |
| GET | `/bot/conversaciones/{id}/mensajes` | Mensajes de la conversación |
| POST | `/bot/conversaciones/{id}/responder` | Body: `{texto}` — agente humano envía mensaje |
| POST | `/bot/conversaciones/{id}/cerrar` | Marca conversación como cerrada |

Los webhooks son públicos (Meta no autentica). La seguridad es por `verify_token` (en GET) y validación del payload.

---

## 📊 `/dashboard` — Métricas y vistas

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/dashboard/resumen` | KPIs del tenant |
| 🌐 GET | `/dashboard/`, `/dashboard/campanas`, `/dashboard/bot`, `/dashboard/pedidos`, `/dashboard/clientes`, `/dashboard/configuracion`, `/dashboard/plan`, `/dashboard/manual` | Vistas HTML (auth por JWT en localStorage) |

---

## 💳 `/billing` — Pagos

| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/billing/checkout/{plan_id}` | Crea sesión de checkout Stripe/MercadoPago, retorna `{checkout_url}` |
| 🌐 POST | `/billing/webhooks/{provider}` | Webhook de pasarela — verifica firma y activa plan |

Si `PAYMENT_PROVIDER` está vacío, checkout devuelve 503 y la UI hace fallback a `/tenant/upgrade-plan` (activación manual).

---

## 🛡️ `/admin` — Super-admin only

Requiere `tenant.es_superadmin == True`. Si no, devuelve 403.

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/admin/tenants` | Lista todos los tenants con métricas |
| POST | `/admin/tenants/{id}/suspender` | Marca `suspended` + `activo=false` |
| POST | `/admin/tenants/{id}/activar` | Marca `active` + `activo=true` |
| POST | `/admin/tenants/{id}/asignar-plan` | Body: `{plan_id}` |
| DELETE | `/admin/tenants/{id}` | Elimina tenant (cascade) |
| GET | `/admin/planes` | CRUD de planes |
| POST/PATCH/DELETE | `/admin/planes[/{id}]` | |
| GET | `/admin/metricas` | Métricas globales de la plataforma |
| 🌐 GET | `/admin/`, `/admin/planes-vista` | HTML |

---

## ⚙️ Sistema

| Método | Path | Descripción |
|--------|------|-------------|
| 🌐 GET | `/health` | `{"status":"ok","servicio":"Venbot"}` |
| 🌐 GET | `/` | Redirect a `/dashboard/` |
| 🌐 GET | `/api/docs` | Swagger UI |
| 🌐 GET | `/api/redoc` | ReDoc |

---

## Convenciones de errores

| HTTP | Cuándo | Body |
|------|--------|------|
| 400 | Body inválido o regla de negocio | `{"detail": "mensaje"}` |
| 401 | Token ausente o inválido | `{"detail": "No se pudo validar las credenciales"}` |
| 402 | Excediste límite del plan | `{"detail": "Alcanzaste el límite de N..."}` |
| 403 | Sin permisos (no eres superadmin) | `{"detail": "Acceso denegado"}` |
| 404 | Recurso no existe o no es del tenant | `{"detail": "X no encontrado"}` |
| 422 | Pydantic validation error | `{"detail": [{"loc": ..., "msg": ...}]}` |
| 502 | Falló API externa (Meta, Gemini, etc.) | `{"detail": "..."}` |
| 503 | Feature deshabilitada (pagos sin provider) | `{"detail": "..."}` |
