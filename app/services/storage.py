"""
Servicio de almacenamiento abstracto.

Soporta dos backends:
  - local: disco del contenedor (en producción, montado como volumen persistente)
  - s3:    bucket S3-compatible (AWS S3, Cloudflare R2, MinIO, etc.)

Selección por settings.storage_backend.

Uso:
    from app.services.storage import storage
    url = await storage.guardar_bytes("productos/abc/imagen.jpg", datos_bytes, "image/jpeg")
    # url es relativa (/media/...) o absoluta (https://...) según el backend
"""
import os
from abc import ABC, abstractmethod
from app.config import settings


class StorageBackend(ABC):
    @abstractmethod
    async def guardar_bytes(self, key: str, datos: bytes, content_type: str = "application/octet-stream") -> str:
        """Guarda los bytes en `key` y retorna la URL pública."""
        ...

    @abstractmethod
    async def eliminar(self, key: str) -> bool:
        """Elimina el archivo. Retorna True si existía."""
        ...

    @abstractmethod
    def url_publica(self, key: str) -> str:
        """Retorna la URL pública de un key sin tocar el almacén."""
        ...


class LocalStorage(StorageBackend):
    def __init__(self, base_path: str, base_url: str):
        self.base_path = base_path.rstrip("/")
        self.base_url = base_url.rstrip("/")
        os.makedirs(self.base_path, exist_ok=True)

    def _ruta(self, key: str) -> str:
        key_safe = key.lstrip("/")
        return os.path.join(self.base_path, key_safe)

    async def guardar_bytes(self, key: str, datos: bytes, content_type: str = "application/octet-stream") -> str:
        ruta = self._ruta(key)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as f:
            f.write(datos)
        return self.url_publica(key)

    async def eliminar(self, key: str) -> bool:
        ruta = self._ruta(key)
        if os.path.exists(ruta):
            os.remove(ruta)
            return True
        return False

    def url_publica(self, key: str) -> str:
        return f"{self.base_url}/{key.lstrip('/')}"


class S3Storage(StorageBackend):
    def __init__(self):
        # Import lazy: solo se requiere boto3 si realmente se usa S3
        import boto3
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        self.public_base = (settings.s3_public_base_url or "").rstrip("/")

        kwargs = {
            "aws_access_key_id": settings.s3_access_key,
            "aws_secret_access_key": settings.s3_secret_key,
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4"),
        }
        if settings.s3_endpoint_url:
            kwargs["endpoint_url"] = settings.s3_endpoint_url
        self.client = boto3.client("s3", **kwargs)

    async def guardar_bytes(self, key: str, datos: bytes, content_type: str = "application/octet-stream") -> str:
        # boto3 es síncrono — lo corremos en el threadpool del event loop
        import asyncio
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key.lstrip("/"),
            Body=datos,
            ContentType=content_type,
            ACL="public-read",
        )
        return self.url_publica(key)

    async def eliminar(self, key: str) -> bool:
        import asyncio
        try:
            await asyncio.to_thread(
                self.client.delete_object, Bucket=self.bucket, Key=key.lstrip("/")
            )
            return True
        except Exception:
            return False

    def url_publica(self, key: str) -> str:
        k = key.lstrip("/")
        if self.public_base:
            return f"{self.public_base}/{k}"
        # Fallback: URL estándar S3
        if settings.s3_endpoint_url:
            return f"{settings.s3_endpoint_url.rstrip('/')}/{self.bucket}/{k}"
        return f"https://{self.bucket}.s3.{settings.s3_region}.amazonaws.com/{k}"


async def leer_url_como_bytes(url: str) -> bytes | None:
    """
    Lee una URL y retorna sus bytes, eligiendo el método óptimo:
      - URL relativa que empieza por base_url local → lee del disco
      - URL absoluta http(s) → descarga via HTTP

    Devuelve None si no se puede leer.
    """
    if not url:
        return None
    base_local = settings.storage_local_base_url.rstrip("/")

    # Caso 1: URL relativa local (/media/...)
    if url.startswith(base_local + "/") or url.startswith("/"):
        rel = url[len(base_local):] if url.startswith(base_local + "/") else url
        ruta = os.path.join(settings.storage_local_path, rel.lstrip("/"))
        if os.path.exists(ruta):
            with open(ruta, "rb") as f:
                return f.read()
        return None

    # Caso 2: URL absoluta — descarga HTTP
    if url.startswith("http://") or url.startswith("https://"):
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None
    return None


def _crear_storage() -> StorageBackend:
    if settings.storage_backend == "s3":
        if not all([settings.s3_bucket, settings.s3_access_key, settings.s3_secret_key]):
            raise RuntimeError(
                "STORAGE_BACKEND=s3 pero faltan S3_BUCKET / S3_ACCESS_KEY / S3_SECRET_KEY en .env"
            )
        return S3Storage()
    return LocalStorage(settings.storage_local_path, settings.storage_local_base_url)


storage: StorageBackend = _crear_storage()
