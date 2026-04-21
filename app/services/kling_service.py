"""
Generación de videos con Kling AI (Kuaishou).

API: https://api.klingai.com
Docs: https://app.klingai.com/global/dev/api-doc

Flujo:
  1. POST /v1/videos/image2video  →  task_id
  2. GET  /v1/videos/image2video/{task_id}  →  polling hasta status="succeed"
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings

KLING_BASE_URL = "https://api.klingai.com"


class KlingService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.kling_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ── Imagen + guión → video ────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def crear_video_desde_imagen(
        self,
        image_url: str,
        prompt: str,
        duracion: int = 5,
        ratio: str = "9:16",
        modelo: str = "kling-v1-6",
    ) -> str:
        """
        Crea un video a partir de una imagen + prompt.
        Retorna el task_id para hacer polling.

        image_url: URL pública de la imagen del producto.
        prompt: guión/instrucción del movimiento (generado por Claude/Gemini).
        duracion: 5 o 10 segundos.
        ratio: "16:9" | "9:16" | "1:1"
        modelo: "kling-v1" | "kling-v1-5" | "kling-v1-6"
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{KLING_BASE_URL}/v1/videos/image2video",
                headers=self.headers,
                json={
                    "model_name": modelo,
                    "image": image_url,
                    "prompt": prompt,
                    "duration": duracion,
                    "aspect_ratio": ratio,
                    "cfg_scale": 0.5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["task_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def crear_video_desde_texto(
        self,
        prompt: str,
        duracion: int = 5,
        ratio: str = "9:16",
        modelo: str = "kling-v1-6",
    ) -> str:
        """Crea un video solo con prompt de texto (sin imagen de referencia). Retorna task_id."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{KLING_BASE_URL}/v1/videos/text2video",
                headers=self.headers,
                json={
                    "model_name": modelo,
                    "prompt": prompt,
                    "duration": duracion,
                    "aspect_ratio": ratio,
                    "cfg_scale": 0.5,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["task_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def obtener_estado(self, task_id: str) -> dict:
        """
        Consulta el estado de una tarea de video.
        Retorna dict con: estado ("processing"|"succeed"|"failed"), video_url (si succeed).
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{KLING_BASE_URL}/v1/videos/image2video/{task_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            task_status = data.get("task_status", "processing")

            if task_status == "succeed":
                videos = data.get("task_result", {}).get("videos", [])
                url = videos[0]["url"] if videos else None
                return {"estado": "completed", "video_url": url}
            elif task_status == "failed":
                return {"estado": "failed", "video_url": None}
            else:
                return {"estado": "processing", "video_url": None}
