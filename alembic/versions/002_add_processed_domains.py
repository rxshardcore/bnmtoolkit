"""Add processed_domains table

Revision ID: 002
Revises: 001
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processed_domains",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("normalized_domain", sa.String(255), nullable=False, unique=True),
        sa.Column("full_domain", sa.String(255)),
        sa.Column("extension", sa.String(20)),
        sa.Column("external_status", sa.String(50)),
        sa.Column("account_name", sa.String(50)),
        sa.Column("processed_at", sa.DateTime),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("actions_taken", sa.String(500)),
    )
    op.create_index("ix_processed_normalized", "processed_domains", ["normalized_domain"], unique=True)


def downgrade() -> None:
    op.drop_table("processed_domains")
