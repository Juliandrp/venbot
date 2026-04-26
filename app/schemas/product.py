import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


def _empty_to_none(v):
    """Convierte string vacío a None — el frontend envía '' cuando el campo está vacío."""
    if v == "" or v is None:
        return None
    return v


class ProductCreate(BaseModel):
    nombre: str
    descripcion_input: str | None = None
    precio: float | None = None
    precio_comparacion: float | None = None
    inventario: int = 0
    imagenes_originales: list[str] | None = None

    @field_validator("precio", "precio_comparacion", mode="before")
    @classmethod
    def _empty_float(cls, v):
        return _empty_to_none(v)

    @field_validator("inventario", mode="before")
    @classmethod
    def _empty_inv(cls, v):
        if v == "" or v is None:
            return 0
        return v


class ProductUpdate(BaseModel):
    nombre: str | None = None
    descripcion_input: str | None = None
    precio: float | None = None
    precio_comparacion: float | None = None
    inventario: int | None = None

    @field_validator("precio", "precio_comparacion", "inventario", mode="before")
    @classmethod
    def _empty_num(cls, v):
        return _empty_to_none(v)


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
    dropi_product_id: str | None = None
    activo: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductDetailOut(ProductOut):
    contenido: ProductContentOut | None = None

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    total: int
    items: list[ProductOut]
