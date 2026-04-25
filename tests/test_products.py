"""Tests del CRUD de productos."""
import pytest


async def test_listar_productos_vacio(client, auth_headers):
    resp = await client.get("/productos/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_crear_producto_basico(client, auth_headers):
    resp = await client.post("/productos/", json={
        "nombre": "Licuadora Pro",
        "descripcion_input": "Licuadora portátil USB",
        "precio": 39.99,
        "inventario": 100,
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["nombre"] == "Licuadora Pro"
    assert data["precio"] == 39.99
    assert data["contenido_generado"] is False


async def test_listar_solo_productos_del_tenant_actual(client, auth_headers, db_session, tenant_normal):
    """Multi-tenant isolation: un tenant no ve productos de otro."""
    from app.models.tenant import Tenant
    from app.models.product import Product
    from app.core.security import hash_password

    otro = Tenant(nombre_empresa="Otra", email="otra@x.com",
                  hashed_password=hash_password("x"), activo=True)
    db_session.add(otro)
    await db_session.commit()
    await db_session.refresh(otro)

    db_session.add(Product(tenant_id=otro.id, nombre="Producto Ajeno"))
    db_session.add(Product(tenant_id=tenant_normal.id, nombre="Mi Producto"))
    await db_session.commit()

    resp = await client.get("/productos/", headers=auth_headers)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["nombre"] == "Mi Producto"


async def test_eliminar_producto(client, auth_headers):
    crear = await client.post("/productos/", json={"nombre": "Para borrar"}, headers=auth_headers)
    pid = crear.json()["id"]

    resp = await client.delete(f"/productos/{pid}", headers=auth_headers)
    assert resp.status_code in (200, 204)

    listado = await client.get("/productos/", headers=auth_headers)
    assert listado.json()["total"] == 0


async def test_obtener_producto_inexistente_404(client, auth_headers):
    import uuid
    resp = await client.get(f"/productos/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


async def test_no_se_puede_acceder_producto_de_otro_tenant(client, auth_headers, db_session, tenant_normal):
    from app.models.tenant import Tenant
    from app.models.product import Product
    from app.core.security import hash_password

    otro = Tenant(nombre_empresa="Otra", email="otra2@x.com",
                  hashed_password=hash_password("x"), activo=True)
    db_session.add(otro)
    await db_session.commit()
    await db_session.refresh(otro)

    p = Product(tenant_id=otro.id, nombre="Ajeno")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)

    resp = await client.get(f"/productos/{p.id}", headers=auth_headers)
    assert resp.status_code == 404
