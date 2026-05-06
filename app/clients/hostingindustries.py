"""HostingIndustries session-based scraper.

Handles login, cookie persistence, domain overview fetching and parsing
for one or two accounts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

BASE_URL = "https://domains.hostingindustries.nl"
LOGIN_URL = f"{BASE_URL}/login.php"
DOMAINS_URL = f"{BASE_URL}/domains.php"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}


@dataclass
class DomainSnapshot:
    domain_name: str
    extension: str
    full_domain: str
    status: str
    holder: str = ""
    start_date: str = ""
    end_date: str = ""
    account_key: str = ""
    account_name: str = ""
    raw_html: str = ""


class LoginError(Exception):
    pass


class FetchError(Exception):
    pass


class HostingIndustriesClient:
    def __init__(
        self,
        username: str,
        password: str,
        account_name: str = "default",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self._username = username
        self._password = password
        self._account_name = account_name
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            transport = httpx.HTTPTransport(retries=self._max_retries)
            self._client = httpx.Client(
                headers=BROWSER_HEADERS,
                follow_redirects=True,
                timeout=self._timeout,
                transport=transport,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # -- login ----------------------------------------------------------------

    def login(self) -> None:
        client = self._get_client()

        logger.info("GET %s (capture session cookie) for account '%s'", LOGIN_URL, self._account_name)
        resp = client.get(LOGIN_URL)
        resp.raise_for_status()

        if not client.cookies:
            logger.warning("No cookies received from GET login.php")

        login_data = {
            "username": self._username,
            "password": self._password,
        }
        post_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": LOGIN_URL,
            "Origin": BASE_URL,
        }

        logger.info("POST %s for account '%s'", LOGIN_URL, self._account_name)
        resp = client.post(LOGIN_URL, data=login_data, headers=post_headers)
        resp.raise_for_status()

        if self._is_login_page(resp.text):
            raise LoginError(
                f"Login failed for account '{self._account_name}': "
                "still seeing login form after POST."
            )

        logger.info("Login successful for account '%s'", self._account_name)

    @staticmethod
    def _is_login_page(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        form = soup.select_one("form[action='login.php']")
        login_panel = soup.select_one(".login-panel")
        return form is not None or login_panel is not None

    # -- fetch domains --------------------------------------------------------

    def fetch_domains_html(self) -> str:
        client = self._get_client()
        logger.info("GET %s for account '%s'", DOMAINS_URL, self._account_name)
        resp = client.get(DOMAINS_URL)
        resp.raise_for_status()

        if self._is_login_page(resp.text):
            raise FetchError(
                f"Session expired or not logged in for account '{self._account_name}'"
            )
        return resp.text

    def fetch_domains(self) -> list[DomainSnapshot]:
        html = self.fetch_domains_html()
        return self.parse_domains(html)

    # -- parsing --------------------------------------------------------------

    def parse_domains(self, html: str) -> list[DomainSnapshot]:
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("div.domains table.table")
        if table is None:
            table = soup.select_one("table.table")
        if table is None:
            logger.error("No domain table found in HTML for account '%s'", self._account_name)
            return []

        tbody = table.find("tbody")
        if tbody is None:
            logger.warning("No <tbody> in table for account '%s'", self._account_name)
            return []

        rows: list[Tag] = tbody.find_all("tr")  # type: ignore[assignment]
        snapshots: list[DomainSnapshot] = []

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            domain_name = cells[0].get_text(strip=True)
            extension = cells[1].get_text(strip=True)
            status = cells[2].get_text(strip=True)

            holder = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            start_date = cells[4].get_text(strip=True) if len(cells) > 4 else ""
            end_date = cells[5].get_text(strip=True) if len(cells) > 5 else ""

            full_domain = f"{domain_name}.{extension}"

            snapshots.append(
                DomainSnapshot(
                    domain_name=domain_name,
                    extension=extension,
                    full_domain=full_domain,
                    status=status,
                    holder=holder,
                    start_date=start_date,
                    end_date=end_date,
                    account_key=self._account_name,
                    account_name=self._account_name,
                    raw_html=str(row),
                )
            )

        logger.info(
            "Parsed %d domains from account '%s'", len(snapshots), self._account_name
        )
        return snapshots


def fetch_all_accounts(
    accounts: list[dict],
    timeout: int = 30,
    max_retries: int = 3,
) -> list[DomainSnapshot]:
    """Login and fetch domains from all configured accounts, merge results."""
    all_snapshots: list[DomainSnapshot] = []

    for acct in accounts:
        client = HostingIndustriesClient(
            username=acct["username"],
            password=acct["password"],
            account_name=acct["name"],
            timeout=timeout,
            max_retries=max_retries,
        )
        try:
            client.login()
            snapshots = client.fetch_domains()
            all_snapshots.extend(snapshots)
        except (LoginError, FetchError) as exc:
            logger.error("Account '%s' failed: %s", acct["name"], exc)
        except httpx.HTTPError as exc:
            logger.error("Network error for account '%s': %s", acct["name"], exc)
        finally:
            client.close()

    seen: dict[str, DomainSnapshot] = {}
    for snap in all_snapshots:
        key = snap.full_domain.lower()
        if key not in seen:
            seen[key] = snap

    deduped = list(seen.values())
    logger.info(
        "Total domains after merge/dedup: %d (from %d raw)",
        len(deduped),
        len(all_snapshots),
    )
    return deduped
