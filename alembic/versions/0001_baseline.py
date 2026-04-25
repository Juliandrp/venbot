"""baseline — esquema inicial creado por create_all

Revision ID: 0001
Revises:
Create Date: 2026-04-25

Esta migración es un no-op. El esquema inicial se crea con
SQLAlchemy `Base.metadata.create_all` desde `app/db_init.py` cuando
la BD está vacía. A partir de aquí, las migraciones siguientes
deben usar `alembic revision --autogenerate -m "descripción"`.
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
