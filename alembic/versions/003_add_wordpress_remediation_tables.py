"""Add WordPress remediation audit tables

Revision ID: 003
Revises: 002
Create Date: 2026-05-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wordpress_remediation_attempts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("source_db", sa.String(100)),
        sa.Column("openorder_id", sa.Integer),
        sa.Column("domain_id", sa.Integer, nullable=True),
        sa.Column("wp_domain", sa.String(255)),
        sa.Column("old_status", sa.String(50)),
        sa.Column("result_status", sa.String(80)),
        sa.Column("result_message", sa.Text, nullable=True),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("plugin_present", sa.Boolean, server_default=sa.text("0")),
        sa.Column("plugin_removed", sa.Boolean, server_default=sa.text("0")),
        sa.Column("plugin_was_active", sa.Boolean, nullable=True),
        sa.Column("newspaper_theme", sa.Boolean, server_default=sa.text("0")),
        sa.Column("theme_name", sa.String(255)),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_wp_remediation_run", "wordpress_remediation_attempts", ["run_id"])
    op.create_index("ix_wp_remediation_status", "wordpress_remediation_attempts", ["result_status"])
    op.create_index("ix_wp_remediation_domain", "wordpress_remediation_attempts", ["wp_domain"])

    op.create_table(
        "wordpress_newspaper_sites",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("source_db", sa.String(100)),
        sa.Column("openorder_id", sa.Integer),
        sa.Column("domain_id", sa.Integer, nullable=True),
        sa.Column("wp_domain", sa.String(255)),
        sa.Column("theme_name", sa.String(255)),
        sa.Column("detected_at", sa.DateTime),
    )
    op.create_index("ix_wp_newspaper_domain", "wordpress_newspaper_sites", ["wp_domain"])
    op.create_index("ix_wp_newspaper_run", "wordpress_newspaper_sites", ["run_id"])


def downgrade() -> None:
    op.drop_table("wordpress_newspaper_sites")
    op.drop_table("wordpress_remediation_attempts")
