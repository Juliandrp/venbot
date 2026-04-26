"""columnas para modelos AI (claude/gemini/openai/kling)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenant_configs") as batch:
        batch.add_column(sa.Column("claude_model", sa.String(50), nullable=False, server_default="claude-sonnet-4-6"))
        batch.add_column(sa.Column("gemini_model", sa.String(50), nullable=False, server_default="gemini-2.5-flash"))
        batch.add_column(sa.Column("openai_model", sa.String(50), nullable=False, server_default="gpt-4o-mini"))
        batch.add_column(sa.Column("kling_model", sa.String(50), nullable=False, server_default="kling-v1-6"))


def downgrade() -> None:
    with op.batch_alter_table("tenant_configs") as batch:
        batch.drop_column("claude_model")
        batch.drop_column("gemini_model")
        batch.drop_column("openai_model")
        batch.drop_column("kling_model")
