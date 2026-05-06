"""CLI entrypoint: python -m app.main <command>"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime

from app.config import get_settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="domain-cleanup",
        description="Domain cleanup automation for expired/quarantined domains",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("fetch-domains", help="Fetch domain list from HostingIndustries")
    sub.add_parser("check-domains", help="Check and classify domain statuses")

    gen = sub.add_parser("generate-email-drafts", help="Generate email drafts for affected orders")
    gen.add_argument("--run-id", type=int, default=None)

    sub.add_parser("cleanup-openorders", help="Delete affected open orders (respects DRY_RUN)")

    run_all = sub.add_parser("run-all", help="Execute full pipeline")
    run_all.add_argument("--dry-run", action="store_true", default=None)
    run_all.add_argument("--no-dry-run", dest="dry_run", action="store_false")

    reset = sub.add_parser("reset-failed", help="Reset failed orders to pending in external DBs")
    reset.add_argument("--dry-run", action="store_true", default=None)
    reset.add_argument("--no-dry-run", dest="dry_run", action="store_false")

    wp = sub.add_parser("remediate-wordpress-failed", help="Remove legacy WP plugin for failed-domain orders")
    wp.add_argument("--dry-run", action="store_true", default=None)
    wp.add_argument("--no-dry-run", dest="dry_run", action="store_false")

    sub.add_parser("draft-failed-images", help="Create owner email drafts for failed_image orders")

    sub.add_parser("dashboard", help="Start the dashboard web server")

    return p


def _run_dashboard(settings) -> None:
    import uvicorn

    from app.dashboard.app import create_app

    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.dashboard_port, log_level="info")


def _run_pipeline(settings, command: str, args: argparse.Namespace) -> None:
    from app.services.run_coordinator import RunCoordinator

    coordinator = RunCoordinator(settings)

    if command == "fetch-domains":
        result = asyncio.run(coordinator.fetch_domains())
        logger.info("Fetched %d domains", len(result))
    elif command == "check-domains":
        asyncio.run(coordinator.check_domains())
    elif command == "generate-email-drafts":
        asyncio.run(coordinator.generate_email_drafts(run_id=args.run_id))
    elif command == "cleanup-openorders":
        asyncio.run(coordinator.cleanup_openorders())
    elif command == "run-all":
        asyncio.run(coordinator.run_all())
    elif command == "reset-failed":
        _run_reset_failed(settings)
    elif command == "remediate-wordpress-failed":
        _run_wordpress_remediation(settings)
    elif command == "draft-failed-images":
        _run_failed_image_owner_drafts(settings)


def _run_reset_failed(settings) -> None:
    from app.clients.audit_db import get_audit_session, RepeatOffenderBatch
    from app.clients.source_db import get_source_session
    from app.services.failed_reset_service import (
        reset_failed_to_pending,
        build_supplier_drafts,
        save_supplier_drafts_to_audit,
        send_replace_threshold_report,
        deduplicate_by_domain,
    )

    audit = get_audit_session(settings.audit_db_url)
    all_results = []

    for db_info in settings.source_db_urls:
        source = get_source_session(db_info["url"])
        try:
            result = reset_failed_to_pending(
                source_session=source,
                audit_session=audit,
                db_name=db_info["name"],
                dry_run=settings.dry_run,
            )
            all_results.append(result)
            logger.info(
                "Reset result for %s: %d failed, %d deleted, %d reset, %d supplier drafts, %d replace-notify",
                db_info["name"],
                result["total_failed"],
                result.get("deleted", 0),
                result.get("reset", 0) or result.get("would_reset", 0),
                len(result.get("supplier_draft_orders", [])),
                len(result.get("replace_notify_orders", [])),
            )
        finally:
            source.close()

    # Save repeat offender batch for dashboard reset functionality
    all_supplier_orders = []
    total_deleted = 0
    for r in all_results:
        all_supplier_orders.extend(r.get("supplier_draft_orders", []))
        total_deleted += r.get("deleted", 0)

    if all_supplier_orders:
        deduped = deduplicate_by_domain(all_supplier_orders)
        batch = RepeatOffenderBatch(
            created_at=datetime.utcnow(),
            total_orders=len(all_supplier_orders),
            unique_domains=len(deduped),
            deleted_orders=total_deleted,
            orders_json=[
                {"order_id": o["order_id"], "db": o["db"], "domainId": o.get("domainId"),
                 "wp_domain": o.get("wp_domain", ""), "status": o["status"]}
                for o in all_supplier_orders
            ],
            status="active",
        )
        audit.add(batch)
        audit.commit()
        logger.info("Repeat offender batch #%d saved (%d orders, %d domains)", batch.id, len(all_supplier_orders), len(deduped))

    supplier_drafts = build_supplier_drafts(all_results)
    if supplier_drafts:
        draft_ids = save_supplier_drafts_to_audit(audit, supplier_drafts, output_dir=settings.output_dir)
        logger.info("Saved %d supplier email drafts (IDs: %s) — review on dashboard", len(draft_ids), draft_ids)
    else:
        logger.info("No supplier drafts needed")

    send_replace_threshold_report(settings, all_results)

    audit.close()


def _run_wordpress_remediation(settings) -> None:
    from app.services.wordpress_remediation_service import run_wordpress_remediation

    result = run_wordpress_remediation(settings)
    logger.info("WordPress remediation result: %s", result)


def _run_failed_image_owner_drafts(settings) -> None:
    from app.clients.audit_db import get_audit_session
    from app.clients.source_db import get_source_session
    from app.repositories import audit_repository
    from app.services.failed_image_owner_draft_service import (
        build_failed_image_owner_drafts,
        enrich_failed_image_orders,
        get_failed_image_orders,
        save_failed_image_owner_drafts,
    )

    audit = get_audit_session(settings.audit_db_url)
    run = audit_repository.create_run(audit, dry_run=settings.dry_run)
    audit.commit()

    all_orders = []
    try:
        for db_info in settings.source_db_urls:
            source = get_source_session(db_info["url"])
            try:
                rows = get_failed_image_orders(source, db_info["name"])
                all_orders.extend(enrich_failed_image_orders(source, rows))
                logger.info("[%s] failed_image orders found: %d", db_info["name"], len(rows))
            finally:
                source.close()

        drafts = build_failed_image_owner_drafts(all_orders)
        draft_ids = save_failed_image_owner_drafts(
            audit,
            drafts,
            run_id=run.id,
            output_dir=settings.output_dir,
        )

        run.total_affected_orders = len(all_orders)
        run.total_email_drafts = len(draft_ids)
        run.summary_json = {
            "type": "failed_image_owner_drafts",
            "orders": len(all_orders),
            "drafts": len(draft_ids),
            "draft_ids": draft_ids,
        }
        audit_repository.finish_run(audit, run, status="success", summary=run.summary_json)
        audit.commit()
        logger.info("Saved %d failed_image owner drafts for %d orders", len(draft_ids), len(all_orders))
    except Exception:
        audit.rollback()
        run.status = "failed"
        audit.commit()
        raise
    finally:
        audit.close()


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    settings = get_settings()

    if args.command in ("run-all", "reset-failed", "remediate-wordpress-failed") and args.dry_run is not None:
        settings.dry_run = args.dry_run

    setup_logging(settings.log_level)

    mode = "DRY-RUN" if settings.dry_run else "LIVE"
    logger.info("Domain Cleanup — command=%s  mode=%s", args.command, mode)

    if args.command == "dashboard":
        _run_dashboard(settings)
    else:
        _run_pipeline(settings, args.command, args)


if __name__ == "__main__":
    main()
