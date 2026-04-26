# 05 — Workers y tareas

## Visión general

Celery procesa todo lo que toma >1 segundo o requiere reintento:
- Generación IA (puede tardar 30s-5min)
- Envíos a APIs externas (Meta, Shopify, WhatsApp)
- Tareas programadas (monitoreo de campañas, tracking de envíos)
- Notificaciones (email, WhatsApp)

## Arquitectura Celery

```
FastAPI (productor)        Celery worker (consumidor)
       │                          │
       │   .delay(args)            │
       │ ────────────────▶  Redis  │  poll
       │                  (cola)   │ ────▶
       │                          │
       │                          ▼
       │                    Ejecuta task
       │                          │
       │                          ▼
       │                  Actualiza BD
```

### Configuración (`app/celery_app.py`)

- **Broker**: Redis DB 1
- **Result backend**: Redis DB 2
- **Timezone**: America/Bogota
- **Serializer**: JSON
- **Acks late**: True (reintenta si crashea)
- **Prefetch**: 1 (no agarra más tareas que pueda procesar)

### Colas

3 colas separadas para priorizar:

| Cola | Tareas | Concurrencia |
|------|--------|--------------|
| `default` | campaign_monitor, shipping_tracker, bot_processor | 4 (default Celery) |
| `content` | content_pipeline (lento) | 2 |
| `notifications` | notificar_cliente_pedido | 4 |

Worker en producción consume todas: `-Q default,content,notifications`.

---

## Tareas

### `app.workers.content_pipeline.generar_contenido_producto`

Pipeline IA completo. Disparado al subir imágenes o desde "Regenerar contenido".

**Pasos:**
1. Genera texto (copy + SEO + guion) → escribe en `product_contents`
2. Genera imágenes (3 estilos) → guarda URLs en `imagenes_generadas`
3. Si hay video provider: dispara `verificar_video_kling` o `verificar_video_higgsfield` (otra task que hace polling)
4. Si hay Shopify: publica producto

**Reintentos**: 3, delay 60s.

**Por qué tiene retry**: Gemini gratis tiene rate limit y a veces tira 429.

### `app.workers.content_pipeline.verificar_video_kling` / `verificar_video_higgsfield`

Polling del estado del video cada 60 segundos hasta que esté listo o falle. Max 20 reintentos (~20 min total).

Se auto-reencola con `task.retry()` mientras Kling/Higgsfield reporten "procesando".

### `app.workers.bot_processor.procesar_mensaje_whatsapp`

Disparado por el webhook de WhatsApp.

1. Crea/encuentra `Customer` por whatsapp_id
2. Crea/encuentra `Conversation` activa
3. Guarda mensaje del cliente
4. **Si el estado es transferida** → no responde (esperando humano)
5. **Si es activa** → genera respuesta con IA (Claude/Gemini según `ai_provider`)
6. Si confianza < 0.5 → marca conversación como `transferida`
7. Envía respuesta vía WhatsApp API

Max retries: 3.

### `app.workers.bot_processor.procesar_mensaje_messenger`

Idem pero para Messenger (no implementado el envío de respuesta todavía).

### `app.workers.notifications.notificar_cliente_pedido`

Envía notificación al cliente cuando cambia estado del pedido. Eventos: `creado`, `confirmado`, `enviado`, `en_camino`, `entregado`, `fallido`, `cancelado`.

Cada evento tiene su plantilla en `MENSAJES`. Envía simultáneamente:
- WhatsApp (si cliente tiene `whatsapp_id` y tenant tiene WABA configurado)
- Email (si cliente tiene email y tenant tiene SMTP)

Si una falla, la otra igual sale.

### `app.workers.campaign_monitor.check_all_campaigns` (programada)

**Programación**: cada 30 minutos vía Celery beat.

1. Lista todas las campañas con `estado=activa` y `meta_campaign_id != null`
2. Para cada una: consulta métricas de Meta (impressions, clicks, spend, ROAS)
3. Guarda snapshot en `ad_performance_snapshots`
4. Si ROAS < `roas_minimo`: pausa los AdSets que más están perdiendo

### `app.workers.shipping_tracker.track_all_shipments` (programada)

**Programación**: cada 2 horas vía Celery beat.

1. Lista pedidos con `dropi_order_id` y estado no-final
2. Consulta Dropi por estado actual
3. Si cambió: actualiza `Order.estado`, crea `ShipmentEvent`, dispara `notificar_cliente_pedido`

---

## Celery beat — schedule

Definido en `app/celery_app.py`:

```python
beat_schedule = {
    "monitor-campaigns": {
        "task": "app.workers.campaign_monitor.check_all_campaigns",
        "schedule": crontab(minute="*/30"),
    },
    "track-shipments": {
        "task": "app.workers.shipping_tracker.track_all_shipments",
        "schedule": crontab(minute=0, hour="*/2"),
    },
}
```

El schedule file vive en `/app/celerybeat/celerybeat-schedule` (volumen persistente para que sobreviva reinicio).

---

## Async + Celery (gotcha importante)

Celery es síncrono. SQLAlchemy es async. Solución:

```python
@celery_app.task(name="...", bind=True)
def mi_task(self, arg):
    asyncio.run(_implementacion_async(arg))

async def _implementacion_async(arg):
    from app.database import make_celery_session
    AsyncSessionLocal = make_celery_session()  # ← engine con NullPool
    async with AsyncSessionLocal() as db:
        ...
```

**Por qué `make_celery_session()` y no el `AsyncSessionLocal` global**:
Si reusas el engine global, el connection pool de asyncpg cachea conexiones a nivel de event loop. Cada `asyncio.run()` crea un loop nuevo → asyncpg falla con "Future attached to a different loop".

Con `NullPool`, cada call abre y cierra conexión nueva, sin caché. Más lento pero seguro.

---

## Encolar una tarea desde código

```python
from app.workers.notifications import notificar_cliente_pedido

# Encolar
notificar_cliente_pedido.delay(order_id="abc-123", evento="confirmado")

# Encolar con delay
notificar_cliente_pedido.apply_async(
    args=["abc-123", "confirmado"],
    countdown=300,  # 5 min
)
```

`.delay()` retorna inmediatamente. La tarea corre cuando un worker la tome.

---

## Monitorear tareas

### En logs (default)

Worker imprime cada task que recibe y termina:

```
docker exec <container> tail -f /var/log/celery-worker.log
```

### Con Flower (opcional, no deployado)

`docker compose up flower` → `localhost:5555` → UI con todas las tareas, throughput, errores.

---

## Cómo agregar una tarea nueva

1. Crear archivo en `app/workers/<modulo>.py` con:
   ```python
   import asyncio
   from app.celery_app import celery_app

   @celery_app.task(name="app.workers.<modulo>.mi_task", bind=True, max_retries=3)
   def mi_task(self, ...):
       try:
           asyncio.run(_async_impl(...))
       except Exception as e:
           raise self.retry(exc=e)

   async def _async_impl(...):
       from app.database import make_celery_session
       AsyncSessionLocal = make_celery_session()
       ...
   ```

2. Agregarla a `include` en `app/celery_app.py`:
   ```python
   include=[..., "app.workers.<modulo>"]
   ```

3. Si va en cola distinta de `default`, agregar a `task_routes`:
   ```python
   task_routes={"app.workers.<modulo>.*": {"queue": "<cola>"}}
   ```

4. Si es periódica, agregar al `beat_schedule`.

5. Reiniciar el contenedor (deploy) para que el worker la cargue.

---

## Tareas que NO se reintentan

Si quieres que una task NO reintente (ej. envío de email — mejor perder un email que enviar duplicado), usa `max_retries=0`:

```python
@celery_app.task(max_retries=0)
def enviar_email(...):
    ...
```

O dentro del handler, captura excepciones y loggéalas sin re-raise.
