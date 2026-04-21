"""Worker: monitoreo y auto-pausa de campañas Meta Ads."""
import asyncio
from app.celery_app import celery_app


@celery_app.task(name="app.workers.campaign_monitor.check_all_campaigns", bind=True)
def check_all_campaigns(self):
    asyncio.run(_check_campaigns())


async def _check_campaigns():
    from app.database import AsyncSessionLocal
    from app.models.campaign import Campaign, CampaignStatus, AdSet, AdPerformanceSnapshot
    from app.models.tenant import TenantConfig
    from app.services.meta_ads import MetaAdsService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Campaign).where(Campaign.estado == CampaignStatus.activa, Campaign.meta_campaign_id.isnot(None))
        )
        campanas = result.scalars().all()

        for campana in campanas:
            try:
                c_result = await db.execute(
                    select(TenantConfig).where(TenantConfig.tenant_id == campana.tenant_id)
                )
                config = c_result.scalar_one_or_none()
                if not config or not config.meta_access_token_enc:
                    continue

                service = MetaAdsService(config)
                metricas = await service.obtener_metricas(campana.meta_campaign_id)

                impresiones = int(metricas.get("impressions", 0))
                clics = int(metricas.get("clicks", 0))
                gasto = float(metricas.get("spend", 0))

                # Calcular conversiones y ROAS desde actions
                conversiones = 0
                revenue = 0.0
                for action in metricas.get("actions", []):
                    if action.get("action_type") == "purchase":
                        conversiones += int(action.get("value", 0))
                for av in metricas.get("action_values", []):
                    if av.get("action_type") == "purchase":
                        revenue += float(av.get("value", 0))

                roas = revenue / gasto if gasto > 0 else 0.0
                ctr = clics / impresiones if impresiones > 0 else 0.0
                cpc = gasto / clics if clics > 0 else 0.0

                # Guardar snapshot
                snapshot = AdPerformanceSnapshot(
                    campaign_id=campana.id,
                    tenant_id=campana.tenant_id,
                    impresiones=impresiones,
                    clics=clics,
                    gasto=gasto,
                    conversiones=conversiones,
                    roas=roas,
                    ctr=ctr,
                    cpc=cpc,
                    datos_raw=metricas,
                )
                db.add(snapshot)

                # Auto-pausa si ROAS por debajo del mínimo configurado
                if campana.roas_minimo and roas > 0 and roas < campana.roas_minimo:
                    campana.estado = CampaignStatus.pausada
                    await service.pausar_adset(campana.meta_campaign_id)

                # Auto-pausa si CPC por encima del máximo
                if campana.cpc_maximo and cpc > 0 and cpc > campana.cpc_maximo:
                    campana.estado = CampaignStatus.pausada

            except Exception:
                pass  # No interrumpir el loop por un tenant con error

        await db.commit()
