"""Generación de imágenes con Google Imagen 3 (via Gemini API)."""
import base64
import os
import uuid
from app.config import settings

MEDIA_ROOT = "/app/media"


async def generar_imagenes_producto(
    nombre: str,
    descripcion: str,
    tenant_id: str,
    product_id: str,
    cantidad: int = 3,
    api_key: str | None = None,
) -> list[str]:
    """
    Genera imágenes publicitarias con Imagen 3.
    Guarda los archivos en disco y retorna URLs relativas /media/...
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key or settings.gemini_api_key)

    estilos = [
        "product photography on clean white background, professional studio lighting, e-commerce style",
        "lifestyle photography, product in use, modern Latin American setting, natural light",
        "advertising image, vibrant colors, product as hero, no text, high contrast",
    ]

    directorio = os.path.join(MEDIA_ROOT, "productos", tenant_id, product_id, "ia")
    os.makedirs(directorio, exist_ok=True)

    urls: list[str] = []
    for i in range(min(cantidad, len(estilos))):
        prompt = (
            f"High quality advertising photo for e-commerce. "
            f"Product: {nombre}. {descripcion}. "
            f"Style: {estilos[i]}. "
            f"No text, no watermark, photorealistic, 4K."
        )
        try:
            response = await client.aio.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    safety_filter_level="block_only_high",
                    person_generation="dont_allow",
                ),
            )
            for img in response.generated_images:
                nombre_archivo = f"imagen3_{i}_{uuid.uuid4().hex[:8]}.png"
                ruta = os.path.join(directorio, nombre_archivo)
                with open(ruta, "wb") as f:
                    f.write(img.image.image_bytes)
                url = f"/media/productos/{tenant_id}/{product_id}/ia/{nombre_archivo}"
                urls.append(url)
        except Exception:
            continue

    return urls
