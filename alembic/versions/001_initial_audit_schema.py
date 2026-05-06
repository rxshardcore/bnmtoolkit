"""Initial audit schema

Revision ID: 001
Revises: None
Create Date: 2026-04-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("dry_run", sa.Boolean, server_default=sa.text("1")),
        sa.Column("total_domains_fetched", sa.Integer, server_default="0"),
        sa.Column("total_unusable_domains", sa.Integer, server_default="0"),
        sa.Column("total_matched_domains", sa.Integer, server_default="0"),
        sa.Column("total_updated_labels", sa.Integer, server_default="0"),
        sa.Column("total_affected_orders", sa.Integer, server_default="0"),
        sa.Column("total_deleted_orders", sa.Integer, server_default="0"),
        sa.Column("total_email_drafts", sa.Integer, server_default="0"),
        sa.Column("summary_json", sa.JSON, nullable=True),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("warning_count", sa.Integer, server_default="0"),
    )

    op.create_table(
        "audit_domains",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("external_domain", sa.String(255)),
        sa.Column("normalized_domain", sa.String(255)),
        sa.Column("extension", sa.String(20)),
        sa.Column("external_status", sa.String(50)),
        sa.Column("is_unusable", sa.Boolean, server_default=sa.text("0")),
        sa.Column("matched_domain_id", sa.Integer, nullable=True),
        sa.Column("matched_wp_domain", sa.String(255), nullable=True),
        sa.Column("account_name", sa.String(50), server_default=""),
        sa.Column("action_taken", sa.String(100), server_default="none"),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("ix_audit_domains_run", "audit_domains", ["run_id"])
    op.create_index("ix_audit_domains_normalized", "audit_domains", ["normalized_domain"])

    op.create_table(
        "audit_orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("openorder_id", sa.Integer),
        sa.Column("domain_id", sa.Integer, nullable=True),
        sa.Column("wp_domain", sa.String(255)),
        sa.Column("customer_id", sa.Integer, nullable=True),
        sa.Column("customer_name", sa.String(255)),
        sa.Column("added_by", sa.Integer, nullable=True),
        sa.Column("addedby_name", sa.String(255)),
        sa.Column("addedby_email", sa.String(255)),
        sa.Column("order_status", sa.String(50)),
        sa.Column("added_on", sa.String(255)),
        sa.Column("delivery_date", sa.String(255)),
        sa.Column("anchor1", sa.String(255)),
        sa.Column("anchor2", sa.String(255)),
        sa.Column("anchor3", sa.String(255)),
        sa.Column("link1", sa.String(500)),
        sa.Column("link2", sa.String(500)),
        sa.Column("link3", sa.String(500)),
        sa.Column("action_taken", sa.String(100), server_default="none"),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_audit_orders_run", "audit_orders", ["run_id"])
    op.create_index("ix_audit_orders_openorder", "audit_orders", ["openorder_id"])

    op.create_table(
        "audit_label_updates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("domlabel_id", sa.Integer),
        sa.Column("dom_id", sa.Integer),
        sa.Column("old_label_id", sa.Integer, nullable=True),
        sa.Column("new_label_id", sa.Integer),
        sa.Column("updated_at", sa.DateTime),
    )

    op.create_table(
        "audit_email_drafts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("added_by", sa.Integer, nullable=True),
        sa.Column("addedby_name", sa.String(255)),
        sa.Column("addedby_email", sa.String(255)),
        sa.Column("subject", sa.String(500)),
        sa.Column("body_html", sa.Text),
        sa.Column("body_json", sa.JSON, nullable=True),
        sa.Column("order_count", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("send_status", sa.String(30), server_default="draft"),
        sa.Column("sent_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_audit_drafts_run", "audit_email_drafts", ["run_id"])
    op.create_index("ix_audit_drafts_recipient", "audit_email_drafts", ["addedby_email"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=True),
        sa.Column("level", sa.String(20)),
        sa.Column("message", sa.Text),
        sa.Column("context_json", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("ix_audit_logs_run", "audit_logs", ["run_id"])
    op.create_index("ix_audit_logs_level", "audit_logs", ["level"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("audit_email_drafts")
    op.drop_table("audit_label_updates")
    op.drop_table("audit_orders")
    op.drop_table("audit_domains")
    op.drop_table("audit_runs")
