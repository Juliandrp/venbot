"""Integración con Dropi API para creación y seguimiento de pedidos."""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

DROPI_BASE = "https://api.dropi.co/integration"


class DropiService:
    def __init__(self, api_key: str, store_id: str):
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.store_id = store_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def crear_pedido(
        self,
        nombre: str,
        telefono: str,
        direccion: str,
        ciudad: str,
        departamento: str,
        producto_referencia: str,
        cantidad: int,
        valor_total: float,
        notas: str | None = None,
    ) -> dict:
        """Crea un pedido en Dropi. Retorna {dropi_order_id, estado}."""
        payload = {
            "store_id": self.store_id,
            "customer": {
                "name": nombre,
                "phone": telefono,
                "address": direccion,
                "city": ciudad,
                "state": departamento,
                "country": "CO",
            },
            "items": [
                {"sku": producto_referencia, "quantity": cantidad, "price": valor_total}
            ],
            "notes": notas or "",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{DROPI_BASE}/orders", json=payload, headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return {
                "dropi_order_id": str(data.get("id") or data.get("order_id")),
                "estado": data.get("status", "pendiente"),
            }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def consultar_estado(self, dropi_order_id: str) -> dict:
        """Consulta el estado de envío de un pedido."""
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{DROPI_BASE}/orders/{dropi_order_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "estado": data.get("status"),
                "numero_seguimiento": data.get("tracking_number"),
                "transportadora": data.get("carrier"),
                "ubicacion": data.get("location"),
            }
