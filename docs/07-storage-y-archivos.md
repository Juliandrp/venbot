# 07 — Storage y archivos

## Visión

`app/services/storage.py` define una **interfaz abstracta** para guardar archivos (imágenes y videos generados). Dos backends listos:

- **`local`** — disco del contenedor, montado como volumen Docker persistente
- **`s3`** — bucket S3-compatible (AWS S3, Cloudflare R2, MinIO, DigitalOcean Spaces)

Configurable via `STORAGE_BACKEND` env var. Sin downtime para cambiar.

## Interfaz

```python
class StorageBackend(ABC):
    async def guardar_bytes(self, key: str, datos: bytes, content_type: str) -> str: ...
    async def eliminar(self, key: str) -> bool: ...
    def url_publica(self, key: str) -> str: ...
```

Y un helper de lectura agnóstico:

```python
async def leer_url_como_bytes(url: str) -> bytes | None:
    """
    URL local (/media/...) → lee del disco
    URL HTTP(S)            → descarga con httpx
    """
```

Esta función es la que usan los servicios IA para procesar imágenes existentes (vision input).

## Backend local

```python
class LocalStorage(StorageBackend):
    base_path = "/app/media"
    base_url = "/media"
```

- Guarda en `/app/media/<key>` dentro del container
- En docker-compose / Coolify, este path está montado como volumen `media_files` (persiste entre redeploys)
- URL pública: `https://tudominio.com/media/<key>` (sirve FastAPI con `app.mount("/media", StaticFiles(...))`)

## Backend S3

```python
class S3Storage(StorageBackend):
    bucket = settings.s3_bucket
    public_base = settings.s3_public_base_url
```

- Usa `boto3` (sync) corriendo en `asyncio.to_thread()` para no bloquear el loop
- Sube con `ACL=public-read` (los archivos son URLs públicas)
- URL pública: configurable via `S3_PUBLIC_BASE_URL` o auto-generada

### Variables S3

```env
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://abc123.r2.cloudflarestorage.com  # si usas R2/MinIO; vacío para AWS
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
S3_BUCKET=venbot-media
S3_REGION=us-east-1
S3_PUBLIC_BASE_URL=https://media.tudominio.com  # CDN o bucket público
```

## Migrar de local a S3

1. Crear bucket en AWS/R2/MinIO
2. Configurar las env vars S3
3. **Migrar archivos existentes** (script manual):
   ```bash
   aws s3 sync /app/media/ s3://venbot-media/
   ```
4. Cambiar `STORAGE_BACKEND=s3`
5. Reiniciar app

**Importante**: las URLs ya guardadas en BD (`product.imagenes_originales`, `product_contents.imagenes_generadas`) siguen siendo `/media/...`. Tienes 2 opciones:

- **Opción A** (sin migrar BD): mantener `STORAGE_LOCAL_BASE_URL=https://tudominio.com/media` apuntando a un nginx que sirve `/media/*` desde S3 con redirect 301
- **Opción B** (migrar BD): script SQL que reemplaza `/media/...` por `https://media.tudominio.com/...` en JSON columns

Opción A es más rápida; Opción B es más limpia a largo plazo.

## Estructura de keys

Por convención:

```
productos/
  └── <tenant_id>/
      └── <product_id>/
          ├── <uuid>.jpg              ← fotos originales subidas por usuario
          ├── pollinations/
          │   └── flux_<i>_<uuid>.jpg ← imágenes Pollinations
          └── ia/
              └── imagen3_<i>_<uuid>.png ← imágenes Imagen 3
```

Si agregas un proveedor nuevo, mete sus archivos en una subcarpeta propia para no chocar.

## Volumen Coolify (producción actual)

- Volumen Docker: `venbot_media`
- Mount path: `/app/media`
- Tamaño: depende del VPS (en Coolify se ve en Resources)
- **Backups**: NO automáticos. Si el VPS muere, pierdes las imágenes.

## Recomendación para producción seria

Migrar a **Cloudflare R2**:
- Sin egress fees (a diferencia de S3)
- $0.015/GB/mes almacenamiento
- API S3-compatible
- Public bucket con CDN gratis (Cloudflare en frente)

Configuración:
```env
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<account>.r2.cloudflarestorage.com
S3_ACCESS_KEY=<r2 token>
S3_SECRET_KEY=<r2 secret>
S3_BUCKET=venbot-media
S3_PUBLIC_BASE_URL=https://media.tudominio.com  # usar Cloudflare custom domain
```

## Cómo agregar un backend nuevo (ej. Google Cloud Storage)

1. Implementar `class GCSStorage(StorageBackend)` con los 3 métodos
2. Agregar a `_crear_storage()`:
   ```python
   if settings.storage_backend == "gcs":
       return GCSStorage()
   ```
3. Agregar settings necesarias en `app/config.py`
4. Documentar en `.env.example`

## Tests

`tests/test_storage.py` cubre:
- Guardar y leer de LocalStorage
- Eliminación
- `url_publica` correctamente formada
- `leer_url_como_bytes` con URL local

S3 no se testea automáticamente (requiere bucket real). Test manual antes de pasar a producción.
