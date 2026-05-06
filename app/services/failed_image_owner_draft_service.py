"""Generate supplier-facing email drafts for failed_image orders."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories import customer_repository
from app.services.failed_reset_service import DEFAULT_SUPPLIER_EMAIL, RUBEN_EMAIL, SUPPLIER_ROUTING

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FailedImageDraft:
    recipient_name: str
    recipient_email: str
    subject: str
    body_html: str
    body_json: dict[str, Any]
    order_count: int


def get_failed_image_orders(source_session: Session, db_name: str) -> list[dict[str, Any]]:
    """Fetch current failed_image orders from one source database."""
    result = source_session.execute(text("""
        SELECT
            oo.id AS order_id,
            oo.domainId,
            d.wp_domain,
            oo.status,
            oo.addedOn,
            oo.deliveryDate,
            oo.addedBy,
            oo.customerId,
            oo.anchor1,
            oo.anchor2,
            oo.anchor3,
            oo.link1,
            oo.link2,
            oo.link3,
            GROUP_CONCAT(DISTINCT dl.labelId ORDER BY dl.labelId SEPARATOR ', ') AS label_ids,
            GROUP_CONCAT(DISTINCT l.name ORDER BY l.name SEPARATOR ', ') AS label_names
        FROM openorder oo
        LEFT JOIN domains d ON oo.domainId = d.id
        LEFT JOIN domlabels dl ON dl.domId = d.id
        LEFT JOIN labels l ON l.id = dl.labelId
        WHERE oo.status LIKE '%failed_image%'
        GROUP BY
            oo.id, oo.domainId, d.wp_domain, oo.status, oo.addedOn, oo.deliveryDate,
            oo.addedBy, oo.customerId, oo.anchor1, oo.anchor2, oo.anchor3,
            oo.link1, oo.link2, oo.link3
        ORDER BY oo.addedBy, d.wp_domain, oo.id
    """))

    rows: list[dict[str, Any]] = []
    for row in result.fetchall():
        rows.append({
            "db": db_name,
            "order_id": row[0],
            "domainId": row[1],
            "wp_domain": row[2] or "",
            "status": row[3] or "",
            "added_on": str(row[4] or ""),
            "delivery_date": str(row[5] or ""),
            "added_by": row[6] or 0,
            "customer_id": row[7] or 0,
            "anchor1": row[8] or "",
            "anchor2": row[9] or "",
            "anchor3": row[10] or "",
            "link1": row[11] or "",
            "link2": row[12] or "",
            "link3": row[13] or "",
            "label_ids": row[14] or "",
            "label_names": row[15] or "",
        })
    return rows


def enrich_failed_image_orders(source_session: Session, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add customer data to failed_image rows."""
    customer_ids = sorted({o["customer_id"] for o in orders if o.get("customer_id")})
    customers = customer_repository.get_customers_by_ids(source_session, customer_ids)

    enriched: list[dict[str, Any]] = []
    for order in orders:
        customer = customers.get(order.get("customer_id"))
        enriched.append({
            **order,
            "customer_name": customer.name if customer else "",
        })
    return enriched


def build_failed_image_owner_drafts(orders: list[dict[str, Any]]) -> list[FailedImageDraft]:
    """Build one draft per supplier: JG labels to Hugo, all others to Stefan."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for order in orders:
        grouped[_resolve_supplier_email(order.get("label_names", ""))].append(order)

    drafts: list[FailedImageDraft] = []
    for supplier_email, supplier_orders in grouped.items():
        recipient_name = "Hugo" if "hugo" in supplier_email.lower() else "Stefan"
        subject = f"Failed image: {len(supplier_orders)} linkbuilding order(s)"
        body_html = build_failed_image_owner_html(recipient_name, supplier_orders)
        drafts.append(FailedImageDraft(
            recipient_name=recipient_name,
            recipient_email=supplier_email,
            subject=subject,
            body_html=body_html,
            body_json={
                "type": "failed_image_supplier_draft",
                "cc": RUBEN_EMAIL,
                "reply_to": RUBEN_EMAIL,
                "orders": [
                    {
                        "db": o.get("db", ""),
                        "order_id": o.get("order_id"),
                        "wp_domain": o.get("wp_domain", ""),
                        "customer_name": o.get("customer_name", ""),
                        "status": o.get("status", ""),
                        "label_names": o.get("label_names", ""),
                    }
                    for o in supplier_orders
                ],
            },
            order_count=len(supplier_orders),
        ))

    return sorted(drafts, key=lambda draft: draft.recipient_email.lower())


def _resolve_supplier_email(label_names: str) -> str:
    for label_key, email in SUPPLIER_ROUTING.items():
        if label_key.lower() in (label_names or "").lower():
            return email
    return DEFAULT_SUPPLIER_EMAIL


def build_failed_image_owner_html(recipient_name: str, orders: list[dict[str, Any]]) -> str:
    rows_html = ""
    for order in orders:
        rows_html += (
            "<tr>"
            f"<td>{order.get('order_id', '')}</td>"
            f"<td>{order.get('wp_domain', '')}</td>"
            f"<td>{order.get('customer_name', '')}</td>"
            f"<td>{order.get('added_on', '')}</td>"
            f"<td>{order.get('delivery_date', '')}</td>"
            f"<td>{order.get('anchor1', '')}</td>"
            f"<td>{order.get('link1', '')}</td>"
            f"<td>{order.get('db', '')}</td>"
            f"<td>{order.get('label_names', '')}</td>"
            "</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: Arial, sans-serif; font-size: 14px; color: #333; line-height: 1.6; }}
table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; font-size: 13px; }}
th {{ background: #f5f5f5; font-weight: 600; }}
</style></head><body>
<p>Hi {recipient_name},</p>

<p>Onderstaande linkbuilding-orders staan momenteel op <code>failed_image</code>.
Wil je controleren waarom de afbeelding niet geplaatst kan worden?</p>

<table>
<thead><tr><th>Order</th><th>Website</th><th>Klant</th><th>Aangemaakt</th><th>Opleverdatum</th><th>Anchor</th><th>Link</th><th>Database</th><th>Labels</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>

<p>Alvast bedankt!</p>

<p>Met vriendelijke groet,<br>
Ruben van Melsen<br>
Blauwe Monsters</p>
</body></html>"""


def save_failed_image_owner_drafts(
    audit_session: Session,
    drafts: list[FailedImageDraft],
    run_id: int | None = None,
) -> list[int]:
    from app.clients.audit_db import AuditEmailDraft

    draft_ids: list[int] = []
    for draft in drafts:
        row = AuditEmailDraft(
            run_id=run_id or 0,
            added_by=0,
            addedby_name=draft.recipient_name,
            addedby_email=draft.recipient_email,
            subject=draft.subject,
            body_html=draft.body_html,
            body_json=draft.body_json,
            order_count=draft.order_count,
            created_at=datetime.utcnow(),
            send_status="draft",
        )
        audit_session.add(row)
        audit_session.flush()
        draft_ids.append(row.id)

    audit_session.commit()
    return draft_ids
