"""Integración con Meta Marketing API."""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.security import decrypt_secret

META_GRAPH = "https://graph.facebook.com/v21.0"

SEGMENTOS = [
    {"grupo_edad": "18-24", "genero": "M", "meta_age_min": 18, "meta_age_max": 24, "meta_genders": [1]},
    {"grupo_edad": "18-24", "genero": "F", "meta_age_min": 18, "meta_age_max": 24, "meta_genders": [2]},
    {"grupo_edad": "25-34", "genero": "M", "meta_age_min": 25, "meta_age_max": 34, "meta_genders": [1]},
    {"grupo_edad": "25-34", "genero": "F", "meta_age_min": 25, "meta_age_max": 34, "meta_genders": [2]},
    {"grupo_edad": "35-44", "genero": "M", "meta_age_min": 35, "meta_age_max": 44, "meta_genders": [1]},
    {"grupo_edad": "35-44", "genero": "F", "meta_age_min": 35, "meta_age_max": 44, "meta_genders": [2]},
    {"grupo_edad": "45+",   "genero": "todos", "meta_age_min": 45, "meta_age_max": 65, "meta_genders": [0]},
]


class MetaAdsService:
    def __init__(self, config):
        self.token = decrypt_secret(config.meta_access_token_enc) if config.meta_access_token_enc else ""
        self.ad_account = config.meta_ad_account_id or ""
        self.pixel_id = config.meta_pixel_id or ""

    def _params(self, extra: dict | None = None) -> dict:
        p = {"access_token": self.token}
        if extra:
            p.update(extra)
        return p

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def crear_campana(self, campana, db) -> str:
        """Crea campaña en Meta y todos sus AdSets segmentados. Retorna campaign_id."""
        from app.models.campaign import AdSet
        from app.models.product import ProductContent

        # 1. Crear campaña
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{META_GRAPH}/act_{self.ad_account}/campaigns",
                params=self._params({
                    "name": campana.nombre,
                    "objective": campana.meta_campaign_objective,
                    "status": "ACTIVE",
                    "special_ad_categories": [],
                }),
            )
            resp.raise_for_status()
            campaign_id = resp.json()["id"]

        # 2. Obtener variantes de copy del producto
        from sqlalchemy import select
        result = await db.execute(
            select(ProductContent).where(ProductContent.product_id == campana.product_id)
        )
        contenido = result.scalar_one_or_none()
        variantes = (contenido.variantes_copy or {}) if contenido else {}

        # 3. Crear AdSets por segmento
        for seg in SEGMENTOS:
            copy_texto = (
                variantes.get(seg["grupo_edad"], {}).get(seg["genero"])
                or variantes.get(seg["grupo_edad"], {}).get("todos", "")
                or campana.nombre
            )
            async with httpx.AsyncClient(timeout=30) as client:
                adset_resp = await client.post(
                    f"{META_GRAPH}/act_{self.ad_account}/adsets",
                    params=self._params({
                        "name": f"{campana.nombre} | {seg['grupo_edad']} | {seg['genero']}",
                        "campaign_id": campaign_id,
                        "daily_budget": int(campana.presupuesto_diario / len(SEGMENTOS) * 100),  # centavos
                        "billing_event": "IMPRESSIONS",
                        "optimization_goal": "OFFSITE_CONVERSIONS",
                        "targeting": {
                            "age_min": seg["meta_age_min"],
                            "age_max": seg["meta_age_max"],
                            "genders": seg["meta_genders"],
                            "geo_locations": {"countries": ["CO", "MX", "PE", "EC"]},
                        },
                        "pixel_id": self.pixel_id,
                        "status": "ACTIVE",
                    }),
                )
                adset_resp.raise_for_status()
                adset_id = adset_resp.json()["id"]

            ad_set = AdSet(
                campaign_id=campana.id,
                tenant_id=campana.tenant_id,
                meta_adset_id=adset_id,
                grupo_edad=seg["grupo_edad"],
                genero=seg["genero"],
                copy_anuncio=copy_texto,
            )
            db.add(ad_set)

        await db.commit()
        return campaign_id

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def obtener_metricas(self, campaign_id: str) -> dict:
        fields = "impressions,clicks,spend,actions,action_values"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{META_GRAPH}/{campaign_id}/insights",
                params=self._params({"fields": fields, "date_preset": "today"}),
            )
            resp.raise_for_status()
            data = resp.json().get("data", [{}])
            return data[0] if data else {}

    async def pausar_adset(self, adset_id: str):
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{META_GRAPH}/{adset_id}",
                params=self._params({"status": "PAUSED"}),
            )
            resp.raise_for_status()
