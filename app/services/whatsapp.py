"""Integración con WhatsApp Business API (WABA)."""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

WABA_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppService:
    def __init__(self, phone_number_id: str, token: str):
        self.phone_number_id = phone_number_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def enviar_texto(self, destinatario: str, texto: str) -> str:
        """Envía mensaje de texto. Retorna el message_id."""
        payload = {
            "messaging_product": "whatsapp",
            "to": destinatario,
            "type": "text",
            "text": {"body": texto},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{WABA_BASE}/{self.phone_number_id}/messages",
                json=payload,
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()["messages"][0]["id"]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def enviar_plantilla(self, destinatario: str, nombre_plantilla: str, parametros: list[str]) -> str:
        components = []
        if parametros:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in parametros],
            })
        payload = {
            "messaging_product": "whatsapp",
            "to": destinatario,
            "type": "template",
            "template": {
                "name": nombre_plantilla,
                "language": {"code": "es"},
                "components": components,
            },
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{WABA_BASE}/{self.phone_number_id}/messages",
                json=payload,
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()["messages"][0]["id"]
