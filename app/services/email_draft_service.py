"""Generate grouped HTML email drafts per responsible admin (addedBy)."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


@dataclass
class OrderRow:
    order_id: int
    added_on: str
    delivery_date: str
    wp_domain: str
    customer_name: str
    order_status: str
    anchor1: str
    anchor2: str
    anchor3: str
    link1: str
    link2: str
    link3: str


@dataclass
class EmailDraft:
    added_by: int
    admin_name: str
    admin_email: str
    subject: str
    body_html: str
    body_json: list[dict]
    order_count: int


def build_drafts(
    enriched_orders: list[dict[str, Any]],
    dry_run: bool = True,
) -> list[EmailDraft]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
    )
    template = env.get_template("expired_domain_orders_email.html")

    grouped: dict[int, list[dict]] = defaultdict(list)
    admin_info: dict[int, dict] = {}
    for o in enriched_orders:
        key = o["added_by"]
        grouped[key].append(o)
        if key not in admin_info:
            admin_info[key] = {"name": o["addedby_name"], "email": o["addedby_email"]}

    drafts: list[EmailDraft] = []
    for admin_id, orders in grouped.items():
        info = admin_info[admin_id]
        rows = [
            OrderRow(
                order_id=o["order_id"],
                added_on=o.get("added_on", ""),
                delivery_date=o.get("delivery_date", ""),
                wp_domain=o.get("wp_domain", ""),
                customer_name=o.get("customer_name", ""),
                order_status=o.get("order_status", ""),
                anchor1=o.get("anchor1", ""),
                anchor2=o.get("anchor2", ""),
                anchor3=o.get("anchor3", ""),
                link1=o.get("link1", ""),
                link2=o.get("link2", ""),
                link3=o.get("link3", ""),
            )
            for o in orders
        ]

        subject = f"Actie nodig: {len(rows)} order(s) op verlopen of niet-bestaande domeinen"
        html = template.render(
            admin_name=info["name"] or "Team",
            orders=rows,
            dry_run=dry_run,
        )
        body_json = [
            {
                "order_id": r.order_id,
                "wp_domain": r.wp_domain,
                "customer_name": r.customer_name,
                "order_status": r.order_status,
            }
            for r in rows
        ]

        drafts.append(
            EmailDraft(
                added_by=admin_id,
                admin_name=info["name"] or "",
                admin_email=info["email"] or "",
                subject=subject,
                body_html=html,
                body_json=body_json,
                order_count=len(rows),
            )
        )

    logger.info("Generated %d email drafts for %d admins", len(drafts), len(grouped))
    return drafts


def save_drafts_to_disk(drafts: list[EmailDraft], output_dir: Path, run_id: int) -> None:
    draft_dir = output_dir / "email_drafts" / f"run_{run_id}"
    draft_dir.mkdir(parents=True, exist_ok=True)
    for d in drafts:
        safe_name = d.admin_email.replace("@", "_at_").replace(".", "_")
        html_path = draft_dir / f"{safe_name}.html"
        json_path = draft_dir / f"{safe_name}.json"
        html_path.write_text(d.body_html, encoding="utf-8")
        json_path.write_text(json.dumps(d.body_json, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d drafts to %s", len(drafts), draft_dir)
