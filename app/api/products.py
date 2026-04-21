import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductOut, ProductListOut

router = APIRouter(prefix="/productos", tags=["Productos"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_model=ProductListOut)
async def listar_productos(
    skip: int = 0,
    limit: int = 50,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(func.count()).select_from(Product).where(Product.tenant_id == tenant.id, Product.activo == True)
    )
    total = count_result.scalar()

    result = await db.execute(
        select(Product)
        .where(Product.tenant_id == tenant.id, Product.activo == True)
        .order_by(Product.created_at.desc())
        .offset(skip).limit(limit)
    )
    items = result.scalars().all()
    return ProductListOut(total=total, items=list(items))


@router.post("/", response_model=ProductOut, status_code=201)
async def crear_producto(
    data: ProductCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    producto = Product(tenant_id=tenant.id, **data.model_dump())
    db.add(producto)
    await db.commit()
    await db.refresh(producto)

    # Disparar pipeline de contenido en background
    from app.workers.content_pipeline import generar_contenido_producto
    generar_contenido_producto.delay(str(producto.id), str(tenant.id))

    return producto


@router.get("/{product_id}", response_model=ProductOut)
async def obtener_producto(
    product_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


@router.post("/{product_id}/publicar-shopify", response_model=ProductOut)
async def publicar_en_shopify(
    product_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Publica (o re-publica) un producto en Shopify inmediatamente."""
    from app.models.product import ProductContent
    from app.models.tenant import TenantConfig
    from app.services.shopify_service import ShopifyService
    from app.core.security import decrypt_secret

    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    if not producto.precio:
        raise HTTPException(status_code=400, detail="El producto necesita precio antes de publicar")

    config_result = await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant.id)
    )
    config = config_result.scalar_one_or_none()
    if not config or not config.shopify_store_url or not config.shopify_access_token_enc:
        raise HTTPException(status_code=400, detail="Configura las credenciales de Shopify primero")

    pc_result = await db.execute(
        select(ProductContent).where(ProductContent.product_id == producto.id)
    )
    contenido = pc_result.scalar_one_or_none()

    shopify_token = decrypt_secret(config.shopify_access_token_enc)
    shopify = ShopifyService(config.shopify_store_url, shopify_token)

    descripcion_html = f"<p>{contenido.descripcion_seo}</p>" if contenido and contenido.descripcion_seo else f"<p>{producto.descripcion_input or producto.nombre}</p>"
    if contenido and contenido.bullet_points:
        items_html = "".join(f"<li>{b}</li>" for b in contenido.bullet_points)
        descripcion_html += f"<ul>{items_html}</ul>"

    imagenes = []
    if producto.imagenes_originales:
        imagenes += producto.imagenes_originales
    if contenido and contenido.imagenes_generadas:
        imagenes += contenido.imagenes_generadas
    imagenes = imagenes[:10]

    titulo = (contenido.titulo_seo if contenido and contenido.titulo_seo else producto.nombre)

    resultado = await shopify.publicar_producto(
        titulo=titulo,
        descripcion_html=descripcion_html,
        precio=float(producto.precio),
        precio_comparacion=float(producto.precio_comparacion) if producto.precio_comparacion else None,
        inventario=producto.inventario,
        imagenes=imagenes,
        video_url=contenido.video_url if contenido else None,
    )

    producto.shopify_product_id = resultado["id"]
    producto.shopify_url = resultado["url"]
    producto.publicado_shopify = True
    await db.commit()
    await db.refresh(producto)
    return producto


@router.post("/{product_id}/regenerar-contenido", status_code=202)
async def regenerar_contenido(
    product_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Vuelve a lanzar el pipeline completo de generación de contenido IA."""
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    producto.contenido_generado = False
    await db.commit()

    from app.workers.content_pipeline import generar_contenido_producto
    generar_contenido_producto.delay(str(producto.id), str(tenant.id))
    return {"mensaje": "Pipeline de contenido relanzado en segundo plano"}


@router.delete("/{product_id}", status_code=204)
async def eliminar_producto(
    product_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    producto.activo = False
    await db.commit()


# ─── Vistas HTML ─────────────────────────────────────────────

@router.get("/vista/lista")
async def vista_productos(request: Request, tenant: Tenant = Depends(get_current_tenant)):
    return templates.TemplateResponse("products/index.html", {"request": request, "tenant": tenant})
