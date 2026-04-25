"""Tests del panel de admin y flujo de billing."""
import pytest
from app.models.tenant import SubscriptionPlan, PlanTier, PlanStatus


async def test_admin_endpoints_requieren_superadmin(client, auth_headers):
    """Tenant común no debe poder acceder a /admin/*."""
    resp = await client.get("/admin/tenants", headers=auth_headers)
    assert resp.status_code == 403


async def test_admin_lista_tenants(client, admin_headers, tenant_normal):
    resp = await client.get("/admin/tenants", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    emails = [t["email"] for t in data["items"]]
    assert "test@example.com" in emails


async def test_admin_metricas_globales(client, admin_headers, tenant_normal):
    resp = await client.get("/admin/metricas", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tenants" in data
    assert "revenue_global" in data
    assert "total_mensajes" in data


async def test_admin_suspender_tenant(client, admin_headers, tenant_normal, db_session):
    resp = await client.post(f"/admin/tenants/{tenant_normal.id}/suspender", headers=admin_headers)
    assert resp.status_code == 200

    await db_session.refresh(tenant_normal)
    assert tenant_normal.estado_suscripcion == PlanStatus.suspended
    assert tenant_normal.activo is False


async def test_admin_crear_plan(client, admin_headers):
    resp = await client.post("/admin/planes", json={
        "nombre": "Pro",
        "tier": "pro",
        "max_productos": 100,
        "max_campanas": 20,
        "max_mensajes_bot": 5000,
        "precio_mensual_usd": 49.99,
        "activo": True,
    }, headers=admin_headers)
    assert resp.status_code == 201
    assert "id" in resp.json()


async def test_tenant_lista_planes_disponibles(client, auth_headers, db_session):
    plan = SubscriptionPlan(
        nombre="Starter", tier=PlanTier.starter,
        max_productos=10, max_campanas=2, max_mensajes_bot=500,
        precio_mensual=999, activo=True,
    )
    db_session.add(plan)
    await db_session.commit()

    resp = await client.get("/tenant/planes-disponibles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["planes"]) == 1
    assert data["planes"][0]["precio_mensual_usd"] == 9.99


async def test_upgrade_plan_manual_activa(client, auth_headers, db_session, tenant_normal):
    plan = SubscriptionPlan(
        nombre="Pro", tier=PlanTier.pro,
        max_productos=50, max_campanas=10, max_mensajes_bot=2000,
        precio_mensual=2999, activo=True,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    resp = await client.post("/tenant/upgrade-plan",
                             json={"plan_id": plan.id},
                             headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["plan"] == "Pro"

    await db_session.refresh(tenant_normal)
    assert tenant_normal.plan_id == plan.id
    assert tenant_normal.estado_suscripcion == PlanStatus.active


async def test_checkout_sin_provider_devuelve_503(client, auth_headers, db_session):
    plan = SubscriptionPlan(
        nombre="X", tier=PlanTier.starter,
        max_productos=1, max_campanas=1, max_mensajes_bot=1,
        precio_mensual=100, activo=True,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)

    resp = await client.post(f"/billing/checkout/{plan.id}", headers=auth_headers)
    assert resp.status_code == 503  # PAYMENT_PROVIDER no configurado en tests
