from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- run behaviour --------------------------------------------------------
    dry_run: bool = True
    log_level: str = "INFO"
    output_dir: Path = Path("/output")

    # -- source database 1 (Linkstatus Blauwe Monsters) -----------------------
    source_db1_host: str = ""
    source_db1_port: int = 3306
    source_db1_name: str = ""
    source_db1_user: str = ""
    source_db1_password: str = ""

    # -- source database 2 (Linkstatus Brand New Media) -----------------------
    source_db2_host: str = ""
    source_db2_port: int = 3306
    source_db2_name: str = ""
    source_db2_user: str = ""
    source_db2_password: str = ""

    # -- audit database -------------------------------------------------------
    audit_db_host: str = "localhost"
    audit_db_port: int = 3306
    audit_db_name: str = "domain_audit"
    audit_db_user: str = ""
    audit_db_password: str = ""

    # -- HostingIndustries account 1 ------------------------------------------
    hi_account1_username: str = ""
    hi_account1_password: str = ""
    hi_account1_name: str = "primary"

    # -- HostingIndustries account 2 (optional) -------------------------------
    hi_account2_username: str = ""
    hi_account2_password: str = ""
    hi_account2_name: str = "secondary"

    # -- dashboard ------------------------------------------------------------
    dashboard_username: str = "admin"
    dashboard_password: str = "changeme"
    dashboard_port: int = 8088

    # -- Mailgun --------------------------------------------------------------
    enable_email_send: bool = False
    mailgun_api_key: str = ""
    mailgun_domain: str = "bnm-server.org"
    mailgun_from: str = "noreply@bnm-server.org"
    mailgun_api_url: str = "https://api.eu.mailgun.net"

    # -- Google Sheets (via n8n webhook proxy) --------------------------------
    enable_sheets_sync: bool = False
    n8n_sheets_webhook_url: str = ""

    # -- business rules -------------------------------------------------------
    unusable_domain_statuses: str = "Quarantaine,Expiry,Expired,Suspended"
    affected_order_statuses: str = "failed,pending,processing"
    expired_label_id: int = 79

    # -- timeouts / retries ---------------------------------------------------
    hi_request_timeout: int = 30
    hi_max_retries: int = 3

    @property
    def unusable_statuses_list(self) -> list[str]:
        return [s.strip() for s in self.unusable_domain_statuses.split(",") if s.strip()]

    @property
    def affected_statuses_list(self) -> list[str]:
        return [s.strip() for s in self.affected_order_statuses.split(",") if s.strip()]

    # -- derived helpers ------------------------------------------------------

    def _db_url(self, host: str, port: int, name: str, user: str, password: str) -> str:
        return f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"

    @property
    def source_db_urls(self) -> list[dict]:
        """Return list of {name, url, send_emails} for all configured source databases."""
        dbs: list[dict] = []
        if self.source_db1_host and self.source_db1_name:
            dbs.append({
                "name": self.source_db1_name,
                "url": self._db_url(
                    self.source_db1_host, self.source_db1_port,
                    self.source_db1_name, self.source_db1_user, self.source_db1_password,
                ),
                "send_emails": True,
            })
        if self.source_db2_host and self.source_db2_name:
            dbs.append({
                "name": self.source_db2_name,
                "url": self._db_url(
                    self.source_db2_host, self.source_db2_port,
                    self.source_db2_name, self.source_db2_user, self.source_db2_password,
                ),
                "send_emails": False,
            })
        return dbs

    @property
    def audit_db_url(self) -> str:
        return self._db_url(
            self.audit_db_host, self.audit_db_port,
            self.audit_db_name, self.audit_db_user, self.audit_db_password,
        )

    @property
    def hi_accounts(self) -> list[dict]:
        accounts: list[dict] = []
        if self.hi_account1_username:
            accounts.append({
                "username": self.hi_account1_username,
                "password": self.hi_account1_password,
                "name": self.hi_account1_name,
            })
        if self.hi_account2_username:
            accounts.append({
                "username": self.hi_account2_username,
                "password": self.hi_account2_password,
                "name": self.hi_account2_name,
            })
        return accounts


def get_settings() -> Settings:
    return Settings()
