from __future__ import annotations
from sqlalchemy.orm import Session
from app.clients.source_db import DomLabel


def get_domain_ids_with_label(session: Session, label_id: int) -> set[int]:
    """Return all domId values that have the given labelId."""
    rows = session.query(DomLabel.domId).filter(DomLabel.labelId == label_id).all()
    return {r[0] for r in rows}


def get_labels_for_domain(session: Session, dom_id: int) -> list[DomLabel]:
    return session.query(DomLabel).filter(DomLabel.domId == dom_id).all()


def update_label(session: Session, dom_id: int, new_label_id: int) -> list[dict]:
    """Update all domlabels for dom_id, return list of change dicts."""
    labels = get_labels_for_domain(session, dom_id)
    changes: list[dict] = []
    for lbl in labels:
        old = lbl.labelId
        if old != new_label_id:
            lbl.labelId = new_label_id
            changes.append({"domlabel_id": lbl.id, "dom_id": dom_id, "old": old, "new": new_label_id})
    return changes
