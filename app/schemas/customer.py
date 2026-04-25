import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class CustomerBase(BaseModel):
    nombre: str | None = None
    email: EmailStr | None = None
    telefono: str | None = None
    whatsapp_id: str | None = None
    messenger_id: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    departamento: str | None = None
    pais: str = "CO"


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    nombre: str | None = None
    email: EmailStr | None = None
    telefono: str | None = None
    whatsapp_id: str | None = None
    direccion: str | None = None
    ciudad: str | None = None
    departamento: str | None = None
    pais: str | None = None


class CustomerOut(CustomerBase):
    id: uuid.UUID
    created_at: datetime
    total_pedidos: int = 0
    total_gastado: float = 0.0

    model_config = {"from_attributes": True}


class CustomerListOut(BaseModel):
    total: int
    items: list[CustomerOut]
