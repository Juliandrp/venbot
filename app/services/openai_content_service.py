"""Generación de contenido IA via OpenAI (GPT-4o)."""
import json
import base64
import mimetypes
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings
from app.services.storage import leer_url_como_bytes


def _get_client(api_key: str | None = None) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key or settings.openai_api_key)


async def _url_a_base64(url: str) -> dict | None:
    datos = await leer_url_como_bytes(url)
    if not datos:
        return None
    mime = mimetypes.guess_type(url)[0] or "image/jpeg"
    b64 = base64.standard_b64encode(datos).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


SYSTEM_PROMPT = """Eres un experto en marketing digital y copywriting para e-commerce latinoamericano.
Creas contenido persuasivo, en español, optimizado para ventas en Colombia, México y LATAM.
Siempre respondes en formato JSON estructurado, sin bloques markdown."""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def generar_contenido_producto(
    nombre: str,
    descripcion: str,
    api_key: str | None = None,
    image_urls: list[str] | None = None,
) -> dict:
    client = _get_client(api_key)

    prompt_text = f"""Producto: {nombre}
Descripción del vendedor: {descripcion}
{"(Analiza las imágenes adjuntas del producto real para generar contenido preciso.)" if image_urls else ""}

Genera el siguiente JSON (sin markdown):
{{
  "titulo_seo": "título optimizado SEO máx 70 chars",
  "descripcion_seo": "descripción persuasiva 150-200 palabras",
  "bullet_points": ["beneficio 1","beneficio 2","beneficio 3","beneficio 4","beneficio 5"],
  "variantes_copy": {{
    "18-24": {{"M":"copy máx 125 chars","F":"copy máx 125 chars","todos":"copy máx 125 chars"}},
    "25-34": {{"M":"...","F":"...","todos":"..."}},
    "35-44": {{"M":"...","F":"...","todos":"..."}},
    "45+":   {{"M":"...","F":"...","todos":"..."}}
  }},
  "video_script": "guión de video corto 30-60 segundos"
}}"""

    content: list = []
    if image_urls:
        for url in image_urls[:4]:
            bloque = await _url_a_base64(url)
            if bloque:
                content.append(bloque)
    content.append({"type": "text", "text": prompt_text})

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=2048,
    )

    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
