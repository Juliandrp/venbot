# 12 — Decisiones de diseño

Por qué se hizo así y no de otra forma. Útil cuando alguien (futuro tú o un dev nuevo) pregunte "¿no era mejor X?".

## Single-database multi-tenant (no schema-per-tenant ni DB-per-tenant)

**Decisión**: una sola BD, todas las tablas con `tenant_id`.

**Por qué**:
- Más simple de operar (un backup, un upgrade, un set de índices)
- Más eficiente en recursos para tenants pequeños
- Fácil agregar features (no hay sync entre schemas)

**Tradeoff**:
- Riesgo de fuga si olvidas filtrar por `tenant_id` (mitigado con tests)
- Difícil dar a un tenant grande dedicación de recursos
- Imposible cumplir requisitos de "datos solo en X país" por tenant

**Cuándo cambiar**: si un tenant >50% de la carga, separarlo a su propia BD.

---

## Server-side rendering (Jinja + Alpine), no SPA

**Decisión**: cero React/Vue/Svelte. Templates Jinja con Alpine.js para reactividad puntual.

**Por qué**:
- Cero build step, cero deploy frontend separado
- Cambios visibles al recargar (no esperar webpack)
- Un solo "deployable" (la app)
- Menor superficie de ataque (no JS bundles que sirvan)

**Tradeoff**:
- UX menos fluida que un SPA
- Difícil compartir lógica con apps móviles
- Alpine es OK pero limitado para forms muy complejos

**Cuándo cambiar**: si vas a tener app móvil (Flutter/React Native), tener API limpia + frontend separado.

---

## Un solo container con uvicorn + worker + beat

**Decisión**: `start.sh` lanza los 3 procesos dentro del mismo container.

**Por qué**:
- Coolify es más simple con apps de 1 container (Application type)
- Menor consumo de RAM (un Python interpreter compartido)
- Replicar patrón de mentisapp (ya validado en el VPS)

**Tradeoff**:
- Si worker crashea, todo el container se reinicia (no aislamiento)
- No puedes escalar uvicorn independiente del worker
- Más difícil debuggear (logs mezclados)

**Cuándo cambiar**: cuando >1000 productos/día o >10K mensajes bot/día. Separar worker en su propia app Coolify apuntando al mismo repo.

---

## Celery síncrono que llama `asyncio.run()`

**Decisión**: cada Celery task es función sync que adentro llama `asyncio.run(_async_impl(...))`.

**Por qué**:
- Celery 5.x todavía no tiene async-native bien
- Permite usar SQLAlchemy async dentro de tasks
- Patrón conocido en la comunidad

**Tradeoff**:
- Cada task crea event loop nuevo (más lento)
- Forzó la creación de `make_celery_session()` con NullPool
- Confunde a devs que esperan tasks async

**Cuándo cambiar**: cuando salga una versión estable de Celery con async tasks (5.5+ o 6.0).

---

## Storage abstracto desde el día 1

**Decisión**: `app/services/storage.py` con interfaz `StorageBackend` y dos implementaciones (local + s3).

**Por qué**:
- Migrar local → S3 es solo cambiar var de entorno
- Permite testear con local en dev y prod en S3
- No quedarse atado a un proveedor

**Tradeoff**:
- Más código que solo usar Local
- Las URLs que se guardan en BD dependen del backend (si migras, hay que migrar URLs)

**Cuándo cambiar**: nunca, esto fue acertado.

---

## API keys de tenants cifradas con Fernet

**Decisión**: Fernet (AES-128-CBC + HMAC) con `ENCRYPTION_KEY` global.

**Por qué**:
- Suficiente para uso normal (no es PCI-DSS)
- Nativo de Python, sin servicios externos
- Reversible (necesario para usar las keys)

**Tradeoff**:
- Si pierdes `ENCRYPTION_KEY` → todos los tenants quedan sin sus keys (irrecuperable)
- No hay rotación automática
- Una sola llave para todos los tenants (no per-tenant)

**Cuándo cambiar**: si tu app maneja datos PCI o necesitas SOC2 → mover a AWS KMS / HashiCorp Vault per-tenant.

---

## JWT en localStorage (no cookie httpOnly)

**Decisión**: token guardado en `localStorage` del browser.

**Por qué**:
- Setup más simple
- API compatible con apps no-web (móvil, CLI)
- Permite refresh transparente del lado JS

**Tradeoff**:
- Vulnerable a XSS (si alguien inyecta JS, roba tokens)
- No CSRF-protected automáticamente

**Cuándo cambiar**: si el app maneja datos muy sensibles (banca, salud), migrar a httpOnly + CSRF token.

---

## Validators Pydantic que aceptan string vacío

**Decisión**: `field_validator(mode="before")` que convierte `""` → `None`.

**Por qué**:
- Forms HTML envían `""` cuando un input number está vacío
- Pydantic no parsea `""` como `Optional[int]` por defecto
- Sin esto, todo el flujo "guardar formulario opcional" rompía

**Tradeoff**:
- Un poco de boilerplate por schema
- Inconsistente con el resto del schema (acepta dos representaciones del mismo "vacío")

**Cuándo cambiar**: nunca, esto debe quedarse en cualquier modelo nuevo con campos numéricos opcionales.

---

## Coolify (vs Kubernetes / Heroku / Render)

**Decisión**: Coolify self-hosted en VPS Hostinger.

**Por qué**:
- Self-hosted = costos predecibles
- Soporta múltiples apps en el mismo server (Mentis, Venbot, etc. ya conviven)
- UI manejable + integración GitHub
- No vendor lock-in

**Tradeoff**:
- Coolify es beta — encontramos bugs (los labels Traefik no se respetan)
- Necesitas administrar el server tú mismo (updates de Docker, OS, etc.)
- Sin SLA

**Cuándo cambiar**: si necesitas auto-scale o multi-region → Kubernetes (GKE/EKS) o Render/Railway.

---

## Idioma español en código y modelos

**Decisión**: identificadores de modelos en español (`Cliente`, `Pedido`), comentarios en español, UI en español.

**Por qué**:
- App va dirigida a LATAM
- Reduce fricción mental (el equipo piensa en español)
- Modelos quedan más cerca del lenguaje del negocio

**Tradeoff**:
- Difícil internacionalizar a otros idiomas más adelante
- Devs que llegan acostumbrados a inglés tienen fricción
- No "estándar" en open-source

**Cuándo cambiar**: si vendes a EE.UU./Europa, traducir UI con i18n. El backend puede quedar en español sin problema.

---

## Sin tests E2E, solo unit + integration

**Decisión**: pytest con SQLite in-memory + fixtures. No hay Cypress/Playwright.

**Por qué**:
- Tests E2E son lentos (5-10x más que unit)
- Setup complejo con CDN-based frontend
- 80% de bugs los atrapan tests de API

**Tradeoff**:
- Bugs en JS/Alpine no se detectan automáticamente
- Refactor de UI puede romper sin que sepas

**Cuándo cambiar**: si la app crece y los bugs UI son frecuentes → agregar Playwright para los flows críticos (login, crear producto, lanzar campaña).

---

## Pagos con fallback manual

**Decisión**: `POST /billing/checkout` devuelve 503 si no hay provider; UI hace fallback a `/tenant/upgrade-plan` (activación sin pago).

**Por qué**:
- Permite usar la app sin Stripe/MercadoPago configurado
- En etapa beta, el operador activa planes manual
- Cero código duplicado para "modo manual"

**Tradeoff**:
- En producción puede dar pie a abusos si nunca configuras pagos
- UI muestra mensaje confuso si la primera vez funciona pero después falla

**Cuándo cambiar**: cuando vendas en producción a clientes reales, configurar provider obligatorio y eliminar el fallback.

---

## Imágenes con Pollinations gratis por default

**Decisión**: si no hay key de Imagen 3 / DALL-E, generar con Pollinations Flux (público, sin auth).

**Por qué**:
- Permite probar la app entera sin pagar nada
- Calidad aceptable para muchos productos
- Ideal para validación rápida

**Tradeoff**:
- Pollinations puede bajarse (uptime no garantizado)
- Sin SLA / no es comercial-grade
- Calidad variable

**Cuándo cambiar**: cuando tengas tracción real, recomendar a clientes Imagen 3 (mejor relación calidad/precio).

---

## Modelo IA por proveedor configurable (no hardcoded)

**Decisión**: `claude_model`, `gemini_model`, `openai_model` en `tenant_configs` con dropdown en UI.

**Por qué**:
- Los proveedores cambian nombres de modelos (`gemini-2.0-flash` → 404 en 2026)
- Diferentes tenants pueden querer balance distinto calidad/costo
- Permite probar modelos nuevos sin redeploy

**Tradeoff**:
- Más columnas en BD
- Lista de modelos hardcoded en UI (hay que mantenerla)

**Cuándo cambiar**: si los proveedores estabilizan sus nombres → eliminar columna y volver a hardcoded.
