"""Dashboard route registration — all views read from audit DB only."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from fastapi import FastAPI, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.clients.audit_db import get_audit_session
from app.config import Settings
from app.repositories import audit_repository

logger = logging.getLogger(__name__)


def _render(templates: Jinja2Templates, request: Request, name: str, ctx: dict):
    """Starlette 1.0-compatible template rendering."""
    ctx["request"] = request
    return templates.TemplateResponse(request, name, ctx)


def register_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    settings: Settings,
    auth: Callable,
) -> None:

    def _audit():
        return get_audit_session(settings.audit_db_url)

    # -- overview -------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request, user: str = Depends(auth)):
        session = _audit()
        try:
            runs = audit_repository.get_recent_runs(session, limit=30)
            return _render(templates, request, "overview.html", {"runs": runs, "user": user})
        finally:
            session.close()

    # -- run detail -----------------------------------------------------------
    @app.get("/run/{run_id}", response_class=HTMLResponse)
    def run_detail(request: Request, run_id: int, user: str = Depends(auth)):
        session = _audit()
        try:
            run = audit_repository.get_run_by_id(session, run_id)
            domains = audit_repository.get_domains_for_run(session, run_id)
            orders = audit_repository.get_orders_for_run(session, run_id)
            drafts = audit_repository.get_drafts_for_run(session, run_id)
            label_updates = audit_repository.get_label_updates_for_run(session, run_id)
            logs = audit_repository.get_logs_for_run(session, run_id)
            return _render(templates, request, "run_detail.html", {
                "run": run, "domains": domains, "orders": orders,
                "drafts": drafts, "label_updates": label_updates, "logs": logs, "user": user,
            })
        finally:
            session.close()

    # -- domains page ---------------------------------------------------------
    @app.get("/domains", response_class=HTMLResponse)
    def domains_page(request: Request, q: str = Query(""), user: str = Depends(auth)):
        session = _audit()
        try:
            if q:
                domains = audit_repository.search_domains(session, q)
            else:
                domains = audit_repository.search_domains(session, "", limit=200)
            return _render(templates, request, "domains.html", {"domains": domains, "query": q, "user": user})
        finally:
            session.close()

    # -- orders page ----------------------------------------------------------
    @app.get("/orders", response_class=HTMLResponse)
    def orders_page(request: Request, q: str = Query(""), user: str = Depends(auth)):
        session = _audit()
        try:
            if q:
                orders = audit_repository.search_orders(session, q)
            else:
                orders = audit_repository.search_orders(session, "", limit=200)
            return _render(templates, request, "orders.html", {"orders": orders, "query": q, "user": user})
        finally:
            session.close()

    # -- email drafts ---------------------------------------------------------
    @app.get("/drafts", response_class=HTMLResponse)
    def drafts_page(request: Request, user: str = Depends(auth)):
        session = _audit()
        try:
            drafts = audit_repository.get_all_drafts(session)
            return _render(templates, request, "email_drafts.html", {"drafts": drafts, "user": user})
        finally:
            session.close()

    # -- draft preview (raw HTML) ---------------------------------------------
    @app.get("/draft/{draft_id}/preview", response_class=HTMLResponse)
    def draft_preview(draft_id: int, user: str = Depends(auth)):
        session = _audit()
        try:
            draft = audit_repository.get_draft_by_id(session, draft_id)
            if not draft:
                return HTMLResponse("Draft not found", status_code=404)
            return HTMLResponse(draft.body_html)
        finally:
            session.close()

    # -- draft detail page (with send button) ---------------------------------
    @app.get("/draft/{draft_id}", response_class=HTMLResponse)
    def draft_detail(request: Request, draft_id: int, user: str = Depends(auth)):
        session = _audit()
        try:
            draft = audit_repository.get_draft_by_id(session, draft_id)
            if not draft:
                return HTMLResponse("Draft not found", status_code=404)
            return _render(templates, request, "draft_detail.html", {"draft": draft, "user": user})
        finally:
            session.close()

    # -- send a single draft --------------------------------------------------
    @app.post("/draft/{draft_id}/send", response_class=HTMLResponse)
    def send_draft(request: Request, draft_id: int, user: str = Depends(auth)):
        from datetime import datetime
        from app.services.mailgun_service import send_email

        session = _audit()
        try:
            draft = audit_repository.get_draft_by_id(session, draft_id)
            if not draft:
                return HTMLResponse("Draft not found", status_code=404)

            if not draft.addedby_email:
                return _render(templates, request, "draft_detail.html", {
                    "draft": draft, "user": user,
                    "error": "Geen ontvanger email adres gevonden voor deze draft.",
                })

            if not settings.mailgun_api_key:
                return _render(templates, request, "draft_detail.html", {
                    "draft": draft, "user": user,
                    "error": "Mailgun API key is niet geconfigureerd. Vul MAILGUN_API_KEY in .env.",
                })

            meta = draft.body_json if isinstance(draft.body_json, dict) else {}
            cc = meta.get("cc")
            reply_to = meta.get("reply_to")
            xlsx_path = meta.get("xlsx_path", "")

            attachments = []
            if xlsx_path:
                from pathlib import Path
                p = Path(xlsx_path)
                if p.exists():
                    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    attachments.append(("linkbuilding_fouten.xlsx", p.read_bytes(), xlsx_mime))

            try:
                send_email(
                    api_key=settings.mailgun_api_key,
                    domain=settings.mailgun_domain,
                    from_addr=settings.mailgun_from,
                    to_addr=draft.addedby_email,
                    subject=draft.subject,
                    html_body=draft.body_html,
                    api_url=settings.mailgun_api_url,
                    cc=cc,
                    reply_to=reply_to,
                    attachments=attachments or None,
                )
                draft.send_status = "sent"
                draft.sent_at = datetime.utcnow()
                session.commit()
                logger.info("Draft %d sent to %s (cc=%s) by %s", draft_id, draft.addedby_email, cc or "-", user)
            except Exception as exc:
                draft.send_status = "failed"
                session.commit()
                logger.error("Failed to send draft %d: %s", draft_id, exc)
                return _render(templates, request, "draft_detail.html", {
                    "draft": draft, "user": user,
                    "error": f"Verzenden mislukt: {exc}",
                })

            return RedirectResponse(f"/draft/{draft_id}", status_code=303)
        finally:
            session.close()

    # -- processed domains ----------------------------------------------------
    @app.get("/processed", response_class=HTMLResponse)
    def processed_page(request: Request, message: str = Query(""), user: str = Depends(auth)):
        session = _audit()
        try:
            domains = audit_repository.get_processed_domains_list(session, limit=1000)
            return _render(templates, request, "processed.html", {
                "domains": domains, "user": user, "message": message,
            })
        finally:
            session.close()

    @app.post("/processed/{domain}/remove", response_class=HTMLResponse)
    def remove_processed(request: Request, domain: str, user: str = Depends(auth)):
        session = _audit()
        try:
            removed = audit_repository.remove_processed_domain(session, domain)
            session.commit()
            msg = f"'{domain}' verwijderd — wordt bij volgende run opnieuw gecontroleerd." if removed else f"'{domain}' niet gevonden."
            logger.info("Processed domain removed by %s: %s (found=%s)", user, domain, removed)
            return RedirectResponse(f"/processed?message={msg}", status_code=303)
        finally:
            session.close()

    # -- manual domain removal ------------------------------------------------
    @app.get("/manual-remove", response_class=HTMLResponse)
    def manual_remove_page(request: Request, user: str = Depends(auth)):
        return _render(templates, request, "manual_remove.html", {"user": user})

    @app.post("/manual-remove", response_class=HTMLResponse)
    def manual_remove_action(request: Request, domains: str = Form(""), user: str = Depends(auth)):
        from datetime import datetime
        from app.clients.source_db import get_source_session
        from app.repositories import domains_repository, domlabels_repository, openorders_repository
        from app.utils.domain_normalization import normalize_domain

        raw_lines = [ln.strip() for ln in domains.splitlines() if ln.strip()]
        if not raw_lines:
            return _render(templates, request, "manual_remove.html", {
                "user": user, "error": "Geen domeinen ingevoerd.",
            })

        normalized = [normalize_domain(ln) for ln in raw_lines]
        audit = _audit()
        actions: list[dict] = []
        not_found: list[str] = []
        total_labels = 0
        total_deleted = 0

        try:
            for db_info in settings.source_db_urls:
                db_name = db_info["name"]
                source = get_source_session(db_info["url"])
                try:
                    lookup = domains_repository.build_domain_lookup(source)

                    for raw, norm in zip(raw_lines, normalized):
                        dom = lookup.get(norm)
                        if not dom:
                            continue

                        label_changes = domlabels_repository.update_label(
                            source, dom.id, settings.expired_label_id,
                        )
                        total_labels += len(label_changes)

                        deleted = openorders_repository.delete_orders_by_domain_and_status(
                            source, [dom.id], settings.affected_statuses_list,
                        )
                        total_deleted += deleted

                        source.commit()

                        actions.append({
                            "domain": norm,
                            "db": db_name,
                            "domain_id": dom.id,
                            "label_changes": len(label_changes),
                            "deleted_orders": deleted,
                        })

                        audit_repository.log_entry(
                            audit, run_id=None, level="INFO",
                            message=f"[MANUAL] {user} removed domain {dom.id} ({norm}) in {db_name}: "
                                    f"{len(label_changes)} label(s) → 79, {deleted} order(s) deleted",
                        )

                    source.commit()
                finally:
                    source.close()

            matched_norms = {a["domain"] for a in actions}
            not_found = [raw for raw, norm in zip(raw_lines, normalized) if norm not in matched_norms]

            audit.commit()
            logger.info(
                "Manual remove by %s: %d input, %d matched, %d labels, %d orders deleted",
                user, len(raw_lines), len(actions), total_labels, total_deleted,
            )
        finally:
            audit.close()

        return _render(templates, request, "manual_remove.html", {
            "user": user,
            "results": {
                "input_count": len(raw_lines),
                "matched": len(actions),
                "labels_updated": total_labels,
                "orders_deleted": total_deleted,
                "not_found": not_found,
                "actions": actions,
            },
            "prefill": domains,
        })

    # -- repeat offender batches -----------------------------------------------
    @app.get("/repeat-offenders", response_class=HTMLResponse)
    def repeat_offenders_page(request: Request, message: str = Query(""), user: str = Depends(auth)):
        from app.clients.audit_db import RepeatOffenderBatch
        session = _audit()
        try:
            batches = session.query(RepeatOffenderBatch).order_by(RepeatOffenderBatch.id.desc()).limit(50).all()
            return _render(templates, request, "repeat_offenders.html", {
                "batches": batches, "user": user, "message": message,
            })
        finally:
            session.close()

    @app.post("/repeat-offenders/{batch_id}/reset", response_class=HTMLResponse)
    def reset_repeat_offender_batch(request: Request, batch_id: int, user: str = Depends(auth)):
        from datetime import datetime
        from sqlalchemy import text, and_
        from app.clients.audit_db import RepeatOffenderBatch, AuditLog
        from app.clients.source_db import get_source_session

        audit = _audit()
        try:
            batch = audit.query(RepeatOffenderBatch).filter(RepeatOffenderBatch.id == batch_id).first()
            if not batch:
                return RedirectResponse("/repeat-offenders?message=Batch niet gevonden", status_code=303)
            if batch.status == "reset":
                return RedirectResponse("/repeat-offenders?message=Batch is al gereset", status_code=303)

            orders = batch.orders_json or []
            if not orders:
                return RedirectResponse("/repeat-offenders?message=Geen orders in batch", status_code=303)

            orders_by_db: dict[str, list[int]] = {}
            for o in orders:
                orders_by_db.setdefault(o["db"], []).append(o["order_id"])

            total_reset = 0
            for db_info in settings.source_db_urls:
                db_name = db_info["name"]
                ids = orders_by_db.get(db_name, [])
                if not ids:
                    continue
                source = get_source_session(db_info["url"])
                try:
                    placeholders = ",".join([str(i) for i in ids])
                    result = source.execute(text(
                        f"UPDATE openorder SET status = 'pending' WHERE id IN ({placeholders})"
                    ))
                    source.commit()
                    total_reset += result.rowcount
                    logger.info("Batch #%d: reset %d orders in %s", batch_id, result.rowcount, db_name)
                finally:
                    source.close()

            # Clear reset history for these orders so they're treated as first-time
            for o in orders:
                logs = audit.query(AuditLog).filter(
                    and_(
                        AuditLog.level == "INFO",
                        AuditLog.message.like(f"[{o['db']}] Reset order {o['order_id']} %"),
                    )
                ).all()
                for log in logs:
                    audit.delete(log)

            batch.status = "reset"
            batch.reset_at = datetime.utcnow()
            audit.add(AuditLog(
                run_id=None, level="INFO",
                message=f"[MANUAL] {user} reset repeat offender batch #{batch_id}: {total_reset} orders → pending",
                context_json={"batch_id": batch_id, "total_reset": total_reset, "user": user},
                created_at=datetime.utcnow(),
            ))
            audit.commit()

            msg = f"Batch #{batch_id} gereset: {total_reset} orders teruggezet naar pending. Repeat-offender geschiedenis gewist."
            logger.info("Repeat offender batch #%d reset by %s: %d orders", batch_id, user, total_reset)
            return RedirectResponse(f"/repeat-offenders?message={msg}", status_code=303)
        finally:
            audit.close()

    # -- logs -----------------------------------------------------------------
    @app.get("/logs", response_class=HTMLResponse)
    def logs_page(request: Request, level: str = Query(""), user: str = Depends(auth)):
        session = _audit()
        try:
            logs = audit_repository.get_all_logs(session, level=level or None)
            return _render(templates, request, "logs.html", {"logs": logs, "level_filter": level, "user": user})
        finally:
            session.close()

    # -- manual triggers ------------------------------------------------------
    def _run_pipeline(dry_run: bool) -> None:
        """Run the full pipeline in a background thread."""
        import copy
        from app.services.run_coordinator import RunCoordinator
        s = copy.copy(settings)
        s.dry_run = dry_run
        coord = RunCoordinator(s)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coord.run_all())
        except Exception as exc:
            logger.error("Pipeline run failed (dry_run=%s): %s", dry_run, exc)
        finally:
            loop.close()

    @app.post("/trigger/dry-run", response_class=HTMLResponse)
    def trigger_dry_run(request: Request, user: str = Depends(auth)):
        import threading
        t = threading.Thread(target=_run_pipeline, args=(True,), daemon=True)
        t.start()
        logger.info("Dry-run triggered by %s", user)
        return RedirectResponse("/", status_code=303)

    @app.post("/trigger/live-run", response_class=HTMLResponse)
    def trigger_live_run(request: Request, user: str = Depends(auth)):
        import threading
        t = threading.Thread(target=_run_pipeline, args=(False,), daemon=True)
        t.start()
        logger.info("LIVE run triggered by %s", user)
        return RedirectResponse("/", status_code=303)
