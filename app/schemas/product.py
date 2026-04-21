import uuid
from datetime import datetime
from pydantic import BaseModel


class ProductCreate(BaseModel):
    nombre: str
    descripcion_input: str | None = None
    precio: float | None = None
    precio_comparacion: float | None = None
    inventario: int = 0
    imagenes_originales: list[str] | None = None


class ProductOut(BaseModel):
    id: uuid.UUID
    nombre: str
    precio: float | None
    inventario: int
    contenido_generado: bool
    publicado_shopify: bool
    shopify_url: str | None
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    total: int
    items: list[ProductOut]
