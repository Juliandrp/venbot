"""Tests del CRUD de clientes."""


async def test_crear_cliente(client, auth_headers):
    resp = await client.post("/clientes/", json={
        "nombre": "Juan Pérez",
        "email": "juan@example.com",
        "telefono": "+57 300 111 2222",
        "ciudad": "Bogotá",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["nombre"] == "Juan Pérez"
    assert data["total_pedidos"] == 0
    assert data["total_gastado"] == 0.0


async def test_listar_clientes_con_busqueda(client, auth_headers):
    await client.post("/clientes/", json={"nombre": "María López"}, headers=auth_headers)
    await client.post("/clientes/", json={"nombre": "Carlos García"}, headers=auth_headers)

    resp = await client.get("/clientes/?q=Mar", headers=auth_headers)
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["nombre"] == "María López"


async def test_actualizar_cliente(client, auth_headers):
    crear = await client.post("/clientes/", json={"nombre": "Ana"}, headers=auth_headers)
    cid = crear.json()["id"]

    resp = await client.patch(f"/clientes/{cid}",
                              json={"ciudad": "Medellín"},
                              headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ciudad"] == "Medellín"
    assert resp.json()["nombre"] == "Ana"  # no se borró


async def test_eliminar_cliente(client, auth_headers):
    crear = await client.post("/clientes/", json={"nombre": "Borrar"}, headers=auth_headers)
    cid = crear.json()["id"]

    resp = await client.delete(f"/clientes/{cid}", headers=auth_headers)
    assert resp.status_code in (200, 204)

    listado = await client.get("/clientes/", headers=auth_headers)
    assert listado.json()["total"] == 0


async def test_email_invalido_rechazado(client, auth_headers):
    resp = await client.post("/clientes/", json={
        "nombre": "X", "email": "no-es-email",
    }, headers=auth_headers)
    assert resp.status_code == 422
