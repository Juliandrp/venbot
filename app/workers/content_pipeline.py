"""
Worker: pipeline completo de generación de contenido IA para productos.

Flujo:
  1. Claude → título SEO, descripción, bullet points, variantes de copy, guión de video
  2. DALL-E 3 → imágenes de producto (3 variantes)
  3. HeyGen → video con el guión generado
  4. (Opcional) Shopify → publicar el producto si la integración está configurada
"""
import asyncio
import uuid
from app.celery_app import celery_app


@celery_app.task(
    name="app.workers.content_pipeline.generar_contenido_producto",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generar_contenido_producto(self, product_id: str, tenant_id: str):
    try:
        asyncio.run(_pipeline(product_id, tenant_id))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _pipeline(product_id: str, tenant_id: str):
    from app.database import AsyncSessionLocal
    from app.models.product import Product, ProductContent
    from app.models.tenant import TenantConfig
    from app.services.ai_content import generar_contenido_producto as ai_generar
    from app.services.dalle_service import generar_imagenes_producto
    from app.services.heygen import HeyGenService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        p_result = await db.execute(select(Product).where(Product.id == uuid.UUID(product_id)))
        producto = p_result.scalar_one_or_none()
        if not producto:
            return

        c_result = await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == uuid.UUID(tenant_id))
        )
        config = c_result.scalar_one_or_none()

        # ── Obtener o crear ProductContent ──────────────────────────────
        pc_result = await db.execute(
            select(ProductContent).where(ProductContent.product_id == producto.id)
        )
        contenido = pc_result.scalar_one_or_none()
        if not contenido:
            contenido = ProductContent(product_id=producto.id)
            db.add(contenido)

        # ── Paso 1: Claude — copy y guión ───────────────────────────────
        anthropic_key = None
        if config and config.anthropic_api_key_enc:
            anthropic_key = decrypt_secret(config.anthropic_api_key_enc)

        datos = await ai_generar(
            nombre=producto.nombre,
            descripcion=producto.descripcion_input or producto.nombre,
            api_key=anthropic_key,
        )
        contenido.titulo_seo = datos.get("titulo_seo")
        contenido.descripcion_seo = datos.get("descripcion_seo")
        contenido.bullet_points = datos.get("bullet_points")
        contenido.variantes_copy = datos.get("variantes_copy")
        contenido.video_script = datos.get("video_script")
        await db.commit()

        # ── Paso 2: DALL-E 3 — imágenes ────────────────────────────────
        openai_key = None
        from app.config import settings
        if settings.openai_api_key:
            openai_key = settings.openai_api_key

        try:
            urls_imagenes = await generar_imagenes_producto(
                nombre=producto.nombre,
                descripcion=producto.descripcion_input or "",
                cantidad=3,
                api_key=openai_key,
            )
            contenido.imagenes_generadas = urls_imagenes
            await db.commit()
        except Exception:
            pass  # No bloquear si falla la generación de imágenes

        # ── Paso 3: HeyGen — video ──────────────────────────────────────
        heygen_key = None
        if config and config.heygen_api_key_enc:
            heygen_key = decrypt_secret(config.heygen_api_key_enc)

        if heygen_key and contenido.video_script:
            try:
                heygen = HeyGenService(heygen_key)
                video_id = await heygen.crear_video(contenido.video_script)
                contenido.heygen_video_id = video_id
                contenido.video_estado = "procesando"
                await db.commit()
            except Exception:
                pass

        # ── Paso 4: Publicar en Shopify (si está configurado y hay precio) ──
        shopify_url_store = config.shopify_store_url if config else None
        shopify_token_enc = config.shopify_access_token_enc if config else None

        if shopify_url_store and shopify_token_enc and producto.precio:
            try:
                shopify_token = decrypt_secret(shopify_token_enc)
                from app.services.shopify_service import ShopifyService

                descripcion_html = f"<p>{contenido.descripcion_seo}</p>"
                if contenido.bullet_points:
                    items_html = "".join(f"<li>{b}</li>" for b in contenido.bullet_points)
                    descripcion_html += f"<ul>{items_html}</ul>"

                imagenes = (
                    (producto.imagenes_originales or []) + (contenido.imagenes_generadas or [])
                )[:10]

                shopify = ShopifyService(shopify_url_store, shopify_token)
                resultado = await shopify.publicar_producto(
                    titulo=contenido.titulo_seo or producto.nombre,
                    descripcion_html=descripcion_html,
                    precio=float(producto.precio),
                    precio_comparacion=float(producto.precio_comparacion) if producto.precio_comparacion else None,
                    inventario=producto.inventario,
                    imagenes=imagenes,
                    video_url=contenido.video_url,
                )
                producto.shopify_product_id = resultado["id"]
                producto.shopify_url = resultado["url"]
                producto.publicado_shopify = True
                await db.commit()
            except Exception:
                pass

        producto.contenido_generado = True
        await db.commit()


@celery_app.task(
    name="app.workers.content_pipeline.verificar_video_heygen",
    bind=True,
    max_retries=10,
    default_retry_delay=300,  # Verificar cada 5 min hasta que esté listo
)
def verificar_video_heygen(self, product_id: str, tenant_id: str):
    """Tarea que se auto-reencola hasta que HeyGen termine de procesar el video."""
    asyncio.run(_verificar_video(product_id, tenant_id, self))


async def _verificar_video(product_id: str, tenant_id: str, task):
    from app.database import AsyncSessionLocal
    from app.models.product import ProductContent
    from app.models.tenant import TenantConfig
    from app.services.heygen import HeyGenService
    from app.core.security import decrypt_secret
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        pc_result = await db.execute(
            select(ProductContent).where(ProductContent.product_id == uuid.UUID(product_id))
        )
        contenido = pc_result.scalar_one_or_none()
        if not contenido or not contenido.heygen_video_id:
            return
        if contenido.video_estado == "completed":
            return

        config_result = await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == uuid.UUID(tenant_id))
        )
        config = config_result.scalar_one_or_none()
        if not config or not config.heygen_api_key_enc:
            return

        heygen_key = decrypt_secret(config.heygen_api_key_enc)
        heygen = HeyGenService(heygen_key)
        estado = await heygen.obtener_estado(contenido.heygen_video_id)

        if estado["estado"] == "completed":
            contenido.video_url = estado["video_url"]
            contenido.video_estado = "completed"
            await db.commit()
        elif estado["estado"] == "failed":
            contenido.video_estado = "failed"
            await db.commit()
        else:
            # Todavía procesando — reintentar
            raise task.retry()
