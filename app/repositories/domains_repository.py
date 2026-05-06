from __future__ import annotations
from sqlalchemy.orm import Session
from app.clients.source_db import Domain
from app.utils.domain_normalization import normalize_domain


def get_all_domains(session: Session) -> list[Domain]:
    return session.query(Domain).all()


def build_domain_lookup(session: Session) -> dict[str, Domain]:
    """Return {normalized_wp_domain: Domain} for fast matching."""
    lookup: dict[str, Domain] = {}
    for d in get_all_domains(session):
        if d.wp_domain:
            key = normalize_domain(d.wp_domain)
            lookup[key] = d
    return lookup
