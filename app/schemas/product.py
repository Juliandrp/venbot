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


class ProductUpdate(BaseModel):
    nombre: str | None = None
    descripcion_input: str | None = None
    precio: float | None = None
    precio_comparacion: float | None = None
    inventario: int | None = None


class ProductContentOut(BaseModel):
    titulo_seo: str | None = None
    descripcion_seo: str | None = None
    bullet_points: list[str] | None = None
    variantes_copy: dict | None = None
    video_script: str | None = None
    video_url: str | None = None
    video_estado: str | None = None
    imagenes_generadas: list[str] | None = None
    pipeline_paso: int = 0

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: uuid.UUID
    nombre: str
    descripcion_input: str | None = None
    precio: float | None
    precio_comparacion: float | None = None
    inventario: int
    imagenes_originales: list[str] | None = None
    contenido_generado: bool
    publicado_shopify: bool
    shopify_product_id: str | None = None
    shopify_url: str | None
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductDetailOut(ProductOut):
    contenido: ProductContentOut | None = None

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    total: int
    items: list[ProductOut]
