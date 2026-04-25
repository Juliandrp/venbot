"""Tests de validación de límites por plan."""
import pytest
from app.models.tenant import SubscriptionPlan, PlanTier


@pytest.fixture
async def plan_limitado(db_session, tenant_normal):
    """Plan que solo permite 2 productos y 1 campaña."""
    plan = SubscriptionPlan(
        nombre="Test Mini",
        tier=PlanTier.starter,
        max_productos=2,
        max_campanas=1,
        max_mensajes_bot=10,
        precio_mensual=0,
        activo=True,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    tenant_normal.plan_id = plan.id
    await db_session.commit()
    return plan


async def test_crear_producto_dentro_del_limite(client, auth_headers, plan_limitado):
    r1 = await client.post("/productos/", json={"nombre": "P1"}, headers=auth_headers)
    assert r1.status_code == 201

    r2 = await client.post("/productos/", json={"nombre": "P2"}, headers=auth_headers)
    assert r2.status_code == 201


async def test_crear_producto_excede_limite_devuelve_402(client, auth_headers, plan_limitado):
    await client.post("/productos/", json={"nombre": "P1"}, headers=auth_headers)
    await client.post("/productos/", json={"nombre": "P2"}, headers=auth_headers)

    r3 = await client.post("/productos/", json={"nombre": "P3"}, headers=auth_headers)
    assert r3.status_code == 402
    assert "límite" in r3.json()["detail"]


async def test_endpoint_uso_devuelve_metricas(client, auth_headers, plan_limitado):
    await client.post("/productos/", json={"nombre": "P1"}, headers=auth_headers)

    resp = await client.get("/tenant/uso", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "Test Mini"
    assert data["productos"]["usado"] == 1
    assert data["productos"]["limite"] == 2
    assert data["campanas"]["limite"] == 1


async def test_superadmin_no_tiene_limites(client, admin_headers, db_session, superadmin):
    # Crear plan limitado y asignarlo al superadmin
    plan = SubscriptionPlan(
        nombre="Mini", tier=PlanTier.starter,
        max_productos=1, max_campanas=1, max_mensajes_bot=10,
        precio_mensual=0, activo=True,
    )
    db_session.add(plan)
    await db_session.commit()
    superadmin.plan_id = plan.id
    await db_session.commit()

    # Debería poder crear más de 1 producto sin importar el plan
    for i in range(3):
        r = await client.post("/productos/", json={"nombre": f"P{i}"}, headers=admin_headers)
        assert r.status_code == 201


async def test_tenant_sin_plan_usa_defaults_trial(client, auth_headers):
    resp = await client.get("/tenant/uso", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "Trial"
    # Defaults definidos en plan_limits.py
    assert data["productos"]["limite"] == 5
    assert data["campanas"]["limite"] == 1
