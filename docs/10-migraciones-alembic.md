# 10 — Migraciones Alembic

## Por qué

Cuando cambias un modelo SQLAlchemy (agregas columna, renombras tabla, etc.), necesitas que la BD de **producción** refleje ese cambio sin perder datos. Alembic genera y aplica esos cambios.

`Base.metadata.create_all` solo crea tablas que no existen. **No agrega columnas a tablas existentes**. Por eso necesitamos Alembic.

## Estado actual

```
alembic/versions/
  ├── 0001_baseline.py        ← marca el schema inicial (no-op)
  ├── 0002_higgsfield_key.py  ← agregó higgsfield_api_key_enc
  └── 0003_modelos_ai.py      ← agregó claude/gemini/openai/kling_model
```

`db_init.py` define `LATEST_REVISION = "0003"` — sincroniza con el último archivo cuando crees uno nuevo.

## Cómo agregar una migración

Cuando modificas un modelo (ejemplo: agregas `precio_oferta` a `Product`):

### 1. Editar el modelo

```python
# app/models/product.py
class Product(Base):
    ...
    precio_oferta: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
```

### 2. Generar migración con autogenerate

```bash
docker compose exec app alembic revision --autogenerate -m "agregar precio_oferta a productos"
```

Esto crea `alembic/versions/0004_<timestamp>_agregar_precio_oferta_a_productos.py`.

**Renómbralo** (opcional, para que sea consistente):
```bash
mv alembic/versions/0004_<timestamp>_*.py alembic/versions/0004_precio_oferta.py
```

### 3. Revisar el archivo generado

```python
# alembic/versions/0004_precio_oferta.py
revision = "0004"
down_revision = "0003"  # ← debe apuntar al anterior

def upgrade():
    op.add_column('products', sa.Column('precio_oferta', sa.Numeric(12, 2), nullable=True))

def downgrade():
    op.drop_column('products', 'precio_oferta')
```

**Siempre revisa que autogenerate no agregue cosas raras** (ej. drops accidentales, tipos cambiados sin querer). Edita manualmente si hace falta.

### 4. Actualizar `LATEST_REVISION`

```python
# app/db_init.py
LATEST_REVISION = "0004"
```

### 5. Probar local

```bash
docker compose exec app alembic upgrade head
docker compose exec postgres psql -U venbot -d venbot_db -c "\d products"
```

Verifica que la columna esté.

### 6. Commit + push

```bash
git add alembic/versions/0004_precio_oferta.py app/models/product.py app/db_init.py
git commit -m "feat: agregar precio_oferta a productos"
git push
```

Coolify hace deploy. El `start.sh` corre `alembic upgrade head` automáticamente. La columna aparece en producción.

## Cómo se inicializa una BD nueva

`app/db_init.py` se llama en el `lifespan` de FastAPI:

```python
async def init_database():
    if alembic_version no existe:
        # BD virgen
        await Base.metadata.create_all()
        INSERT INTO alembic_version VALUES ('0003')
    else:
        # BD ya versionada
        # (las migraciones reales corren en start.sh ANTES)
        log "BD versionada en X"
```

Por qué insertamos manualmente en `alembic_version` en vez de usar `command.stamp()`:
`stamp` dispara el `env.py` de Alembic que llama `asyncio.run()`, lo cual choca con el event loop de uvicorn y produce un crash silencioso del container.

## env.py — config de Alembic

```python
# alembic/env.py
db_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
```

Lee el URL async (asyncpg). Usa `async_engine_from_config` con `NullPool`.

```python
target_metadata = Base.metadata
import app.models  # registra todos los modelos
```

`autogenerate` compara `Base.metadata` (lo que dicen los modelos) vs el schema real de la BD y genera el diff.

## Comandos útiles

```bash
# Ver estado actual
alembic current

# Ver historial completo
alembic history

# Generar migración nueva (autogenerate)
alembic revision --autogenerate -m "descripción"

# Aplicar todas las pendientes
alembic upgrade head

# Aplicar solo una hacia adelante
alembic upgrade +1

# Revertir una hacia atrás
alembic downgrade -1

# Revertir hasta una específica
alembic downgrade 0001

# SQL preview sin ejecutar
alembic upgrade head --sql
```

## Cuándo NO usar autogenerate

Autogenerate es bueno para cambios simples (add column, drop column). **Falla o genera mal** en estos casos:

- Renombrar columna (autogenerate ve drop+add → pierdes datos)
- Cambio de tipo con conversión (ej. text → int con cast)
- Cambios en enums
- Constraints complejos
- Triggers, funciones, vistas

Para esos casos, **escribe la migración a mano**:

```python
def upgrade():
    op.alter_column('products', 'precio',
                    type_=sa.Numeric(14, 2),
                    existing_type=sa.Numeric(12, 2))

def downgrade():
    op.alter_column('products', 'precio',
                    type_=sa.Numeric(12, 2),
                    existing_type=sa.Numeric(14, 2))
```

O incluso SQL crudo si es necesario:

```python
def upgrade():
    op.execute("UPDATE products SET precio = precio * 1.19 WHERE pais='CO'")
```

## Tabla `alembic_version`

```sql
CREATE TABLE alembic_version (
  version_num VARCHAR(32) PRIMARY KEY
);
```

Una sola fila. Apunta al último revision aplicado. **No la edites manual** salvo que sepas exactamente lo que haces.

Si la BD se desincroniza (ej. agregaste columna a mano sin migración):

```bash
# Opción 1: forzar versión (asume que el schema ya coincide)
alembic stamp 0003

# Opción 2: bajar versión y reaplicar
alembic downgrade base
alembic upgrade head
```

## Reset total de BD (solo desarrollo)

```bash
docker exec venbot-postgres psql -U venbot -d venbot_db -c \
  "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# Reiniciar app — init_database() recreará todo
docker restart <container>
```

**NUNCA en producción.**

## Checklist antes de cada migración

- [ ] El modelo SQLAlchemy refleja el cambio deseado
- [ ] `down_revision` apunta a la última revision (no a `None` salvo que sea baseline)
- [ ] `upgrade()` NO contiene drops inesperados
- [ ] `downgrade()` está implementado y es coherente
- [ ] Probaste local: `alembic upgrade head` y `alembic downgrade -1`
- [ ] Actualizaste `LATEST_REVISION` en `db_init.py`
- [ ] Commit incluye: archivo de migración + cambios al modelo + `db_init.py`
