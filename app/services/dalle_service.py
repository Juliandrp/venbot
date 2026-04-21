"""Generación de imágenes de producto con DALL-E 3 (OpenAI)."""
import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings


def _get_client(api_key: str | None = None) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key or settings.openai_api_key)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
async def generar_imagenes_producto(
    nombre: str,
    descripcion: str,
    cantidad: int = 3,
    api_key: str | None = None,
) -> list[str]:
    """
    Genera imágenes publicitarias para un producto con DALL-E 3.
    Retorna lista de URLs temporales de OpenAI (válidas 1 hora).
    """
    client = _get_client(api_key)

    estilos = [
        "fotografía profesional de producto sobre fondo blanco limpio, iluminación de estudio",
        "fotografía lifestyle del producto en uso, ambiente moderno latinoamericano",
        "imagen publicitaria del producto con texto espacio vacío, colores vibrantes",
    ]

    urls: list[str] = []
    for i in range(min(cantidad, len(estilos))):
        prompt = (
            f"Imagen publicitaria de alta calidad para e-commerce. "
            f"Producto: {nombre}. {descripcion}. "
            f"Estilo: {estilos[i]}. "
            f"Sin texto, sin marca de agua, 4K, hyperrealista."
        )
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        urls.append(response.data[0].url)

    return urls


async def descargar_imagen(url: str) -> bytes:
    """Descarga el contenido binario de una imagen desde una URL."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content
