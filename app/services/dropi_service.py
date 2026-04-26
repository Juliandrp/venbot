"""
Integración con Dropi API.

Endpoints implementados:
  - crear_pedido       — al cerrar venta desde el bot
  - consultar_estado   — tracking automático cada 2h
  - cotizar_envio      — bot lo llama cuando cliente pregunta por envío
  - listar_productos   — para importar al catálogo de Venbot
  - obtener_producto   — detalle de un producto específico

Documentación oficial: https://api.dropi.co/docs (puede variar)
Si la API real difiere, ajustar los path/payload aquí — el resto de la app
ya está hecho contra esta interfaz.
"""
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

    # ─── Pedidos ──────────────────────────────────────────────

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
                "name": nombre, "phone": telefono, "address": direccion,
                "city": ciudad, "state": departamento, "country": "CO",
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
        """Consulta el estado de envío de un pedido existente."""
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

    # ─── Cotización de envío (para que el bot responda en vivo) ────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def cotizar_envio(
        self,
        ciudad: str,
        departamento: str,
        peso_kg: float = 1.0,
        valor_declarado: float = 50000,
    ) -> dict | None:
        """
        Cotiza el envío a una ciudad/departamento.
        Retorna: {"min": float, "max": float, "transportadoras": [{"nombre", "valor", "dias"}]}
        o None si no hay cobertura.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{DROPI_BASE}/shipping/quote",
                    json={
                        "store_id": self.store_id,
                        "destination": {
                            "city": ciudad,
                            "state": departamento,
                            "country": "CO",
                        },
                        "weight_kg": peso_kg,
                        "declared_value": valor_declarado,
                    },
                    headers=self.headers,
                )
                if resp.status_code == 404:
                    return None  # Sin cobertura
                resp.raise_for_status()
                data = resp.json()

                opciones = data.get("options") or data.get("carriers") or []
                if not opciones:
                    return None

                normalizadas = []
                for opt in opciones:
                    normalizadas.append({
                        "nombre": opt.get("carrier") or opt.get("name", "Transportadora"),
                        "valor": float(opt.get("price") or opt.get("cost", 0)),
                        "dias": opt.get("estimated_days") or opt.get("delivery_days", "2-5"),
                    })

                valores = [t["valor"] for t in normalizadas if t["valor"] > 0]
                return {
                    "min": min(valores) if valores else 0,
                    "max": max(valores) if valores else 0,
                    "transportadoras": normalizadas,
                }
        except Exception:
            return None

    # ─── Catálogo de productos (para importar a Venbot) ──────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def listar_productos(self, page: int = 1, limit: int = 50, search: str | None = None) -> dict:
        """
        Lista productos disponibles del catálogo Dropi del tenant.
        Retorna: {"total": int, "items": [{"id", "nombre", "precio", "imagen", "descripcion", "sku"}]}
        """
        params = {"store_id": self.store_id, "page": page, "limit": limit}
        if search:
            params["search"] = search

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{DROPI_BASE}/products",
                params=params,
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()

            items_raw = data.get("data") or data.get("items") or data.get("products") or []
            items = []
            for p in items_raw:
                items.append({
                    "id": str(p.get("id") or p.get("product_id") or ""),
                    "nombre": p.get("name") or p.get("title") or "Sin nombre",
                    "descripcion": p.get("description") or p.get("short_description") or "",
                    "precio": float(p.get("price") or p.get("sale_price") or 0),
                    "precio_comparacion": float(p.get("compare_price") or p.get("original_price") or 0) or None,
                    "imagen": (p.get("images") or [None])[0] if p.get("images") else (p.get("image") or p.get("image_url")),
                    "imagenes": p.get("images") or ([p.get("image")] if p.get("image") else []),
                    "sku": p.get("sku") or "",
                    "inventario": int(p.get("stock") or p.get("inventory", 0)),
                })

            return {
                "total": data.get("total") or len(items),
                "page": page,
                "items": items,
            }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def obtener_producto(self, dropi_product_id: str) -> dict | None:
        """Detalle completo de un producto específico de Dropi."""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{DROPI_BASE}/products/{dropi_product_id}",
                    headers=self.headers,
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                p = resp.json()
                return {
                    "id": str(p.get("id") or dropi_product_id),
                    "nombre": p.get("name") or p.get("title") or "",
                    "descripcion": p.get("description") or "",
                    "precio": float(p.get("price") or 0),
                    "precio_comparacion": float(p.get("compare_price") or 0) or None,
                    "imagenes": p.get("images") or ([p.get("image")] if p.get("image") else []),
                    "sku": p.get("sku") or "",
                    "inventario": int(p.get("stock") or 0),
                    "peso_kg": float(p.get("weight") or 1.0),
                }
        except Exception:
            return None
