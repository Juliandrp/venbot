"""dropi_product_id en products (para evitar duplicados al importar)

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("dropi_product_id", sa.String(100), nullable=True))
    op.create_index("ix_products_dropi_product_id", "products", ["dropi_product_id"])


def downgrade() -> None:
    op.drop_index("ix_products_dropi_product_id", table_name="products")
    with op.batch_alter_table("products") as batch:
        batch.drop_column("dropi_product_id")
