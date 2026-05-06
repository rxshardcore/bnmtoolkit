from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
from app.clients.source_db import OpenOrder


def get_affected_orders(
    session: Session, domain_ids: list[int], status_patterns: list[str]
) -> list[OpenOrder]:
    """Find orders matching domain IDs where status LIKE any of the patterns.

    Uses SQL LIKE '%pattern%' so 'failed' matches 'failed_image', 'failed_domain', etc.
    """
    if not domain_ids or not status_patterns:
        return []

    like_clauses = [OpenOrder.status.like(f"%{pat}%") for pat in status_patterns]

    return (
        session.query(OpenOrder)
        .filter(
            and_(
                OpenOrder.domainId.in_(domain_ids),
                or_(*like_clauses),
            )
        )
        .all()
    )


def delete_orders_by_domain_and_status(
    session: Session, domain_ids: list[int], status_patterns: list[str]
) -> int:
    """Delete orders matching domain IDs where status LIKE any of the patterns."""
    if not domain_ids or not status_patterns:
        return 0

    like_clauses = [OpenOrder.status.like(f"%{pat}%") for pat in status_patterns]

    count = (
        session.query(OpenOrder)
        .filter(
            and_(
                OpenOrder.domainId.in_(domain_ids),
                or_(*like_clauses),
            )
        )
        .delete(synchronize_session="fetch")
    )
    return count
