"""Tests del flujo de autenticación."""


async def test_register_crea_tenant_y_devuelve_tokens(client):
    resp = await client.post("/auth/register", json={
        "nombre_empresa": "Mi Tienda",
        "email": "nuevo@test.com",
        "password": "secreto123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_register_email_duplicado_falla(client, tenant_normal):
    resp = await client.post("/auth/register", json={
        "nombre_empresa": "Otra",
        "email": "test@example.com",  # ya existe
        "password": "x123456",
    })
    assert resp.status_code == 400
    assert "ya está registrado" in resp.json()["detail"]


async def test_login_credenciales_validas(client, tenant_normal):
    resp = await client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "test123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_password_invalida_devuelve_401(client, tenant_normal):
    resp = await client.post("/auth/login", json={
        "email": "test@example.com",
        "password": "wrong",
    })
    assert resp.status_code == 401


async def test_endpoint_protegido_sin_token_devuelve_401(client):
    resp = await client.get("/tenant/me")
    assert resp.status_code == 401


async def test_endpoint_protegido_con_token_funciona(client, auth_headers):
    resp = await client.get("/tenant/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test@example.com"


async def test_refresh_token_genera_nuevos_tokens(client, tenant_normal):
    login = await client.post("/auth/login", json={
        "email": "test@example.com", "password": "test123",
    })
    refresh = login.json()["refresh_token"]
    resp = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
