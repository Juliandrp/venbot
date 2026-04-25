"""higgsfield_api_key_enc en tenant_configs

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_configs") as batch:
        batch.add_column(sa.Column("higgsfield_api_key_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tenant_configs") as batch:
        batch.drop_column("higgsfield_api_key_enc")
