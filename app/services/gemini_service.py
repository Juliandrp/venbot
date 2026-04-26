"""Generación de contenido IA via Gemini Flash."""
import json
import mimetypes
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.services.storage import leer_url_como_bytes

# Modelo Flash más reciente. "gemini-2.0-flash" devuelve 404 desde 2026-Q1.
# Cambiar a "gemini-2.5-pro" si necesitas mejor calidad (más caro/lento).
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT_CONTENIDO = (
    "Eres un experto en marketing digital y copywriting para e-commerce latinoamericano. "
    "Creas contenido persuasivo, en español, optimizado para ventas en Colombia, México y LATAM. "
    "Siempre respondes en formato JSON estructurado, sin bloques markdown."
)


def _get_client(api_key: str | None = None):
    from google import genai
    return genai.Client(api_key=api_key or settings.gemini_api_key)


async def _leer_partes_imagen(image_urls: list[str]) -> list:
    """Lee imágenes (locales o S3) y las convierte en Parts de Gemini."""
    from google.genai import types
    partes = []
    for url in image_urls[:4]:
        datos = await leer_url_como_bytes(url)
        if not datos:
            continue
        mime = mimetypes.guess_type(url)[0] or "image/jpeg"
        partes.append(types.Part.from_bytes(data=datos, mime_type=mime))
    return partes


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generar_contenido_producto(
    nombre: str,
    descripcion: str,
    api_key: str | None = None,
    image_urls: list[str] | None = None,
    model: str | None = None,
) -> dict:
    """Genera título SEO, descripción, bullet points y variantes de copy por segmento."""
    client = _get_client(api_key)

    prompt_text = f"""{SYSTEM_PROMPT_CONTENIDO}

Producto: {nombre}
Descripción del vendedor: {descripcion}
{"(Analiza las imágenes adjuntas del producto real para generar contenido preciso.)" if image_urls else ""}

Genera el siguiente JSON (sin markdown, solo el JSON):
{{
  "titulo_seo": "título optimizado SEO máx 70 chars",
  "descripcion_seo": "descripción persuasiva 150-200 palabras",
  "bullet_points": ["beneficio 1", "beneficio 2", "beneficio 3", "beneficio 4", "beneficio 5"],
  "variantes_copy": {{
    "18-24": {{"M": "copy máx 125 chars", "F": "copy máx 125 chars", "todos": "copy máx 125 chars"}},
    "25-34": {{"M": "...", "F": "...", "todos": "..."}},
    "35-44": {{"M": "...", "F": "...", "todos": "..."}},
    "45+":   {{"M": "...", "F": "...", "todos": "..."}}
  }},
  "video_script": "guión de video corto 30-60 segundos para HeyGen"
}}"""

    contents = []
    if image_urls:
        contents.extend(await _leer_partes_imagen(image_urls))
    contents.append(prompt_text)

    response = await client.aio.models.generate_content(model=model or MODEL, contents=contents)
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generar_respuesta_bot(
    historial: list[dict],
    contexto_producto: str,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[str, float]:
    """Genera respuesta del bot de ventas. Retorna (texto, confianza)."""
    client = _get_client(api_key)

    system = (
        f"Eres un asesor de ventas experto y amigable para una tienda de e-commerce latinoamericana. "
        f"Tu objetivo es cerrar ventas respondiendo dudas, manejando objeciones y guiando al cliente. "
        f"Hablas en español latinoamericano, de forma natural y persuasiva, nunca robótica.\n\n"
        f"Contexto del producto:\n{contexto_producto}\n\n"
        f"Cuando el cliente esté listo para comprar, solicita: nombre completo, teléfono, dirección, ciudad y departamento.\n"
        f'Si no puedes responder con confianza: {{"texto": "tu respuesta", "confianza": 0.3, "transferir": true}}\n'
        f'Si puedes responder con seguridad: {{"texto": "tu respuesta", "confianza": 0.9, "transferir": false}}\n'
        f"Responde SIEMPRE en JSON con esa estructura, sin markdown."
    )

    mensajes_txt = "\n".join(
        f"{'Cliente' if m['rol'] == 'user' else 'Asesor'}: {m['contenido']}"
        for m in historial[-20:]
    )
    prompt = f"{system}\n\nConversación:\n{mensajes_txt}\nAsesor:"

    response = await client.aio.models.generate_content(
        model=model or MODEL,
        contents=prompt,
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text.strip())
    return data.get("texto", ""), float(data.get("confianza", 0.8))
