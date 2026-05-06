"""Unified repository for all audit-database writes and reads."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from app.clients.audit_db import (
    AuditRun, AuditDomain, AuditOrder, AuditLabelUpdate,
    AuditEmailDraft, AuditLog, ProcessedDomain,
    WordPressRemediationAttempt, WordPressNewspaperSite,
    ensure_wordpress_remediation_tables,
)


# -- runs ---------------------------------------------------------------------

def create_run(session: Session, dry_run: bool) -> AuditRun:
    run = AuditRun(dry_run=dry_run, started_at=datetime.utcnow(), status="running")
    session.add(run)
    session.flush()
    return run


def finish_run(session: Session, run: AuditRun, status: str = "success", summary: dict | None = None) -> None:
    run.finished_at = datetime.utcnow()
    run.status = status
    if summary:
        run.summary_json = summary


# -- domains ------------------------------------------------------------------

def log_domain(session: Session, run_id: int, **kwargs) -> AuditDomain:
    row = AuditDomain(run_id=run_id, **kwargs)
    session.add(row)
    return row


# -- orders -------------------------------------------------------------------

def log_order(session: Session, run_id: int, **kwargs) -> AuditOrder:
    row = AuditOrder(run_id=run_id, **kwargs)
    session.add(row)
    return row


# -- label updates ------------------------------------------------------------

def log_label_update(session: Session, run_id: int, **kwargs) -> AuditLabelUpdate:
    row = AuditLabelUpdate(run_id=run_id, **kwargs)
    session.add(row)
    return row


# -- email drafts -------------------------------------------------------------

def log_email_draft(session: Session, run_id: int, **kwargs) -> AuditEmailDraft:
    row = AuditEmailDraft(run_id=run_id, **kwargs)
    session.add(row)
    return row


# -- logs ---------------------------------------------------------------------

def log_entry(session: Session, run_id: int | None, level: str, message: str, context: dict | None = None) -> AuditLog:
    row = AuditLog(run_id=run_id, level=level, message=message, context_json=context)
    session.add(row)
    return row


# -- queries (for dashboard) --------------------------------------------------

def get_recent_runs(session: Session, limit: int = 50) -> list[AuditRun]:
    return session.query(AuditRun).order_by(AuditRun.id.desc()).limit(limit).all()


def get_run_by_id(session: Session, run_id: int) -> AuditRun | None:
    return session.query(AuditRun).filter(AuditRun.id == run_id).first()


def get_domains_for_run(session: Session, run_id: int) -> list[AuditDomain]:
    return session.query(AuditDomain).filter(AuditDomain.run_id == run_id).all()


def get_orders_for_run(session: Session, run_id: int) -> list[AuditOrder]:
    return session.query(AuditOrder).filter(AuditOrder.run_id == run_id).all()


def get_drafts_for_run(session: Session, run_id: int) -> list[AuditEmailDraft]:
    return session.query(AuditEmailDraft).filter(AuditEmailDraft.run_id == run_id).all()


def get_draft_by_id(session: Session, draft_id: int) -> AuditEmailDraft | None:
    return session.query(AuditEmailDraft).filter(AuditEmailDraft.id == draft_id).first()


def get_logs_for_run(session: Session, run_id: int) -> list[AuditLog]:
    return session.query(AuditLog).filter(AuditLog.run_id == run_id).order_by(AuditLog.id).all()


def get_label_updates_for_run(session: Session, run_id: int) -> list[AuditLabelUpdate]:
    return session.query(AuditLabelUpdate).filter(AuditLabelUpdate.run_id == run_id).all()


def search_domains(session: Session, query: str, limit: int = 200) -> list[AuditDomain]:
    return (
        session.query(AuditDomain)
        .filter(AuditDomain.normalized_domain.contains(query))
        .order_by(AuditDomain.id.desc())
        .limit(limit)
        .all()
    )


def search_orders(session: Session, query: str, limit: int = 200) -> list[AuditOrder]:
    return (
        session.query(AuditOrder)
        .filter(AuditOrder.wp_domain.contains(query))
        .order_by(AuditOrder.id.desc())
        .limit(limit)
        .all()
    )


def get_all_drafts(session: Session, limit: int = 200) -> list[AuditEmailDraft]:
    return session.query(AuditEmailDraft).order_by(AuditEmailDraft.id.desc()).limit(limit).all()


def get_all_logs(session: Session, level: str | None = None, limit: int = 500) -> list[AuditLog]:
    q = session.query(AuditLog)
    if level:
        q = q.filter(AuditLog.level == level)
    return q.order_by(AuditLog.id.desc()).limit(limit).all()


# -- processed domains -------------------------------------------------------

def get_all_processed_domains(session: Session) -> set[str]:
    """Return set of normalized domains that were already fully processed."""
    rows = session.query(ProcessedDomain.normalized_domain).all()
    return {r[0] for r in rows}


def mark_domain_processed(
    session: Session,
    normalized_domain: str,
    full_domain: str,
    extension: str,
    external_status: str,
    account_name: str,
    run_id: int,
    actions_taken: str,
) -> None:
    existing = (
        session.query(ProcessedDomain)
        .filter(ProcessedDomain.normalized_domain == normalized_domain)
        .first()
    )
    if existing:
        existing.external_status = external_status
        existing.run_id = run_id
        existing.actions_taken = actions_taken
        existing.processed_at = datetime.utcnow()
    else:
        session.add(ProcessedDomain(
            normalized_domain=normalized_domain,
            full_domain=full_domain,
            extension=extension,
            external_status=external_status,
            account_name=account_name,
            run_id=run_id,
            actions_taken=actions_taken,
        ))


def get_processed_domains_list(session: Session, limit: int = 500) -> list[ProcessedDomain]:
    return session.query(ProcessedDomain).order_by(ProcessedDomain.id.desc()).limit(limit).all()


def remove_processed_domain(session: Session, normalized_domain: str) -> bool:
    """Remove a domain from the processed list (e.g. if it was renewed)."""
    count = (
        session.query(ProcessedDomain)
        .filter(ProcessedDomain.normalized_domain == normalized_domain)
        .delete()
    )
    return count > 0


# -- WordPress remediation ----------------------------------------------------

def get_wordpress_remediation_attempts(
    session: Session,
    status: str | None = None,
    limit: int = 500,
) -> list[WordPressRemediationAttempt]:
    ensure_wordpress_remediation_tables(session)
    q = session.query(WordPressRemediationAttempt)
    if status:
        q = q.filter(WordPressRemediationAttempt.result_status == status)
    return q.order_by(WordPressRemediationAttempt.id.desc()).limit(limit).all()


def get_wordpress_newspaper_sites(session: Session, limit: int = 500) -> list[WordPressNewspaperSite]:
    ensure_wordpress_remediation_tables(session)
    return session.query(WordPressNewspaperSite).order_by(WordPressNewspaperSite.id.desc()).limit(limit).all()
