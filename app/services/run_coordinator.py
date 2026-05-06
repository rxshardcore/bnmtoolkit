"""Orchestrates the full pipeline: fetch -> match -> label -> orders -> drafts -> delete.

Runs against ALL configured source databases (e.g. linkstatus_blauwemonsters +
linkstatus_brandnewmedia) in a single run.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.clients.audit_db import get_audit_session
from app.clients.hostingindustries import DomainSnapshot, fetch_all_accounts
from app.clients.source_db import get_source_session
from app.config import Settings
from app.repositories import (
    admin_repository,
    audit_repository,
    customer_repository,
    domlabels_repository,
    domains_repository,
    openorders_repository,
)
from app.services.email_draft_service import build_drafts, save_drafts_to_disk
from app.services.mailgun_service import send_email
from app.services.report_service import save_csv_export, save_json_report
from app.services.sheets_service import mark_domains_expired_via_n8n
from app.utils.domain_normalization import normalize_domain

logger = logging.getLogger(__name__)


class RunCoordinator:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_domains(self) -> list[DomainSnapshot]:
        return fetch_all_accounts(
            self.settings.hi_accounts,
            timeout=self.settings.hi_request_timeout,
            max_retries=self.settings.hi_max_retries,
        )

    async def check_domains(self) -> None:
        await self.run_all()

    async def generate_email_drafts(self, run_id: int | None = None) -> None:
        await self.run_all()

    async def cleanup_openorders(self) -> None:
        await self.run_all()

    async def run_all(self) -> None:
        s = self.settings
        audit = get_audit_session(s.audit_db_url)

        run = audit_repository.create_run(audit, dry_run=s.dry_run)
        audit.commit()
        run_id = run.id

        mode = "DRY-RUN" if s.dry_run else "LIVE"
        logger.info("=== Run %d started (%s) ===", run_id, mode)
        audit_repository.log_entry(audit, run_id, "INFO", f"Run started in {mode} mode")

        errors = 0
        warnings = 0
        total_label_changes = 0
        total_deleted = 0
        all_enriched: list[dict[str, Any]] = []
        all_affected_orders_raw: list = []
        all_processed_snapshots: list[DomainSnapshot] = []

        try:
            # ── 1. Fetch external domains from HostingIndustries ─────────
            snapshots = fetch_all_accounts(
                s.hi_accounts, timeout=s.hi_request_timeout, max_retries=s.hi_max_retries
            )
            run.total_domains_fetched = len(snapshots)
            audit.commit()
            logger.info("Fetched %d domains from HostingIndustries", len(snapshots))

            # ── 2. Classify unusable and filter out already-processed ─────
            already_processed = audit_repository.get_all_processed_domains(audit)
            logger.info("Already processed domains in history: %d", len(already_processed))

            all_unusable = [
                snap for snap in snapshots
                if snap.status in s.unusable_statuses_list
            ]

            unusable = [
                snap for snap in all_unusable
                if normalize_domain(snap.full_domain) not in already_processed
            ]
            skipped = len(all_unusable) - len(unusable)

            run.total_unusable_domains = len(all_unusable)
            audit.commit()
            logger.info(
                "Unusable domains: %d total, %d new to process, %d already processed (skipped)",
                len(all_unusable), len(unusable), skipped,
            )
            if skipped > 0:
                audit_repository.log_entry(
                    audit, run_id, "INFO",
                    f"Skipped {skipped} already-processed domains",
                )

            # ── 3. Process each source database ─────────────────────────
            source_dbs = s.source_db_urls
            if not source_dbs:
                logger.error("No source databases configured!")
                audit_repository.log_entry(audit, run_id, "ERROR", "No source databases configured")
                errors += 1

            total_matched = 0

            for db_info in source_dbs:
                db_name = db_info["name"]
                db_url = db_info["url"]
                logger.info("── Processing source database: %s ──", db_name)
                audit_repository.log_entry(audit, run_id, "INFO", f"Processing source DB: {db_name}")

                source = get_source_session(db_url)
                try:
                    # 3a. Build lookup and match
                    domain_lookup = domains_repository.build_domain_lookup(source)
                    matched_pairs: list[tuple[DomainSnapshot, Any]] = []

                    for snap in snapshots:
                        norm = normalize_domain(snap.full_domain)
                        is_unusable = snap.status in s.unusable_statuses_list
                        matched = domain_lookup.get(norm)

                        if matched:
                            audit_repository.log_domain(
                                audit, run_id=run_id,
                                external_domain=snap.full_domain,
                                normalized_domain=norm,
                                extension=snap.extension,
                                external_status=snap.status,
                                is_unusable=is_unusable,
                                matched_domain_id=matched.id,
                                matched_wp_domain=matched.wp_domain,
                                account_name=snap.account_name,
                                action_taken=f"matched:{db_name}" if is_unusable else "none",
                                notes=db_name,
                            )
                            if is_unusable:
                                matched_pairs.append((snap, matched))

                    # 3a2. Detect orphaned domains (in DB but NOT in HostingIndustries)
                    #       Skip domains that carry label 76 (externally managed)
                    hi_normalized = {normalize_domain(snap.full_domain) for snap in snapshots}
                    excluded_label_ids = domlabels_repository.get_domain_ids_with_label(source, 76)
                    orphaned_domains = []
                    for norm_domain, dom in domain_lookup.items():
                        if norm_domain in hi_normalized:
                            continue
                        if norm_domain in already_processed:
                            continue
                        if dom.id in excluded_label_ids:
                            continue
                        orphaned_domains.append(dom)

                    logger.info("  Orphaned domains in %s (in DB, not in HI): %d", db_name, len(orphaned_domains))

                    for dom in orphaned_domains:
                        norm = normalize_domain(dom.wp_domain) if dom.wp_domain else ""
                        audit_repository.log_domain(
                            audit, run_id=run_id,
                            external_domain=dom.wp_domain or "",
                            normalized_domain=norm,
                            extension="",
                            external_status="not_in_hostingindustries",
                            is_unusable=True,
                            matched_domain_id=dom.id,
                            matched_wp_domain=dom.wp_domain,
                            account_name="orphaned",
                            action_taken=f"orphaned:{db_name}",
                            notes=f"Domain {dom.id} exists in {db_name} but not found in any HostingIndustries account",
                        )
                        matched_pairs.append((
                            DomainSnapshot(
                                domain_name=dom.wp_domain or "",
                                extension="",
                                full_domain=dom.wp_domain or "",
                                status="not_in_hostingindustries",
                                account_key="orphaned",
                                account_name="orphaned",
                            ),
                            dom,
                        ))

                    total_matched += len(matched_pairs)
                    all_processed_snapshots.extend([snap for snap, _ in matched_pairs])
                    logger.info("  Total to process in %s: %d (unusable: %d, orphaned: %d)",
                                db_name, len(matched_pairs),
                                len(matched_pairs) - len(orphaned_domains), len(orphaned_domains))

                    # 3b. Update labels
                    for snap, dom in matched_pairs:
                        if s.dry_run:
                            audit_repository.log_entry(
                                audit, run_id, "INFO",
                                f"[DRY-RUN] Would update label for domain {dom.id} ({dom.wp_domain}) in {db_name}"
                            )
                        else:
                            changes = domlabels_repository.update_label(source, dom.id, s.expired_label_id)
                            for ch in changes:
                                audit_repository.log_label_update(
                                    audit, run_id=run_id,
                                    domlabel_id=ch["domlabel_id"], dom_id=ch["dom_id"],
                                    old_label_id=ch["old"], new_label_id=ch["new"],
                                )
                                total_label_changes += 1
                            source.commit()

                    # 3c. Find affected orders
                    matched_domain_ids = [dom.id for _, dom in matched_pairs]
                    affected_orders = openorders_repository.get_affected_orders(
                        source, matched_domain_ids, s.affected_statuses_list
                    )
                    all_affected_orders_raw.extend(
                        [(o, db_name, source) for o in affected_orders]
                    )
                    logger.info("  Affected orders in %s: %d", db_name, len(affected_orders))

                    # 3d. Enrich orders
                    admin_ids = list({o.addedBy for o in affected_orders if o.addedBy})
                    customer_ids = list({o.customerId for o in affected_orders if o.customerId})
                    admins = admin_repository.get_admins_by_ids(source, admin_ids)
                    customers = customer_repository.get_customers_by_ids(source, customer_ids)
                    wp_by_id = {dom.id: dom.wp_domain for _, dom in matched_pairs}

                    for o in affected_orders:
                        adm = admins.get(o.addedBy)
                        cust = customers.get(o.customerId)
                        row = {
                            "order_id": o.id,
                            "added_on": o.addedOn or "",
                            "delivery_date": o.deliveryDate or "",
                            "wp_domain": wp_by_id.get(o.domainId, ""),
                            "customer_name": cust.name if cust else "",
                            "customer_id": o.customerId,
                            "added_by": o.addedBy or 0,
                            "addedby_name": adm.Name if adm else "",
                            "addedby_email": adm.email if adm else "",
                            "anchor1": o.anchor1 or "",
                            "anchor2": o.anchor2 or "",
                            "anchor3": o.anchor3 or "",
                            "link1": o.link1 or "",
                            "link2": o.link2 or "",
                            "link3": o.link3 or "",
                            "order_status": o.status or "",
                            "domain_id": o.domainId,
                            "source_db": db_name,
                        }
                        all_enriched.append(row)

                        audit_repository.log_order(
                            audit, run_id=run_id,
                            openorder_id=o.id, domain_id=o.domainId,
                            wp_domain=row["wp_domain"],
                            customer_id=o.customerId, customer_name=row["customer_name"],
                            added_by=o.addedBy,
                            addedby_name=row["addedby_name"], addedby_email=row["addedby_email"],
                            order_status=o.status or "",
                            added_on=row["added_on"], delivery_date=row["delivery_date"],
                            anchor1=row["anchor1"], anchor2=row["anchor2"], anchor3=row["anchor3"],
                            link1=row["link1"], link2=row["link2"], link3=row["link3"],
                            action_taken=f"pending_delete:{db_name}" if not s.dry_run else f"dry_run:{db_name}",
                        )

                    audit.commit()

                except Exception as exc:
                    logger.error("Error processing %s: %s", db_name, exc)
                    audit_repository.log_entry(audit, run_id, "ERROR", f"DB {db_name}: {exc}")
                    errors += 1
                    source.rollback()
                finally:
                    source.close()

            # Also log unmatched unusable domains (not found in any source DB)
            for snap in unusable:
                norm = normalize_domain(snap.full_domain)
                # Check if already logged (we only logged matched ones above)
                # Log unmatched with matched_domain_id=None
                audit_repository.log_domain(
                    audit, run_id=run_id,
                    external_domain=snap.full_domain,
                    normalized_domain=norm,
                    extension=snap.extension,
                    external_status=snap.status,
                    is_unusable=True,
                    matched_domain_id=None,
                    matched_wp_domain=None,
                    account_name=snap.account_name,
                    action_taken="unmatched",
                    notes="Not found in any source DB",
                )
            audit.commit()

            run.total_matched_domains = total_matched
            run.total_updated_labels = total_label_changes
            run.total_affected_orders = len(all_enriched)
            audit.commit()

            # ── 4. Generate email drafts (only for databases with send_emails=True)
            email_dbs = {d["name"] for d in source_dbs if d.get("send_emails", True)}
            email_orders = [o for o in all_enriched if o.get("source_db") in email_dbs]
            no_email_orders = [o for o in all_enriched if o.get("source_db") not in email_dbs]

            if no_email_orders:
                no_email_dbs = {o["source_db"] for o in no_email_orders}
                logger.info(
                    "Skipping email drafts for %d orders from %s (send_emails=false)",
                    len(no_email_orders), ", ".join(no_email_dbs),
                )
                audit_repository.log_entry(
                    audit, run_id, "INFO",
                    f"No emails for {len(no_email_orders)} orders from {', '.join(no_email_dbs)} (labels + orders only)",
                )

            drafts = build_drafts(email_orders, dry_run=s.dry_run)
            save_drafts_to_disk(drafts, s.output_dir, run_id)
            run.total_email_drafts = len(drafts)

            for d in drafts:
                audit_repository.log_email_draft(
                    audit, run_id=run_id,
                    added_by=d.added_by, addedby_name=d.admin_name,
                    addedby_email=d.admin_email, subject=d.subject,
                    body_html=d.body_html, body_json=d.body_json,
                    order_count=d.order_count, send_status="draft",
                )
            audit.commit()

            # ── 5. Optionally send via Mailgun ───────────────────────────
            if s.enable_email_send and s.mailgun_api_key:
                for d in drafts:
                    if not d.admin_email:
                        continue
                    try:
                        send_email(
                            api_key=s.mailgun_api_key, domain=s.mailgun_domain,
                            from_addr=s.mailgun_from, to_addr=d.admin_email,
                            subject=d.subject, html_body=d.body_html,
                            api_url=s.mailgun_api_url,
                        )
                    except Exception as exc:
                        logger.error("Mailgun send failed for %s: %s", d.admin_email, exc)
                        errors += 1

            # ── 6. Optionally sync to Google Sheets via n8n ──────────────
            if s.enable_sheets_sync and s.n8n_sheets_webhook_url:
                try:
                    sheets_data = [
                        {
                            "full_domain": snap.full_domain,
                            "extension": snap.extension,
                            "status": snap.status,
                            "end_date": getattr(snap, "end_date", ""),
                            "account_name": snap.account_name,
                        }
                        for snap in all_processed_snapshots
                    ]
                    sheets_result = mark_domains_expired_via_n8n(
                        s.n8n_sheets_webhook_url, sheets_data, dry_run=s.dry_run
                    )
                    audit_repository.log_entry(audit, run_id, "INFO", f"Sheets sync: {sheets_result}")
                    audit.commit()
                except Exception as exc:
                    logger.error("Sheets sync failed (non-fatal): %s", exc)
                    audit_repository.log_entry(audit, run_id, "WARNING", f"Sheets sync error: {exc}")
                    audit.commit()
                    warnings += 1

            # ── 7. Delete open orders (per source DB) ────────────────────
            for db_info in source_dbs:
                db_name = db_info["name"]
                domain_ids_for_db = [
                    row["domain_id"] for row in all_enriched
                    if row.get("source_db") == db_name
                ]
                domain_ids_for_db = list(set(domain_ids_for_db))
                if not domain_ids_for_db:
                    continue

                order_count = len([r for r in all_enriched if r.get("source_db") == db_name])
                if s.dry_run:
                    logger.info("[DRY-RUN] Would delete %d orders from %s", order_count, db_name)
                else:
                    source = get_source_session(db_info["url"])
                    try:
                        deleted = openorders_repository.delete_orders_by_domain_and_status(
                            source, domain_ids_for_db, s.affected_statuses_list
                        )
                        source.commit()
                        total_deleted += deleted
                        logger.info("Deleted %d orders from %s", deleted, db_name)
                    finally:
                        source.close()

            run.total_deleted_orders = total_deleted
            audit.commit()

            # ── 8. Mark processed domains (ONLY on live runs) ──────────
            if not s.dry_run:
                for snap in all_processed_snapshots:
                    norm = normalize_domain(snap.full_domain)
                    actions = ["label_updated"]
                    if len(all_enriched) > 0:
                        actions.append("orders_deleted")
                    if s.enable_sheets_sync:
                        actions.append("sheets_synced")
                    if s.enable_email_send:
                        actions.append("emails_sent")

                    audit_repository.mark_domain_processed(
                        audit,
                        normalized_domain=norm,
                        full_domain=snap.full_domain,
                        extension=snap.extension,
                        external_status=snap.status,
                        account_name=snap.account_name,
                        run_id=run_id,
                        actions_taken=",".join(actions),
                    )
                audit.commit()
                logger.info("Marked %d domains as processed", len(all_processed_snapshots))
            else:
                logger.info("[DRY-RUN] Would mark %d domains as processed (skipped)", len(unusable))

            # ── 9. Generate report ───────────────────────────────────────
            summary = {
                "run_id": run_id,
                "mode": mode,
                "total_domains_fetched": len(snapshots),
                "total_unusable_domains": len(unusable),
                "total_matched_domains": total_matched,
                "total_updated_labels": total_label_changes,
                "total_affected_orders": len(all_enriched),
                "total_email_drafts": len(drafts),
                "total_deleted_orders": total_deleted,
                "source_databases": [d["name"] for d in source_dbs],
                "errors": errors,
                "warnings": warnings,
            }
            save_json_report(summary, s.output_dir, run_id)
            save_csv_export(all_enriched, s.output_dir, run_id, "affected_orders")

            audit_repository.finish_run(audit, run, status="success", summary=summary)
            run.error_count = errors
            run.warning_count = warnings
            audit.commit()
            logger.info("=== Run %d finished successfully ===", run_id)

        except Exception as exc:
            logger.exception("Run %d failed: %s", run_id, exc)
            audit_repository.log_entry(audit, run_id, "ERROR", str(exc))
            audit_repository.finish_run(audit, run, status="failed")
            run.error_count = errors + 1
            audit.commit()
            raise
        finally:
            audit.close()
