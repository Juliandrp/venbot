# 08 — Multi-tenant y seguridad

## Modelo de aislamiento

Venbot es **single-database, multi-tenant by row-level isolation**. No hay schemas separados por cliente, no hay BD por cliente. Todas las tablas (excepto `subscription_plans`) tienen una columna `tenant_id` (FK a `tenants.id`).

### Regla de oro

**Toda query SQL debe filtrar por `tenant_id` del usuario autenticado.**

```python
# ✅ CORRECTO
result = await db.execute(
    select(Product).where(
        Product.id == product_id,
        Product.tenant_id == tenant.id,  # ← obligatorio
    )
)

# ❌ MAL — fuga de datos entre tenants
result = await db.execute(
    select(Product).where(Product.id == product_id)
)
```

El `tenant` viene de `Depends(get_current_tenant)`. Si lo olvidas, cualquier usuario podría leer/modificar datos de otros con un UUID adivinado.

### Tests de isolation

`tests/test_products.py` tiene `test_listar_solo_productos_del_tenant_actual` y `test_no_se_puede_acceder_producto_de_otro_tenant`. **Cualquier endpoint nuevo debe tener su test análogo**.

## Auth: JWT

Stack:
- `python-jose[cryptography]` para firma/verificación
- `passlib[bcrypt]` para hash de passwords
- Storage del token en `localStorage` del browser (no cookie)

### Flujo

```
POST /auth/login {email, password}
  ↓
Verificar bcrypt match
  ↓
Generar:
  - access_token (60 min, type=access)
  - refresh_token (30 días, type=refresh)
  ↓
Browser guarda en localStorage
  ↓
Cada request: Authorization: Bearer <access_token>
  ↓
get_current_tenant() decodifica el JWT, busca tenant en BD
  ↓
Si tenant.activo == False → 401
```

### Refresh automático

`venbot.js` define `apiFetch()`:
- Si la response es 401 → llama `/auth/refresh` con el refresh_token
- Reintenta la request original con el nuevo access_token
- Si refresh también falla → redirect a login

Esto significa que **el usuario nunca ve un "sesión expirada"** mientras tenga refresh válido.

### Por qué localStorage y no cookie httpOnly

Tradeoff consciente:
- **Pro**: simpler. JS puede leer el token. Sirve para apps con frontend separado.
- **Contra**: vulnerable a XSS. Si alguien inyecta JS malicioso, puede robar el token.

Mitigación: la app no acepta input HTML del usuario en ningún lado (todo es text/json + escapado por Jinja). No hay ventanas de XSS conocidas.

Para producción más segura: migrar a httpOnly cookie con SameSite=Strict + endpoint CSRF.

## Cifrado de secretos de tenants

Los API keys de cada tenant (Anthropic, OpenAI, Shopify, etc.) se guardan **cifrados con Fernet**:

```python
from app.core.security import encrypt_secret, decrypt_secret

# guardar
config.anthropic_api_key_enc = encrypt_secret("sk-ant-...")

# leer
api_key = decrypt_secret(config.anthropic_api_key_enc)
```

Fernet usa AES-128-CBC + HMAC-SHA256. La llave es `ENCRYPTION_KEY` del `.env`.

### IMPORTANTE: si pierdes ENCRYPTION_KEY

**Todos los API keys de todos los tenants se vuelven irrecuperables.** No hay forma de descifrarlos.

Por eso:
1. **Backup de `ENCRYPTION_KEY`** en un secret manager (1Password, Bitwarden, AWS Secrets Manager)
2. Nunca regenerar `ENCRYPTION_KEY` sin un script de migración que descifre con la vieja y cifre con la nueva

## Roles

Solo dos roles:

| Rol | Cómo se identifica | Privilegios |
|-----|---------------------|-------------|
| **Tenant** | `tenant.es_superadmin == False` | Solo ve sus propios datos. Sin acceso a `/admin/*` |
| **Super-admin** | `tenant.es_superadmin == True` | Ve todo. Bypass de plan limits. Acceso a `/admin/*` |

No hay roles intermedios (admin de tenant, viewer, etc.) — fuera de scope inicial.

### Cómo crear un super-admin

Por defecto se crea uno al arrancar desde `.env`:
```env
SUPERADMIN_EMAIL=admin@venbot.io
SUPERADMIN_PASSWORD=Cali24680.
```

`_seed_superadmin()` en `main.py` lo crea si no existe, o actualiza la password si cambió.

Para crear más super-admins:
```sql
UPDATE tenants SET es_superadmin = true WHERE email = 'otro@admin.com';
```

## Validación de límites de plan

`app/services/plan_limits.py` contiene 3 verificaciones reusables:

```python
verificar_puede_crear_producto(tenant, db)
verificar_puede_crear_campana(tenant, db)
verificar_puede_enviar_mensaje_bot(tenant, db)
```

Cada una:
1. Bypass si `tenant.es_superadmin`
2. Si `estado_suscripcion == suspended` o `activo == False` → 402 (Payment Required)
3. Cuenta uso actual vs límite del plan
4. Si excede → 402

Llamarlas **antes** de crear el recurso, no después.

## Headers de seguridad

Actualmente la app **no setea** estos headers (son opcionales y mejorables):
- `Content-Security-Policy`
- `X-Frame-Options`
- `Strict-Transport-Security`

Traefik (Coolify) sí mete `X-Content-Type-Options: nosniff` por default.

Si quieres apretar la seguridad, agregar middleware en `main.py`:

```python
@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp
```

## Webhooks públicos

Los webhooks de WhatsApp/Messenger/Stripe/MercadoPago son **públicos** (sin auth Bearer) porque las plataformas externas no envían JWTs.

Cada uno valida de otra forma:
- **WhatsApp/Messenger**: `verify_token` definido por el tenant en su Configuración
- **Stripe**: firma `Stripe-Signature` validada con `stripe.Webhook.construct_event()`
- **MercadoPago**: HMAC-SHA256 en `x-signature`

Si alguien adivina la URL del webhook pero no tiene la firma, no pasa nada útil.

## Rate limiting

**No implementado todavía.** Riesgo: un atacante podría:
- Spam de `/auth/register` para crear cuentas masivas
- Spam de `/bot/whatsapp/webhook/*` para saturar el worker
- Brute force de `/auth/login`

Mitigaciones recomendadas (no incluidas):
1. **Cloudflare** delante del dominio (rate limit + bot protection gratis)
2. **slowapi** middleware en FastAPI con límite por IP
3. **Captcha** en `/auth/register`

Son fáciles de agregar cuando salgas a vender.

## Auditoría

**No hay log de auditoría.** Cada acción del super-admin (suspender tenant, eliminar tenant) ocurre sin trazo.

Para producción seria, agregar tabla `audit_log` y middleware que registre POST/PATCH/DELETE con `tenant_id` y `actor_id`.

## Backups

**Responsabilidad del operador del VPS**. Coolify NO hace backups automáticos del volumen `venbot_postgres`.

Recomendación mínima:
```bash
# Cron diario en el server
0 3 * * * docker exec venbot-postgres pg_dump -U venbot venbot_db | gzip > /backups/venbot_$(date +\%Y\%m\%d).sql.gz
```

Para producción seria: snapshots gestionados (DigitalOcean Backups, Hetzner Cloud Snapshots) + replicación a otro región.
