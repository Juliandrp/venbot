import uuid
import os
import mimetypes
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut, ProductDetailOut, ProductListOut

MEDIA_ROOT = "/app/media"
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}

router = APIRouter(prefix="/productos", tags=["Productos"])
templates = Jinja2Templates(directory="app/templates")


# ─── Vistas HTML (antes de rutas con parámetros) ─────────────

@router.get("/vista/lista")
async def vista_productos(request: Request):
    return templates.TemplateResponse("products/index.html", {"request": request})


@router.get("/vista/{product_id}")
async def vista_detalle_producto(product_id: uuid.UUID, request: Request):
    return templates.TemplateResponse("products/detalle.html", {"request": request, "product_id": str(product_id)})


# ─── API JSON ─────────────────────────────────────────────────

@router.get("/", response_model=ProductListOut)
async def listar_productos(
    skip: int = 0,
    limit: int = 50,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(func.count()).select_from(Product).where(
            Product.tenant_id == tenant.id, Product.activo == True
        )
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
    return producto


@router.post("/{product_id}/imagenes", response_model=ProductOut)
async def subir_imagenes(
    product_id: uuid.UUID,
    imagenes: list[UploadFile] = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Sube imágenes al producto y lanza el pipeline de contenido IA."""
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    if len(imagenes) > 10:
        raise HTTPException(status_code=400, detail="Máximo 10 imágenes por producto")

    directorio = os.path.join(MEDIA_ROOT, "productos", str(tenant.id), str(product_id))
    os.makedirs(directorio, exist_ok=True)

    urls_guardadas = list(producto.imagenes_originales or [])

    for img in imagenes:
        contenido = await img.read()
        if len(contenido) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail=f"Imagen {img.filename} supera los 10 MB")

        mime = img.content_type or mimetypes.guess_type(img.filename or "")[0] or "image/jpeg"
        if mime not in ALLOWED_MIME:
            raise HTTPException(status_code=400, detail=f"Formato no soportado: {mime}")

        ext = mimetypes.guess_extension(mime) or ".jpg"
        nombre_archivo = f"{uuid.uuid4().hex}{ext}"
        ruta = os.path.join(directorio, nombre_archivo)

        async with aiofiles.open(ruta, "wb") as f:
            await f.write(contenido)

        # URL pública relativa (el worker la resuelve como ruta de disco)
        url_relativa = f"/media/productos/{tenant.id}/{product_id}/{nombre_archivo}"
        urls_guardadas.append(url_relativa)

    producto.imagenes_originales = urls_guardadas
    await db.commit()
    await db.refresh(producto)

    # Lanzar pipeline con las imágenes ya guardadas
    from app.workers.content_pipeline import generar_contenido_producto
    generar_contenido_producto.delay(str(producto.id), str(tenant.id))

    return producto


@router.get("/{product_id}", response_model=ProductDetailOut)
async def obtener_producto(
    product_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.models.product import ProductContent
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.contenido))
        .where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


@router.patch("/{product_id}", response_model=ProductOut)
async def editar_producto(
    product_id: uuid.UUID,
    data: ProductUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.tenant_id == tenant.id)
    )
    producto = result.scalar_one_or_none()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(producto, field, value)
    await db.commit()
    await db.refresh(producto)
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

    descripcion_html = (
        f"<p>{contenido.descripcion_seo}</p>" if contenido and contenido.descripcion_seo
        else f"<p>{producto.descripcion_input or producto.nombre}</p>"
    )
    if contenido and contenido.bullet_points:
        items_html = "".join(f"<li>{b}</li>" for b in contenido.bullet_points)
        descripcion_html += f"<ul>{items_html}</ul>"

    imagenes = []
    if producto.imagenes_originales:
        imagenes += producto.imagenes_originales
    if contenido and contenido.imagenes_generadas:
        imagenes += contenido.imagenes_generadas
    imagenes = imagenes[:10]

    titulo = contenido.titulo_seo if contenido and contenido.titulo_seo else producto.nombre

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
