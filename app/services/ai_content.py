"""Generación de contenido IA via Claude API."""
import base64
import mimetypes
import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.services.storage import leer_url_como_bytes


GRUPOS_EDAD = ["18-24", "25-34", "35-44", "45+"]
GENEROS = ["M", "F", "todos"]

SYSTEM_PROMPT_CONTENIDO = """Eres un experto en marketing digital y copywriting para e-commerce latinoamericano.
Creas contenido persuasivo, en español, optimizado para ventas en Colombia, México y LATAM.
Siempre respondes en formato JSON estructurado."""


def _get_client(api_key: str | None = None) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key or settings.anthropic_api_key)


async def _url_a_bloque_imagen(url: str) -> dict | None:
    """Convierte cualquier URL (local o S3) a un bloque de imagen base64 para Claude."""
    datos = await leer_url_como_bytes(url)
    if not datos:
        return None
    mime = mimetypes.guess_type(url)[0] or "image/jpeg"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": base64.standard_b64encode(datos).decode()},
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generar_contenido_producto(
    nombre: str,
    descripcion: str,
    api_key: str | None = None,
    image_urls: list[str] | None = None,
) -> dict:
    """Genera título SEO, descripción, bullet points y variantes de copy por segmento."""
    client = _get_client(api_key)

    prompt_text = f"""Producto: {nombre}
Descripción del vendedor: {descripcion}
{"" if not image_urls else "(Analiza las imágenes adjuntas del producto real para generar contenido preciso.)"}

Genera el siguiente JSON (sin markdown, solo el JSON):
{{
  "titulo_seo": "título optimizado SEO máx 70 chars",
  "descripcion_seo": "descripción persuasiva 150-200 palabras",
  "bullet_points": ["beneficio 1", "beneficio 2", "beneficio 3", "beneficio 4", "beneficio 5"],
  "variantes_copy": {{
    "18-24": {{
      "M": "copy anuncio para hombres 18-24 años (máx 125 chars)",
      "F": "copy anuncio para mujeres 18-24 años (máx 125 chars)",
      "todos": "copy anuncio para 18-24 años (máx 125 chars)"
    }},
    "25-34": {{"M": "...", "F": "...", "todos": "..."}},
    "35-44": {{"M": "...", "F": "...", "todos": "..."}},
    "45+":   {{"M": "...", "F": "...", "todos": "..."}}
  }},
  "video_script": "guión de video corto 30-60 segundos para HeyGen"
}}"""

    content: list = []
    if image_urls:
        for url in image_urls[:4]:
            bloque = await _url_a_bloque_imagen(url)
            if bloque:
                content.append(bloque)
    content.append({"type": "text", "text": prompt_text})

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT_CONTENIDO,
        messages=[{"role": "user", "content": content}],
    )

    import json
    text = message.content[0].text.strip()
    return json.loads(text)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generar_respuesta_bot(
    historial: list[dict],
    contexto_producto: str,
    api_key: str | None = None,
) -> tuple[str, float]:
    """Genera respuesta del bot de ventas. Retorna (texto, confianza)."""
    client = _get_client(api_key)

    system = f"""Eres un asesor de ventas experto y amigable para una tienda de e-commerce latinoamericana.
Tu objetivo es cerrar ventas respondiendo dudas, manejando objeciones y guiando al cliente.
Hablas en español latinoamericano, de forma natural y persuasiva, nunca robótica.

Contexto del producto que estás vendiendo:
{contexto_producto}

Cuando el cliente esté listo para comprar, solicita: nombre completo, teléfono, dirección de envío completa, ciudad y departamento.
Si no puedes responder con confianza (tema fuera de contexto, queja grave, solicitud de devolución), responde con:
{{"texto": "tu respuesta", "confianza": 0.3, "transferir": true}}
Si puedes responder con seguridad:
{{"texto": "tu respuesta", "confianza": 0.9, "transferir": false}}

Responde SIEMPRE en JSON con esa estructura."""

    messages = [{"role": m["rol"], "content": m["contenido"]} for m in historial[-20:]]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=messages,
    )

    import json
    data = json.loads(response.content[0].text.strip())
    return data.get("texto", ""), float(data.get("confianza", 0.8))
