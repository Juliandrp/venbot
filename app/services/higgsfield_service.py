"""
Cliente para Higgsfield.ai — generación de video con IA cinemática.

Documentación: https://higgsfield.ai/docs (API pública)

API endpoints típicos:
  POST /v1/jobs          → crear job (text2video o image2video)
  GET  /v1/jobs/{id}     → consultar estado

Como la API requiere key, configurarla por tenant en TenantConfig.higgsfield_api_key_enc
o via variable HIGGSFIELD_API_KEY.
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

HIGGSFIELD_BASE = "https://api.higgsfield.ai/v1"


class HiggsfieldService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    async def crear_video_desde_texto(
        self,
        prompt: str,
        duracion: int = 5,
        ratio: str = "9:16",
        modelo: str = "lite",
    ) -> str:
        """
        Crea un video text-to-video.
        Retorna el job_id para hacer polling.
        """
        payload = {
            "type": "text2video",
            "model": modelo,
            "prompt": prompt,
            "duration": duracion,
            "aspect_ratio": ratio,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{HIGGSFIELD_BASE}/jobs", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()["job_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    async def crear_video_desde_imagen(
        self,
        image_url: str,
        prompt: str,
        duracion: int = 5,
        ratio: str = "9:16",
        modelo: str = "lite",
    ) -> str:
        """
        Crea un video image-to-video.
        Higgsfield destaca por movimiento de cámara cinemático.
        """
        payload = {
            "type": "image2video",
            "model": modelo,
            "image_url": image_url,
            "prompt": prompt,
            "duration": duracion,
            "aspect_ratio": ratio,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{HIGGSFIELD_BASE}/jobs", json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()["job_id"]

    async def obtener_estado(self, job_id: str) -> dict:
        """
        Consulta el estado del job.
        Retorna: {"estado": "processing|completed|failed", "video_url": "..."}
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{HIGGSFIELD_BASE}/jobs/{job_id}", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()

            status_map = {
                "queued": "procesando",
                "processing": "procesando",
                "running": "procesando",
                "completed": "completed",
                "succeeded": "completed",
                "failed": "failed",
                "error": "failed",
            }
            estado = status_map.get(data.get("status", "").lower(), "procesando")

            return {
                "estado": estado,
                "video_url": data.get("video_url") or data.get("output_url") or "",
                "error": data.get("error_message"),
            }
