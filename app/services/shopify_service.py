"""Integración con Shopify Admin API."""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


class ShopifyService:
    def __init__(self, store_url: str, access_token: str):
        self.base = f"https://{store_url}/admin/api/2024-10"
        self.headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def publicar_producto(
        self,
        titulo: str,
        descripcion_html: str,
        precio: float,
        precio_comparacion: float | None,
        inventario: int,
        imagenes: list[str],
        video_url: str | None = None,
    ) -> dict:
        """Crea un producto en Shopify y retorna {id, url}."""
        body = {
            "product": {
                "title": titulo,
                "body_html": descripcion_html,
                "status": "active",
                "variants": [
                    {
                        "price": str(precio),
                        "compare_at_price": str(precio_comparacion) if precio_comparacion else None,
                        "inventory_quantity": inventario,
                        "inventory_management": "shopify",
                    }
                ],
                "images": [{"src": url} for url in imagenes],
            }
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.base}/products.json", json=body, headers=self.headers)
            response.raise_for_status()
            product = response.json()["product"]
            return {
                "id": str(product["id"]),
                "url": f"https://{self.base.split('/')[2]}/products/{product['handle']}",
            }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def actualizar_producto(self, shopify_id: str, campos: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"{self.base}/products/{shopify_id}.json",
                json={"product": campos},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()["product"]
