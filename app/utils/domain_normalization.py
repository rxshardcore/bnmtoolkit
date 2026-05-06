"""Normalize domains for comparison between HostingIndustries and the source DB."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_domain(raw: str) -> str:
    """Return a bare root-domain form suitable for matching.

    Handles inputs like:
      https://www.anieuws.be/  -> anieuws.be
      http://www.example.com   -> example.com
      www.example.com          -> example.com
      example.com              -> example.com
      EXAMPLE.COM/             -> example.com
    """
    value = raw.strip().lower()

    if "://" not in value:
        value = "http://" + value

    parsed = urlparse(value)
    host = parsed.hostname or parsed.path.split("/")[0]
    if not host:
        return value.strip("/")

    if host.startswith("www."):
        host = host[4:]

    return host.rstrip(".")
