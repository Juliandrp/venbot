"""Integración con HeyGen API para generación de videos."""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

HEYGEN_BASE = "https://api.heygen.com/v2"


class HeyGenService:
    def __init__(self, api_key: str):
        self.headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def crear_video(self, script: str, avatar_id: str = "default") -> str:
        """Envía el script a HeyGen y retorna el video_id."""
        payload = {
            "video_inputs": [
                {
                    "character": {"type": "avatar", "avatar_id": avatar_id},
                    "voice": {"type": "text", "input_text": script, "voice_id": "es-CO-SalomeNeural"},
                    "background": {"type": "color", "value": "#ffffff"},
                }
            ],
            "dimension": {"width": 1280, "height": 720},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{HEYGEN_BASE}/video/generate", json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()["data"]["video_id"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def obtener_estado(self, video_id: str) -> dict:
        """Consulta el estado de un video en HeyGen."""
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{HEYGEN_BASE}/video/{video_id}", headers=self.headers)
            response.raise_for_status()
            data = response.json()["data"]
            return {
                "estado": data.get("status"),         # processing | completed | failed
                "video_url": data.get("video_url"),
            }
