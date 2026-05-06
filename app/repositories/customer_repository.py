from __future__ import annotations
from sqlalchemy.orm import Session
from app.clients.source_db import Customer


def get_customer_by_id(session: Session, customer_id: int) -> Customer | None:
    return session.query(Customer).filter(Customer.id == customer_id).first()


def get_customers_by_ids(session: Session, customer_ids: list[int]) -> dict[int, Customer]:
    if not customer_ids:
        return {}
    customers = session.query(Customer).filter(Customer.id.in_(customer_ids)).all()
    return {c.id: c for c in customers}
