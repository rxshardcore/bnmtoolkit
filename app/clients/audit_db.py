"""SQLAlchemy models for the local audit / logging database."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Index, JSON,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class AuditBase(DeclarativeBase):
    pass


class AuditRun(AuditBase):
    __tablename__ = "audit_runs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")
    dry_run = Column(Boolean, default=True)
    total_domains_fetched = Column(Integer, default=0)
    total_unusable_domains = Column(Integer, default=0)
    total_matched_domains = Column(Integer, default=0)
    total_updated_labels = Column(Integer, default=0)
    total_affected_orders = Column(Integer, default=0)
    total_deleted_orders = Column(Integer, default=0)
    total_email_drafts = Column(Integer, default=0)
    summary_json = Column(JSON, nullable=True)
    error_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)


class AuditDomain(AuditBase):
    __tablename__ = "audit_domains"
    __table_args__ = (
        Index("ix_audit_domains_run", "run_id"),
        Index("ix_audit_domains_normalized", "normalized_domain"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    external_domain = Column(String(255))
    normalized_domain = Column(String(255))
    extension = Column(String(20))
    external_status = Column(String(50))
    is_unusable = Column(Boolean, default=False)
    matched_domain_id = Column(Integer, nullable=True)
    matched_wp_domain = Column(String(255), nullable=True)
    account_name = Column(String(50), default="")
    action_taken = Column(String(100), default="none")
    notes = Column(Text, nullable=True)


class AuditOrder(AuditBase):
    __tablename__ = "audit_orders"
    __table_args__ = (
        Index("ix_audit_orders_run", "run_id"),
        Index("ix_audit_orders_openorder", "openorder_id"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    openorder_id = Column(Integer)
    domain_id = Column(Integer, nullable=True)
    wp_domain = Column(String(255))
    customer_id = Column(Integer, nullable=True)
    customer_name = Column(String(255))
    added_by = Column(Integer, nullable=True)
    addedby_name = Column(String(255))
    addedby_email = Column(String(255))
    order_status = Column(String(50))
    added_on = Column(String(255))
    delivery_date = Column(String(255))
    anchor1 = Column(String(255))
    anchor2 = Column(String(255))
    anchor3 = Column(String(255))
    link1 = Column(String(500))
    link2 = Column(String(500))
    link3 = Column(String(500))
    action_taken = Column(String(100), default="none")
    deleted_at = Column(DateTime, nullable=True)


class AuditLabelUpdate(AuditBase):
    __tablename__ = "audit_label_updates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    domlabel_id = Column(Integer)
    dom_id = Column(Integer)
    old_label_id = Column(Integer, nullable=True)
    new_label_id = Column(Integer)
    updated_at = Column(DateTime, default=datetime.utcnow)


class AuditEmailDraft(AuditBase):
    __tablename__ = "audit_email_drafts"
    __table_args__ = (
        Index("ix_audit_drafts_run", "run_id"),
        Index("ix_audit_drafts_recipient", "addedby_email"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=False)
    added_by = Column(Integer, nullable=True)
    addedby_name = Column(String(255))
    addedby_email = Column(String(255))
    subject = Column(String(500))
    body_html = Column(Text)
    body_json = Column(JSON, nullable=True)
    order_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    send_status = Column(String(30), default="draft")
    sent_at = Column(DateTime, nullable=True)


class AuditLog(AuditBase):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_run", "run_id"),
        Index("ix_audit_logs_level", "level"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, nullable=True)
    level = Column(String(20))
    message = Column(Text)
    context_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class RepeatOffenderBatch(AuditBase):
    """Tracks each batch of repeat offenders for dashboard reset functionality."""
    __tablename__ = "repeat_offender_batches"
    __table_args__ = (
        Index("ix_ro_batches_created", "created_at"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_orders = Column(Integer, default=0)
    unique_domains = Column(Integer, default=0)
    deleted_orders = Column(Integer, default=0)
    orders_json = Column(JSON, nullable=True)
    status = Column(String(30), default="active")
    reset_at = Column(DateTime, nullable=True)


class ProcessedDomain(AuditBase):
    """Tracks domains that have been fully processed (label updated, orders cleaned, sheet marked).
    Used to skip already-handled domains on subsequent runs."""
    __tablename__ = "processed_domains"
    __table_args__ = (
        Index("ix_processed_normalized", "normalized_domain", unique=True),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized_domain = Column(String(255), nullable=False, unique=True)
    full_domain = Column(String(255))
    extension = Column(String(20))
    external_status = Column(String(50))
    account_name = Column(String(50))
    processed_at = Column(DateTime, default=datetime.utcnow)
    run_id = Column(Integer, nullable=False)
    actions_taken = Column(String(500))


def get_audit_engine(url: str):
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def get_audit_session(url: str) -> Session:
    engine = get_audit_engine(url)
    factory = sessionmaker(bind=engine)
    return factory()
