"""Mailgun HTTP API integration for sending email drafts."""

from __future__ import annotations

import logging
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


def send_email(
    api_key: str,
    domain: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    html_body: str,
    api_url: str = "https://api.eu.mailgun.net",
    cc: str | None = None,
    reply_to: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> dict:
    """Send email via Mailgun.

    attachments: list of (filename, file_bytes, mime_type) tuples.
    """
    url = f"{api_url}/v3/{domain}/messages"
    data: dict = {
        "from": from_addr,
        "to": [to_addr],
        "subject": subject,
        "html": html_body,
    }
    if cc:
        data["cc"] = cc
    if reply_to:
        data["h:Reply-To"] = reply_to

    files = None
    if attachments:
        files = [("attachment", (name, content, mime)) for name, content, mime in attachments]

    resp = httpx.post(url, auth=("api", api_key), data=data, files=files, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    logger.info("Mailgun sent to %s (cc=%s, attachments=%d): %s",
                to_addr, cc or "-", len(attachments or []), result.get("id", "ok"))
    return result
