"""Google Sheets integration via n8n webhook proxy.

Instead of managing OAuth2 tokens directly, we POST data to an n8n webhook
that uses the existing BM OAUTH2 credentials to update the Google Sheet.
This means zero OAuth configuration in this application.

Expected n8n workflow:
  1. Webhook trigger (POST, path: /webhook/domain-cleanup-sheets)
  2. Receives JSON body with {action, spreadsheet_id, sheet_name, rows}
  3. Uses existing BM OAUTH2 credential to update/append rows in the sheet
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1leL8nGuKMaWeWodefOxlLMJg4Zjb0hMu-9ZYI_bQX9M"

SHEET_GID_MAP = {
    "nl": {"gid": 0, "name": "Nederlandse domeinen"},
    "be": {"gid": 889084002, "name": "Belgische domeinen"},
    "de": {"gid": 1724723029, "name": "Duitse domeinen"},
    "com": {"gid": 716030372, "name": "Engelse domeinen"},
    "fr": {"gid": 1522027212, "name": "Franse domeinen"},
    "at": {"gid": 1910690628, "name": "Oostenrijkse domeinen"},
    "it": {"gid": 1949071364, "name": "Italiaanse domeinen"},
}

EXTENSION_TO_SHEET = {
    "nl": "nl",
    "be": "be",
    "de": "de",
    "at": "at",
    "com": "com",
    "fr": "fr",
    "it": "it",
    "eu": "nl",
}


def get_sheet_for_extension(extension: str) -> dict | None:
    key = EXTENSION_TO_SHEET.get(extension.lower())
    if key:
        return SHEET_GID_MAP.get(key)
    return None


def mark_domains_expired_via_n8n(
    webhook_url: str,
    domains: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict:
    """Send expired domain data to n8n webhook for Google Sheets update.

    Args:
        webhook_url: Full n8n webhook URL (e.g. https://n8n.bnm-server.org/webhook/domain-cleanup-sheets)
        domains: List of dicts with keys: full_domain, extension, status, matched, etc.
        dry_run: If True, n8n workflow should log but not write.

    Returns:
        Response dict from n8n.
    """
    if not webhook_url or not domains:
        logger.info("Sheets sync skipped: no webhook URL or no domains")
        return {"status": "skipped"}

    grouped: dict[str, list[dict]] = {}
    for d in domains:
        ext = d.get("extension", "").lower()
        sheet_info = get_sheet_for_extension(ext)
        if sheet_info:
            sheet_name = sheet_info["name"]
            if sheet_name not in grouped:
                grouped[sheet_name] = []
            grouped[sheet_name].append(d)

    results = {}
    for sheet_name, rows in grouped.items():
        payload = {
            "action": "mark_expired",
            "spreadsheet_id": SPREADSHEET_ID,
            "sheet_name": sheet_name,
            "dry_run": dry_run,
            "domains": [
                {
                    "domain": r.get("full_domain", ""),
                    "status": r.get("status", ""),
                    "extension": r.get("extension", ""),
                    "end_date": r.get("end_date", ""),
                    "account": r.get("account_name", ""),
                }
                for r in rows
            ],
        }

        try:
            resp = httpx.post(webhook_url, json=payload, timeout=120)
            resp.raise_for_status()
            body = resp.text[:500]
            results[sheet_name] = {"status": "ok", "count": len(rows), "response": body}
            logger.info(
                "Sheets sync via n8n: %s → %d domains sent, response: %s",
                sheet_name, len(rows), body[:200],
            )
        except httpx.TimeoutException:
            results[sheet_name] = {"status": "timeout", "count": len(rows)}
            logger.warning("Sheets sync timeout for %s (120s) — n8n may still be processing", sheet_name)
        except Exception as exc:
            results[sheet_name] = {"status": "error", "error": str(exc)}
            logger.error("Sheets sync failed for %s: %s", sheet_name, exc)

    return results
