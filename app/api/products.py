import uuid
import os
import mimetypes
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.core.deps import get_current_tenant
from app.models.tenant import Tenant
from app.models.product import Product
from app.models.product import ProductContent
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
        .options(selectinload(Product.contenido))
        .order_by(Product.created_at.desc())
        .offset(skip).limit(limit)
    )
    items = result.scalars().all()

    # Serializar con pipeline_paso incluido
    items_out = []
    for p in items:
        d = ProductOut.model_validate(p).model_dump()
        d["pipeline_paso"] = p.contenido.pipeline_paso if p.contenido else 0
        items_out.append(d)
    return {"total": total, "items": items_out}


@router.post("/", response_model=ProductOut, status_code=201)
async def crear_producto(
    data: ProductCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    from app.services.plan_limits import verificar_puede_crear_producto
    await verificar_puede_crear_producto(tenant, db)

    producto = Product(tenant_id=tenant.id, **data.model_dump())
    db.add(producto)
    await db.commit()
    await db.refresh(producto)
    return producto


# ─── Importación desde Dropi ──────────────────────────────────

@router.get("/dropi/disponibles")
async def listar_productos_dropi(
    page: int = 1,
    limit: int = 30,
    search: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista productos disponibles en el catálogo Dropi del tenant."""
    from app.models.tenant import TenantConfig
    from app.services.dropi_service import DropiService
    from app.core.security import decrypt_secret

    config_q = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = config_q.scalar_one_or_none()
    if not config or not config.dropi_api_key_enc or not config.dropi_store_id:
        raise HTTPException(status_code=400, detail="Configura primero las credenciales de Dropi en Configuración")

    dropi_key = decrypt_secret(config.dropi_api_key_enc)
    dropi = DropiService(dropi_key, config.dropi_store_id)
    try:
        data = await dropi.listar_productos(page=page, limit=limit, search=search)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dropi rechazó la consulta: {str(e)[:200]}")

    # Marcar cuáles ya están importados
    ids_dropi = [item["id"] for item in data["items"] if item["id"]]
    if ids_dropi:
        existentes_q = await db.execute(
            select(Product.dropi_product_id).where(
                Product.tenant_id == tenant.id,
                Product.dropi_product_id.in_(ids_dropi),
            )
        )
        ya_importados = {row[0] for row in existentes_q.all()}
        for item in data["items"]:
            item["ya_importado"] = item["id"] in ya_importados

    return data


@router.post("/dropi/importar", status_code=201)
async def importar_productos_dropi(
    payload: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Importa productos desde Dropi. Body: {"dropi_ids": ["1","2","3"]}.
    Crea cada uno como Product (skip si ya existe). Opcionalmente lanza
    pipeline IA si payload incluye {"generar_contenido": true}.
    """
    from app.models.tenant import TenantConfig
    from app.services.dropi_service import DropiService
    from app.services.plan_limits import verificar_puede_crear_producto
    from app.core.security import decrypt_secret

    dropi_ids = payload.get("dropi_ids") or []
    generar_contenido = bool(payload.get("generar_contenido", True))
    if not dropi_ids:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un dropi_id en 'dropi_ids'")

    config_q = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = config_q.scalar_one_or_none()
    if not config or not config.dropi_api_key_enc or not config.dropi_store_id:
        raise HTTPException(status_code=400, detail="Configura primero las credenciales de Dropi")

    dropi_key = decrypt_secret(config.dropi_api_key_enc)
    dropi = DropiService(dropi_key, config.dropi_store_id)

    importados = []
    saltados = []
    errores = []

    for did in dropi_ids:
        # Skip si ya existe
        existente_q = await db.execute(
            select(Product).where(
                Product.tenant_id == tenant.id,
                Product.dropi_product_id == str(did),
            )
        )
        if existente_q.scalar_one_or_none():
            saltados.append({"dropi_id": did, "razon": "ya importado"})
            continue

        # Verificar plan limit (uno por uno; falla suave)
        try:
            await verificar_puede_crear_producto(tenant, db)
        except HTTPException as e:
            errores.append({"dropi_id": did, "razon": e.detail})
            break  # No tiene sentido seguir si no hay cupo

        # Traer detalle de Dropi
        det = await dropi.obtener_producto(str(did))
        if not det:
            errores.append({"dropi_id": did, "razon": "no encontrado en Dropi"})
            continue

        # Crear el producto
        producto = Product(
            tenant_id=tenant.id,
            nombre=det["nombre"],
            descripcion_input=det["descripcion"] or None,
            precio=det["precio"] or None,
            precio_comparacion=det.get("precio_comparacion"),
            inventario=det.get("inventario") or 0,
            imagenes_originales=det.get("imagenes") or None,
            dropi_product_id=det["id"],
        )
        db.add(producto)
        await db.commit()
        await db.refresh(producto)

        # Lanzar pipeline IA si lo pidieron
        if generar_contenido:
            from app.workers.content_pipeline import generar_contenido_producto as gen_task
            gen_task.delay(str(producto.id), str(tenant.id))

        importados.append({"dropi_id": did, "venbot_id": str(producto.id), "nombre": producto.nombre})

    return {
        "importados": len(importados),
        "saltados": len(saltados),
        "errores": len(errores),
        "detalle": {
            "importados": importados,
            "saltados": saltados,
            "errores": errores,
        },
    }


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

    from app.services.storage import storage
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
        key = f"productos/{tenant.id}/{product_id}/{nombre_archivo}"
        url = await storage.guardar_bytes(key, contenido, mime)
        urls_guardadas.append(url)

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
