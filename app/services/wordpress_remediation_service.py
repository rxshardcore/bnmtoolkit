"""Remediate failed-domain orders by removing a legacy WordPress plugin."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from sqlalchemy import bindparam, text

from app.clients.source_db import get_source_session
from app.config import Settings
from app.repositories import audit_repository
from app.services.wordpress_client import WordPressCheckResult, WordPressClient
from app.services.wordpress_credentials_service import (
    CredentialSchema,
    CredentialSchemaError,
    discover_wordpress_credentials_schema,
    get_wordpress_credentials,
)
from app.utils.linkstatus_crypto import PasswordDecryptionError, decrypt_linkstatus_password
from app.utils.domain_normalization import normalize_domain

logger = logging.getLogger(__name__)


def _status_clause(statuses: list[str]) -> str:
    return " OR ".join(f"oo.status LIKE :status_{idx}" for idx, _ in enumerate(statuses))


def get_wordpress_remediation_orders(source_session, statuses: list[str]) -> list[dict[str, Any]]:
    if not statuses:
        return []

    params = {f"status_{idx}": f"%{status}%" for idx, status in enumerate(statuses)}
    result = source_session.execute(text(f"""
        SELECT
            oo.id AS order_id,
            oo.domainId,
            d.wp_domain,
            oo.status,
            GROUP_CONCAT(DISTINCT dl.labelId ORDER BY dl.labelId SEPARATOR ',') AS label_ids
        FROM openorder oo
        LEFT JOIN domains d ON oo.domainId = d.id
        LEFT JOIN domlabels dl ON dl.domId = d.id
        WHERE {_status_clause(statuses)}
        GROUP BY oo.id, oo.domainId, d.wp_domain, oo.status
        ORDER BY oo.id
    """), params)

    orders: list[dict[str, Any]] = []
    for row in result.fetchall():
        label_ids = {
            int(value)
            for value in str(row[4] or "").split(",")
            if value.strip().isdigit()
        }
        orders.append({
            "order_id": int(row[0]),
            "domainId": row[1],
            "wp_domain": row[2] or "",
            "status": row[3] or "",
            "label_ids": label_ids,
        })
    return orders


def group_orders_by_website(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse remediation candidates to one attempt per website."""
    grouped: dict[str, dict[str, Any]] = {}
    for order in orders:
        key = normalize_domain(order.get("wp_domain", ""))
        if not key:
            key = f"domain-id:{order.get('domainId') or order['order_id']}"

        group = grouped.setdefault(
            key,
            {
                **order,
                "order_ids": [],
                "statuses": set(),
                "label_ids": set(),
            },
        )
        group["order_ids"].append(order["order_id"])
        group["statuses"].add(order.get("status", ""))
        group["label_ids"].update(order.get("label_ids", set()))

    result = []
    for group in grouped.values():
        statuses = sorted(s for s in group["statuses"] if s)
        group["status"] = ", ".join(statuses)
        group["order_count"] = len(group["order_ids"])
        result.append(group)
    return result


def _record_attempt(audit_session, run_id: int, db_name: str, order: dict[str, Any], result: WordPressCheckResult) -> None:
    from app.clients.audit_db import WordPressRemediationAttempt, WordPressNewspaperSite

    attempt = WordPressRemediationAttempt(
        run_id=run_id,
        source_db=db_name,
        openorder_id=order["order_id"],
        domain_id=order.get("domainId"),
        wp_domain=order.get("wp_domain", ""),
        old_status=order.get("status", ""),
        result_status=result.status,
        result_message=_result_message_with_order_count(result.message, order),
        http_status=result.http_status,
        plugin_present=result.plugin_present,
        plugin_removed=result.plugin_removed,
        plugin_was_active=result.plugin_was_active,
        newspaper_theme=result.newspaper_theme,
        theme_name=result.theme_name,
        created_at=datetime.utcnow(),
    )
    audit_session.add(attempt)

    if result.newspaper_theme:
        audit_session.add(WordPressNewspaperSite(
            run_id=run_id,
            source_db=db_name,
            openorder_id=order["order_id"],
            domain_id=order.get("domainId"),
            wp_domain=order.get("wp_domain", ""),
            theme_name=result.theme_name or "Newspaper",
            detected_at=datetime.utcnow(),
        ))


def _result_message_with_order_count(message: str, order: dict[str, Any]) -> str:
    count = int(order.get("order_count") or 1)
    if count <= 1:
        return message
    suffix = f"{count} orders op deze website"
    return f"{message} ({suffix})" if message else suffix


def _static_result(status: str, message: str = "", **kwargs) -> WordPressCheckResult:
    return WordPressCheckResult(status=status, message=message, **kwargs)


def classify_label_preflight(label_ids: set[int], jg_label_id: int, expired_label_id: int) -> str | None:
    """Return a preflight result status for labels that should not use WP login."""
    if jg_label_id in label_ids:
        return "skipped_jg_label"
    if expired_label_id in label_ids:
        return "deleted_label79"
    return None


def run_wordpress_remediation(settings: Settings) -> dict[str, Any]:
    """Run WordPress remediation across configured source databases."""
    from app.clients.audit_db import get_audit_session, ensure_wordpress_remediation_tables

    audit = get_audit_session(settings.audit_db_url)
    ensure_wordpress_remediation_tables(audit)
    run = audit_repository.create_run(audit, dry_run=settings.dry_run)
    audit.commit()
    run_id = run.id

    totals = {
        "checked": 0,
        "deleted_label79": 0,
        "skipped_jg": 0,
        "pending": 0,
        "login_invalid": 0,
        "site_errors": 0,
        "newspaper": 0,
        "errors": 0,
    }

    mode = "DRY-RUN" if settings.dry_run else "LIVE"
    audit_repository.log_entry(audit, run_id, "INFO", f"WordPress remediation started in {mode} mode")

    if not settings.wp_remediation_enabled:
        audit_repository.log_entry(audit, run_id, "INFO", "WordPress remediation is disabled")
        run.status = "success"
        run.summary_json = totals
        run.finished_at = datetime.utcnow()
        audit.commit()
        audit.close()
        return totals

    source_dbs = settings.source_db_urls
    if not source_dbs:
        audit_repository.log_entry(audit, run_id, "ERROR", "No source databases configured")
        run.status = "failed"
        audit.commit()
        audit.close()
        return totals

    credential_schema: CredentialSchema | None = None
    credential_source = get_source_session(source_dbs[0]["url"])
    try:
        credential_schema = discover_wordpress_credentials_schema(credential_source)
    except CredentialSchemaError as exc:
        audit_repository.log_entry(audit, run_id, "ERROR", str(exc))
        totals["errors"] += 1
    finally:
        credential_source.close()

    client = WordPressClient(
        timeout_seconds=settings.wp_request_timeout,
        headless=settings.wp_remediation_headless,
        plugin_name=settings.wp_plugin_name,
        newspaper_theme_name=settings.wp_newspaper_theme_name,
    )

    try:
        for db_info in source_dbs:
            db_name = db_info["name"]
            source = get_source_session(db_info["url"])
            credential_source = get_source_session(source_dbs[0]["url"])
            try:
                orders = group_orders_by_website(
                    get_wordpress_remediation_orders(source, settings.wp_failed_statuses_list)
                )
                logger.info("[%s] WordPress remediation candidate websites: %d", db_name, len(orders))

                for order in orders:
                    totals["checked"] += 1
                    label_ids = order.get("label_ids", set())

                    preflight_status = classify_label_preflight(
                        label_ids,
                        settings.jg_label_id,
                        settings.expired_label_id,
                    )

                    if preflight_status == "skipped_jg_label":
                        totals["skipped_jg"] += 1
                        result = _static_result("skipped_jg_label", f"Skipped label {settings.jg_label_id}")
                        _record_attempt(audit, run_id, db_name, order, result)
                        continue

                    if preflight_status == "deleted_label79":
                        if not settings.dry_run:
                            source.execute(
                                text("DELETE FROM openorder WHERE id IN :order_ids").bindparams(
                                    bindparam("order_ids", expanding=True, value=order["order_ids"])
                                )
                            )
                            source.commit()
                        totals["deleted_label79"] += len(order["order_ids"])
                        result = _static_result("deleted_label79", f"Order removed because domain has label {settings.expired_label_id}")
                        _record_attempt(audit, run_id, db_name, order, result)
                        continue

                    if not credential_schema:
                        result = _static_result("credential_schema_missing", "Credential schema was not discovered")
                        _record_attempt(audit, run_id, db_name, order, result)
                        totals["errors"] += 1
                        continue

                    credentials = get_wordpress_credentials(
                        credential_source,
                        order["wp_domain"],
                        schema=credential_schema,
                    )
                    if not credentials:
                        result = _static_result("missing_credentials", "No WordPress credentials found")
                        _record_attempt(audit, run_id, db_name, order, result)
                        continue

                    try:
                        decrypted = decrypt_linkstatus_password(
                            credentials.encrypted_password,
                            settings.linkstatus_decryption_key,
                        )
                        password = decrypted.value
                    except PasswordDecryptionError as exc:
                        result = _static_result("credential_decryption_failed", str(exc))
                        _record_attempt(audit, run_id, db_name, order, result)
                        totals["errors"] += 1
                        continue

                    result = client.remediate(
                        domain=order["wp_domain"],
                        username=credentials.username,
                        password=password,
                        dry_run=settings.dry_run,
                    )

                    if result.status in {"site_404", "site_500", "site_unreachable"}:
                        totals["site_errors"] += 1
                    if result.status == "login_invalid":
                        totals["login_invalid"] += 1
                    if result.newspaper_theme:
                        totals["newspaper"] += 1

                    if result.plugin_removed and not settings.dry_run:
                        source.execute(
                            text("UPDATE openorder SET status = 'pending' WHERE id IN :order_ids").bindparams(
                                bindparam("order_ids", expanding=True, value=order["order_ids"])
                            ),
                        )
                        source.commit()
                        totals["pending"] += len(order["order_ids"])

                    _record_attempt(audit, run_id, db_name, order, result)
                    audit.commit()
            except Exception as exc:
                source.rollback()
                totals["errors"] += 1
                logger.exception("[%s] WordPress remediation failed", db_name)
                audit_repository.log_entry(audit, run_id, "ERROR", f"[{db_name}] WordPress remediation failed: {exc}")
            finally:
                source.close()
                credential_source.close()

        run.total_affected_orders = totals["checked"]
        run.total_deleted_orders = totals["deleted_label79"]
        run.summary_json = totals
        run.error_count = totals["errors"]
        run.warning_count = totals["login_invalid"] + totals["site_errors"]
        run.status = "failed" if totals["errors"] else "success"
        run.finished_at = datetime.utcnow()
        audit_repository.log_entry(audit, run_id, "INFO", f"WordPress remediation finished: {totals}")
        audit.commit()
        return totals
    finally:
        audit.close()
