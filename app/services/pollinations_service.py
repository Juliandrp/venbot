"""
Generación de imágenes gratis con Pollinations.ai (modelo Flux).
Sin API key, sin límite de peticiones, sin costo.
https://pollinations.ai
"""
import os
import uuid
import urllib.parse
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
MEDIA_ROOT = "/app/media"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15))
async def _descargar_imagen(prompt: str, ancho: int = 1024, alto: int = 1024) -> bytes:
    encoded = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_URL.format(prompt=encoded)}?width={ancho}&height={alto}&nologo=true&model=flux&enhance=true"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


async def generar_imagenes_producto(
    nombre: str,
    descripcion: str,
    tenant_id: str,
    product_id: str,
    cantidad: int = 3,
) -> list[str]:
    """
    Genera imágenes publicitarias completamente gratis con Pollinations (Flux).
    Guarda en disco y retorna URLs relativas /media/...
    """
    estilos = [
        (
            f"professional product photography of {nombre}, {descripcion}, "
            "white background, studio lighting, e-commerce style, no text, photorealistic 4K",
            "1:1", 1024, 1024,
        ),
        (
            f"lifestyle photo of {nombre} in use, {descripcion}, "
            "modern Latin American home setting, natural daylight, no text, photorealistic",
            "4:5", 1024, 1280,
        ),
        (
            f"advertising banner for {nombre}, {descripcion}, "
            "vibrant colors, product as hero shot, clean background, no text, commercial photography",
            "16:9", 1280, 720,
        ),
    ]

    directorio = os.path.join(MEDIA_ROOT, "productos", tenant_id, product_id, "pollinations")
    os.makedirs(directorio, exist_ok=True)

    urls: list[str] = []
    for i, (prompt, _, ancho, alto) in enumerate(estilos[:cantidad]):
        try:
            datos = await _descargar_imagen(prompt, ancho, alto)
            nombre_archivo = f"flux_{i}_{uuid.uuid4().hex[:8]}.jpg"
            ruta = os.path.join(directorio, nombre_archivo)
            with open(ruta, "wb") as f:
                f.write(datos)
            urls.append(f"/media/productos/{tenant_id}/{product_id}/pollinations/{nombre_archivo}")
        except Exception:
            continue

    return urls
