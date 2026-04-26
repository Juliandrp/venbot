# 06 — Pipeline IA

## Objetivo

Convertir un producto + sus fotos en contenido completo de marketing: copy SEO, descripciones, bullet points, copies de anuncios segmentados, imágenes y video. Listo para publicar en Shopify y lanzar campañas.

## Flujo

```
Crear producto
     │
     ▼
Subir imágenes (POST /productos/{id}/imagenes)
     │
     ▼
content_pipeline.delay(product_id, tenant_id)
     │
     ▼
┌────────────────────────────────────────────────┐
│ Paso 1: Texto                                  │
│   Provider: Gemini (default) | Claude | OpenAI │
│   Output: titulo_seo, descripcion_seo,         │
│           bullet_points, variantes_copy,        │
│           video_script                          │
└────────────────────────────────────────────────┘
     │ pipeline_paso = 1
     ▼
┌────────────────────────────────────────────────┐
│ Paso 2: Imágenes                               │
│   Provider:                                    │
│     - Gemini key → Imagen 3 (4K, paga)         │
│     - OpenAI key → DALL-E 3                    │
│     - Sin key → Pollinations Flux (gratis)     │
│   Output: 3 imágenes (white bg + lifestyle + ad) │
└────────────────────────────────────────────────┘
     │ pipeline_paso = 2
     ▼
┌────────────────────────────────────────────────┐
│ Paso 3: Video (si hay key)                     │
│   Provider: Kling | Higgsfield | HeyGen        │
│   Async: dispara verificar_video_X cada 60s   │
│   Output: video MP4 + URL pública              │
└────────────────────────────────────────────────┘
     │ pipeline_paso = 3
     ▼
┌────────────────────────────────────────────────┐
│ Paso 4: Publicar en Shopify (si configurado)   │
│   Crea producto con imágenes + descripción HTML│
└────────────────────────────────────────────────┘
     │ pipeline_paso = 4
     ▼
contenido_generado = true
```

## Estrategia de proveedores (priority + fallback)

### Texto

```python
# pseudo
if ai_provider == "claude" and tiene_anthropic_key:
    intentar(claude)
elif ai_provider == "openai" and tiene_openai_key:
    intentar(openai)

# fallback universal
if datos is None:
    intentar(gemini)  # con key del tenant o platform
```

Gemini es el fallback porque (1) es gratis hasta cierto uso, (2) la plataforma puede tener una `GEMINI_API_KEY` global que sirve a todos.

### Imágenes

```python
if ai_provider == "gemini" and tiene_gemini_key:
    intentar(imagen_3)  # mejor calidad, usa misma key
else:
    intentar(dalle)     # si tiene openai_key

# fallback universal: gratis
if not urls_imagenes:
    intentar(pollinations)
```

### Video

**No hay fallback** — si no hay key, no hay video. La razón: no existe un proveedor de video gratis lo suficientemente bueno.

## Detalles por proveedor

### Gemini (`gemini_service.py`)

- SDK: `google-genai` (NO `google-generativeai`, está deprecated)
- Modelos válidos en 2026:
  - `gemini-2.5-pro` — mejor calidad
  - `gemini-2.5-flash` — **default**, balance
  - `gemini-2.5-flash-lite` — más rápido/barato
  - `gemini-1.5-pro` — legacy
- **Modelo `gemini-2.0-flash` devuelve 404** desde 2026-Q1 (renombrado por Google)
- Soporta vision: pasa imágenes como `types.Part.from_bytes()`
- Usa `client.aio.models.generate_content()` (async)
- Lee la imagen vía `leer_url_como_bytes()` del storage abstracto

### Claude (`ai_content.py`)

- SDK: `anthropic` (oficial)
- Modelos: `claude-opus-4-7`, `claude-sonnet-4-6` (default), `claude-haiku-4-5`
- Vision: imágenes en base64 con `media_type`
- **Cliente síncrono** (`anthropic.Anthropic`) corriendo en async — funciona porque httpx por dentro es no-bloqueante a nivel de red, pero `client.messages.create()` se ve sync en el código
- Reintentos: 3 con tenacity exponential backoff

### OpenAI (`openai_content_service.py`)

- SDK: `openai` (oficial), usa `AsyncOpenAI`
- Modelos: `gpt-4o`, `gpt-4o-mini` (default), `gpt-5`
- Vision: data URL en base64
- Devuelve JSON estructurado (validado en código, no usa response_format por compatibilidad)

### Pollinations (`pollinations_service.py`)

- **No requiere API key**. URL pública: `image.pollinations.ai/prompt/{prompt}?...`
- Modelo Flux subyacente
- 3 estilos hardcodeados: white background, lifestyle, advertising banner
- Tamaños 1024×1024, 1024×1280, 1280×720
- Guarda con storage abstracto

### Imagen 3 (`imagen_service.py`)

- Mismo SDK que Gemini (`google-genai`), distinto endpoint
- Modelo: `imagen-3.0-generate-002`
- Aspect ratio fijo `1:1`
- `safety_filter_level=block_only_high`, `person_generation=dont_allow` (compliant para e-commerce)

### DALL-E (`dalle_service.py`)

- SDK OpenAI con `client.images.generate()`
- Modelo: `dall-e-3`
- Costo: ~$0.04/imagen (HD)

### Kling (`kling_service.py`)

- API REST custom (no SDK oficial)
- 2 endpoints: text-to-video, image-to-video
- Devuelve `task_id` → polling con `obtener_estado(task_id)` cada 60s
- **Image-to-video** es lo que mejor funciona para e-commerce: usas la primera foto del producto como anchor
- Modelos: `kling-v1`, `kling-v1-5`, `kling-v1-6` (default), `kling-v2`
- Duración: 5 o 10 segundos
- Aspect ratio: 9:16 (mobile/Reels)

### Higgsfield (`higgsfield_service.py`)

- API estimada según docs públicas (puede requerir ajuste cuando uses la real)
- Especialidad: movimiento de cámara cinemático
- Mismo patrón de polling que Kling

### HeyGen (`heygen.py`)

- Para videos con avatar humano hablando
- Más caro y limitado para productos físicos
- Útil para marcas personales / coaching

## Vision: cómo se pasan las imágenes

Antes la app solo soportaba imágenes locales. Después de migrar a storage abstracto:

```python
# storage.py
async def leer_url_como_bytes(url: str) -> bytes | None:
    if url.startswith("/media/"):
        # local: lee del disco
        ...
    elif url.startswith("http"):
        # S3 o cualquier URL pública: descarga con httpx
        ...
```

Cada servicio IA llama a este helper:

```python
datos = await leer_url_como_bytes(image_url)
mime = mimetypes.guess_type(image_url)[0]
# pasarlo al SDK (base64 / Part.from_bytes / etc.)
```

Beneficio: **agnóstico al storage** — funciona igual con local o S3.

## Schema esperado del JSON de IA

Las 3 services (Claude/Gemini/OpenAI) devuelven el mismo dict:

```json
{
  "titulo_seo": "string máx 70 chars",
  "descripcion_seo": "string 150-200 palabras",
  "bullet_points": ["beneficio 1", "...", "beneficio 5"],
  "variantes_copy": {
    "18-24": {"M": "...", "F": "...", "todos": "..."},
    "25-34": {"M": "...", "F": "...", "todos": "..."},
    "35-44": {"M": "...", "F": "...", "todos": "..."},
    "45+":   {"M": "...", "F": "...", "todos": "..."}
  },
  "video_script": "guion 30-60 seg para Kling/HeyGen"
}
```

Si el JSON no parsea, el pipeline falla y se reintenta hasta 3 veces.

## Observabilidad del pipeline

- `pipeline_paso` (0-4) en `product_contents` → frontend lo muestra como barra de progreso
- `contenido_generado` (bool) en `product` → marca completado para evitar re-disparos
- `video_estado` ("procesando" / "completed" / "failed") → status del polling de video

## Costos estimados por producto

Asumiendo Gemini 2.5 Flash + Pollinations + sin video:
- **$0** (gratis)

Asumiendo Claude Sonnet 4.6 + Imagen 3 + Kling:
- Claude texto: ~$0.005
- Imagen 3 × 3: ~$0.06
- Kling video 5s: ~$0.50
- **Total: ~$0.57/producto**
