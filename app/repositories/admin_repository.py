from __future__ import annotations
from sqlalchemy.orm import Session
from app.clients.source_db import Admin


def get_admin_by_id(session: Session, admin_id: int) -> Admin | None:
    return session.query(Admin).filter(Admin.id == admin_id).first()


def get_admins_by_ids(session: Session, admin_ids: list[int]) -> dict[int, Admin]:
    if not admin_ids:
        return {}
    admins = session.query(Admin).filter(Admin.id.in_(admin_ids)).all()
    return {a.id: a for a in admins}
